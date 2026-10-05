"""Measured camera correspondences and an explicitly draft 3D stock overlay."""

import math
import threading
import time

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Field, Surface, label
from carveracontroller.machine.camera_calibration_file import (
    CalibrationReference,
    calibration_data,
    read_calibration,
    write_calibration,
)
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    RegistrationObservation,
    fit_camera_pose,
)
from carveracontroller.webcam_view import WebcamTexture


class CameraRegistrationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.reference = None
        self.reference_revision = 0
        self.registration = None
        self.result = None
        self.fit_identity = None
        self.overlay_enabled = False
        self.reference_machine_y = None
        self.intrinsics = None
        self.observations = ()
        self.running = False
        self.add_widget(label("Camera registration", 15, height=26, bold=True))
        self.add_widget(
            label(
                "Known points: X Y Z (mm), image U V (pixels). Use measured Saunders hole coordinates in the bed frame.",
                11,
                MUTED,
                48,
            )
        )
        self.reference_texture = WebcamTexture()
        self.reference_view = self.reference_texture.new_view()
        self.reference_view.size_hint_y = None
        self.reference_view.height = dp(180)
        self.reference_view.bind(width=self._size_reference, on_touch_down=self._pick_reference)
        self.picking_reference = False
        self.reference_view.empty_text = "Capture a reference image before entering correspondences"
        self.add_widget(self.reference_view)
        self.reference_note = label("No image bound · the live camera remains live", 11, MUTED, 48)
        self.add_widget(self.reference_note)
        self.add_widget(Action("Capture reference image", self.capture_reference))
        self.points = Field(
            text="", hint_text="X Y Z U V · one correspondence per line", multiline=True, height=dp(110)
        )
        self.add_widget(self.points)
        self.points.bind(text=self._draw_reference_points)
        self.world_point = Field(text="", hint_text="Known point X Y Z · mm")
        self.add_widget(self.world_point)
        self.pick_button = Action("Pick image point", self.toggle_point_pick)
        self.add_widget(self.pick_button)
        self.focal = Field(text="", hint_text="Intrinsic prior: fx fy cx cy (pixels)")
        self.add_widget(self.focal)
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        actions.add_widget(Action("Load calibration", self.load))
        actions.add_widget(Action("Fit registration", self.fit))
        actions.add_widget(Action("Save calibration", self.save))
        self.overlay_button = Action("Show stock overlay", self.toggle_overlay)
        actions.add_widget(self.overlay_button)
        self.add_widget(actions)
        self.note = label(
            "Image calibration, bed registration and stock placement each need evidence. An outline is a setup preview.",
            11,
            MUTED,
            64,
        )
        self.add_widget(self.note)

    def _size_reference(self, *_):
        size = self.reference.frame.size if self.reference else (16, 9)
        self.reference_view.height = max(dp(100), min(dp(360), self.reference_view.width * size[1] / size[0]))

    def toggle_point_pick(self):
        self.picking_reference = not self.picking_reference
        self.pick_button.text = "Cancel point pick" if self.picking_reference else "Pick image point"
        if self.picking_reference:
            self.note.text = "Enter known X Y Z, then click its location in the frozen reference image."

    def _pick_reference(self, _view, touch):
        if not self.picking_reference or self.reference is None or self.running:
            return False
        pixel = self.reference_view.local_to_image_pixel(touch.pos)
        if pixel is None:
            return False
        try:
            world = [float(v) for v in self.world_point.text.replace(",", " ").split()]
            if len(world) != 3 or not all(math.isfinite(v) for v in world):
                raise ValueError("Enter three finite known coordinates X Y Z")
            lines = [line for line in self.points.text.splitlines() if line.strip()]
            if len(lines) >= 128:
                raise ValueError("At most 128 correspondences")
            lines.append(" ".join(f"{v:.6f}" for v in (*world, *pixel)))
            self.points.text = "\n".join(lines)
            self.picking_reference = False
            self.pick_button.text = "Pick image point"
            self.note.text = f"Correspondence {len(lines)} added · U {pixel[0]:.2f}, V {pixel[1]:.2f} px"
        except ValueError as exc:
            self.note.text = str(exc)
        return True

    def _draw_reference_points(self, *_):
        if self.reference is None:
            self.reference_view.set_overlay((), None)
            return
        segments = []
        for line in self.points.text.splitlines()[:128]:
            try:
                values = [float(v) for v in line.replace(",", " ").split()]
                if len(values) != 5 or not all(math.isfinite(v) for v in values):
                    continue
                u, v = values[-2:]
                segments.extend((((u - 3, v), (u + 3, v)), ((u, v - 3), (u, v + 3))))
            except ValueError:
                continue
        self.reference_view.set_overlay(segments, self.reference.frame.size)

    def capture_reference(self):
        recorder = getattr(self.workspace, "run_recording_panel", None)
        if recorder is not None and recorder.camera_replay_enabled:
            self.note.text = "Show live camera before capturing a calibration reference."
            return
        if self.running:
            self.note.text = "Wait for the current calibration operation."
            return
        enabled, frame, generation, source = self.workspace.camera_client.calibration_snapshot()
        if not enabled or frame is None or frame.age() is None or frame.age() > 2 or not frame.jpeg:
            self.note.text = "Capture needs a fresh JPEG with a server capture timestamp."
            return
        controller = self.workspace.machine.controller
        pose = getattr(controller, "observed_pose", None)
        fresh = pose is not None and pose.fresh(time.monotonic())
        self.reference = CalibrationReference(
            frame,
            source,
            generation,
            getattr(controller, "_connection_generation", 0),
            tuple(pose.machine_mm) if fresh else None,
            pose.timestamp if fresh else None,
        )
        self.reference_revision += 1
        self.registration = self.result = self.fit_identity = None
        self.reference_machine_y = None
        self.observations = ()
        self.points.text = ""
        self._show_reference()
        self.note.text = "Reference captured. Enter measured points against this frozen image."
        self.update_overlay()

    def _show_reference(self):
        reference = self.reference
        self.reference_texture.update(None)
        self.reference_texture.update(reference.frame if reference else None)
        self._size_reference()
        self._draw_reference_points()
        self.reference_note.text = (
            f"Frozen frame {reference.frame.sequence} · {reference.frame.size[0]} × {reference.frame.size[1]} pixels\n"
            + (
                f"Observed table Y {reference.machine_mm[1]:.3f} mm"
                if reference.machine_mm
                else "No fresh machine pose bound"
            )
            + " · exposure synchronization unqualified"
            if reference
            else "Legacy calibration · reference image unavailable; capture before refitting"
        )

    def _input_identity(self):
        return self.reference_revision, self.points.text, self.focal.text

    def _owner_identity(self):
        profile = getattr(self.workspace, "selected_machine_profile", None)
        return (
            self.workspace.camera_client.calibration_snapshot()[2:],
            getattr(self.workspace.machine.controller, "_connection_generation", 0),
            profile.get("id") if isinstance(profile, dict) else None,
        )

    def fit(self):
        recorder = getattr(self.workspace, "run_recording_panel", None)
        if recorder is not None and recorder.camera_replay_enabled:
            self.note.text = (
                "Show live camera before fitting a live registration; historical registration is unavailable."
            )
            return
        if self.running:
            return
        try:
            reference = self.reference
            if reference is None:
                raise ValueError("Capture a reference image before fitting calibration")
            frame = reference.frame
            values = [float(value) for value in self.focal.text.replace(",", " ").split()]
            if len(values) != 4:
                raise ValueError("Enter fx fy cx cy, or load measured intrinsics")
            intrinsics = CameraIntrinsics(
                *frame.size, *values, self.intrinsics.distortion if self.intrinsics else (0, 0, 0, 0, 0)
            )
            observations = []
            for line in self.points.text.splitlines():
                if not line.strip():
                    continue
                values = [float(value) for value in line.replace(",", " ").split()]
                if len(values) != 5:
                    raise ValueError("Each correspondence needs X Y Z U V")
                if not 0 <= values[3] < frame.size[0] or not 0 <= values[4] < frame.size[1]:
                    raise ValueError("Correspondence pixels must lie inside the frozen image")
                observations.append(RegistrationObservation(tuple(values[:3]), tuple(values[3:])))
            if len(observations) > 128:
                raise ValueError("Fit at most 128 well-spread correspondences")
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.note.text = "Fitting camera pose and calculating reprojection residuals…"
        identity = self._input_identity()
        owner = self._owner_identity()
        reference_y = reference.machine_mm[1] if reference.machine_mm else None

        def run():
            try:
                result = fit_camera_pose(intrinsics, observations)
                error = None
            except (ValueError, ArithmeticError) as exc:
                result, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def finish(result, error):
            self.running = False
            if identity != self._input_identity() or owner != self._owner_identity():
                self.note.text = (
                    "Fit discarded: inputs, camera source or connection changed. Fit the reviewed reference again."
                )
                return
            if error:
                self.note.text = "Registration not applied: " + error
                return
            self.result, self.registration, self.intrinsics = result, result.registration, intrinsics
            self.fit_identity = identity
            self.observations = tuple(observations)
            self.reference_machine_y = reference_y
            self.note.text = (
                f"Fit RMS {result.rms_px:.2f} px · max {result.max_px:.2f} px · "
                f"{len(result.outlier_indices)} outliers\n"
                + "; ".join(result.warnings)
                + "\nDraft registration · intrinsic prior and physical datum remain unqualified"
            )
            if self.reference_machine_y is None:
                self.note.text += "\nNo live table position was bound; the overlay is withheld."
            self.update_overlay()

        threading.Thread(target=run, daemon=True).start()

    def toggle_overlay(self):
        self.overlay_enabled = not self.overlay_enabled
        self.overlay_button.text = "Hide stock overlay" if self.overlay_enabled else "Show stock overlay"
        self.update_overlay()

    def update_overlay(self):
        recorder = getattr(self.workspace, "run_recording_panel", None)
        if recorder is not None and recorder.camera_replay_enabled:
            for view in self.workspace.camera_texture.views:
                view.set_overlay((), None)
            return
        segments = []
        size = None
        source_matches = (
            self.reference is not None
            and self.reference.source_sha256 == self.workspace.camera_client.calibration_snapshot()[3]
        )
        if (
            self.overlay_enabled
            and self.registration
            and source_matches
            and self.fit_identity == self._input_identity()
        ):
            frame = self.workspace.camera_client.snapshot()[1]
            viewer = self.workspace.machine.gcode_viewer
            setup = viewer.machine_setup
            size = (self.registration.intrinsics.width, self.registration.intrinsics.height)
            pose = getattr(self.workspace.machine.controller, "observed_pose", None)
            if (
                frame
                and frame.size == size
                and frame.age() is not None
                and frame.age() <= 2
                and setup.stock_size_mm
                and self.reference_machine_y is not None
                and pose
                and pose.fresh(time.monotonic())
            ):
                low = setup.machine_point(setup.stock_origin_mm)
                high = tuple(a + b for a, b in zip(low, setup.stock_size_mm))
                # Observations are entered in the bed frame. Calibration is
                # valid at the recorded table pose; bed movement is accounted
                # for using the declared C1 table translation.
                shift = self.reference_machine_y - pose.machine_mm[1]
                corners = [
                    (x, y + shift, z) for z in (low[2], high[2]) for y in (low[1], high[1]) for x in (low[0], high[0])
                ]
                try:
                    pixels = [self.registration.project(point) for point in corners]
                    edges = (
                        (0, 1),
                        (1, 3),
                        (3, 2),
                        (2, 0),
                        (4, 5),
                        (5, 7),
                        (7, 6),
                        (6, 4),
                        (0, 4),
                        (1, 5),
                        (2, 6),
                        (3, 7),
                    )
                    segments = [(pixels[a], pixels[b]) for a, b in edges]
                except ValueError:
                    segments = []
        for view in self.workspace.camera_texture.views:
            view.set_overlay(segments, size)

    def _background(self, operation, finish):
        if self.running:
            self.note.text = "Wait for the current calibration operation."
            return
        self.running = True
        identity = self._input_identity()
        owner = self._owner_identity()
        self.note.text = "Preparing calibration file…"

        def run():
            try:
                result, error = operation(), None
            except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
                result, error = None, str(exc)
            Clock.schedule_once(lambda _dt: publish(result, error), 0)

        def publish(result, error):
            self.running = False
            if error:
                self.note.text = "Calibration operation failed: " + error
            elif identity != self._input_identity() or owner != self._owner_identity():
                self.note.text = "Inputs or owner changed; result withheld. Any written export is retained."
            else:
                finish(result)

        threading.Thread(target=run, name="camera-calibration-file", daemon=True).start()

    def save(self):
        if self.registration is None:
            self.note.text = "Fit or load registration before saving."
            return

        if self.fit_identity != self._input_identity():
            self.note.text = "Correspondences or intrinsics changed. Refit before saving."
            return

        def selected(path):
            # Snapshot immutable references and numeric evidence before starting IO.
            registration, observations, reference, reference_y = (
                self.registration,
                self.observations,
                self.reference,
                self.reference_machine_y,
            )
            self._background(
                lambda: write_calibration(path, calibration_data(registration, observations, reference, reference_y)),
                lambda digest: setattr(self.note, "text", "Saved and read back calibration · SHA256 " + digest),
            )

        self.workspace.choose_profile_file(selected, save=True, extension=".cvcal", title="Save camera calibration")

    def load(self):
        def selected(path):
            def finish(result):
                self.apply_calibration(result)

            self._background(lambda: read_calibration(path), finish)

        self.workspace.choose_asset_file(selected, suffixes=(".cvcal",))

    def apply_calibration(self, result):
        """Replace every calibration component together, including absent images."""
        self.reference_revision += 1
        self.picking_reference = False
        self.pick_button.text = "Pick image point"
        self.result = None
        if result is None:
            self.registration = self.intrinsics = self.reference = self.reference_machine_y = None
            self.observations = ()
            self.focal.text = self.points.text = ""
            self.fit_identity = None
            self._show_reference()
            self.note.text = "No camera calibration retained in this job."
        else:
            registration, observations, reference, reference_y = result
            self.registration, self.intrinsics, self.observations = registration, registration.intrinsics, observations
            self.reference, self.reference_machine_y = reference, reference_y
            self.focal.text = " ".join(
                f"{v:g}"
                for v in (
                    registration.intrinsics.fx,
                    registration.intrinsics.fy,
                    registration.intrinsics.cx,
                    registration.intrinsics.cy,
                )
            )
            self.points.text = "\n".join(" ".join(f"{v:g}" for v in (*o.world_mm, *o.pixel)) for o in observations)
            self.fit_identity = self._input_identity()
            self._show_reference()
            self.note.text = (
                "Loaded calibration and verified reference image. Physical setup and exposure timing remain unqualified."
                if reference
                else "Loaded legacy calibration without reference image. Overlay withheld; capture a new image before refitting."
            )
        self.update_overlay()
