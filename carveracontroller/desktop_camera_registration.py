"""Measured camera correspondences and an explicitly draft 3D stock overlay."""

import math
import threading
import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    Field,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.machine.camera_calibration_file import (
    CalibrationReference,
    calibration_data,
    read_calibration,
    write_calibration,
)
from carveracontroller.machine.camera_coverage import parse_correspondences, review_coverage
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraRegistration,
    fit_camera_pose,
)
from carveracontroller.webcam_view import RegisteredCameraImage, WebcamTexture


class ReferenceCameraImage(RegisteredCameraImage):
    """Consume a measured pick before the framing gesture can grab its touch."""

    def __init__(self, **kwargs):
        self.pick_handler = None
        super().__init__(**kwargs)
        self.interactive = True
        self.is_focusable = True

    def on_touch_down(self, touch):
        if self.pick_handler is not None and self.pick_handler(self, touch):
            return True
        return super().on_touch_down(touch)


class CameraRegistrationPanel(Surface):
    def __init__(self, workspace, source=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), **kwargs)
        self.workspace = workspace
        self.reference = None
        self.reference_revision = 0
        self.registration = None
        self.result = None
        self.fit_identity = None
        self.overlay_enabled = False
        self.reference_machine_y = None
        self.intrinsics = None
        self.lens_distortion = (0.0, 0.0, 0.0, 0.0, 0.0)
        self.lens_model_size = None
        self.lens_model_source = None
        self.observations = ()
        self.running = False
        self.sections = ScreenManager(transition=NoTransition())
        self.section_buttons = {}
        tabs = AdaptiveGrid(max_cols=3, min_width=100, row_height=36, spacing=dp(6))
        contents = {}
        names = ("Source", "Reference", "Fit & exchange") if source is not None else ("Reference", "Fit & exchange")
        for name in names:
            button = Action(name, lambda name=name: self.select_section(name))
            self.section_buttons[name] = button
            tabs.add_widget(button)
            content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
            content.bind(minimum_height=content.setter("height"))
            scroll = DesktopScrollView(do_scroll_x=False)
            scroll.add_widget(content)
            screen = Screen(name=name)
            screen.add_widget(scroll)
            self.sections.add_widget(screen)
            contents[name] = content
        if source is not None:
            contents["Source"].add_widget(source)
        self.add_widget(tabs)
        self.add_widget(self.sections)
        reference = contents["Reference"]
        self._reference_content = reference
        fitting = contents["Fit & exchange"]
        self.reference_texture = WebcamTexture()
        self.reference_view = self.reference_texture.new_view(ReferenceCameraImage)
        self.reference_view.size_hint_y = None
        self.reference_view.height = dp(180)
        self.reference_view.bind(width=self._size_reference)
        self.reference_view.pick_handler = self._pick_reference
        self.picking_reference = False
        self._pick_undo = None
        self.reference_view.empty_text = "Capture a reference image before entering correspondences"
        self.world_point = Field(text="", hint_text="Measured bed-frame X Y Z · mm")
        reference.add_widget(self.world_point)
        self.pick_button = Action("Pick image point", self.toggle_point_pick)
        self.undo_pick_button = Action("Undo last pick", self.undo_point_pick)
        capture_actions = AdaptiveGrid(max_cols=3, min_width=90, row_height=34, spacing=dp(6))
        capture_actions.add_widget(Action("Capture reference", self.capture_reference))
        capture_actions.add_widget(self.pick_button)
        capture_actions.add_widget(self.undo_pick_button)
        reference.add_widget(capture_actions)
        framing = AdaptiveGrid(max_cols=3, min_width=90, row_height=30, spacing=dp(6))
        framing.add_widget(Action("Zoom +", lambda: self.reference_view.zoom_by(1.5)))
        framing.add_widget(Action("Zoom −", lambda: self.reference_view.zoom_by(1 / 1.5)))
        framing.add_widget(Action("Fit image", self.reference_view.reset_framing))
        reference.add_widget(framing)
        self._reference_primary_controls = (self.world_point, capture_actions, framing)
        reference.add_widget(self.reference_view)
        self.reference_note = label("No image bound · the live camera remains live", 11, MUTED, 48)
        reference.add_widget(self.reference_note)
        from carveracontroller.desktop_pointer_trace import PointerTrace

        self.pointer_note = label("Pointer diagnostics are off; no input is retained.", 11, MUTED, 112)
        panes = {"reference": self.reference_view}
        machine_view = getattr(getattr(workspace, "machine", None), "gcode_viewer", None)
        if machine_view is not None:
            panes["machine"] = machine_view
        self.pointer_trace = PointerTrace(panes, self._refresh_pointer_trace)
        self.pointer_button = Action("Trace pointer · 30 s", self._toggle_pointer_trace)
        reference.add_widget(self.pointer_button)
        reference.add_widget(self.pointer_note)
        self.bind(parent=self._pointer_parent)
        self.review_note = label("", 11, MUTED, 64)
        fitting.add_widget(self.review_note)
        self.points = Field(
            text="", hint_text="X Y Z U V · one correspondence per line", multiline=True, height=dp(110)
        )
        fitting.add_widget(self.points)
        self.points.bind(text=self._draw_reference_points)
        self.coverage_note = label("Capture a reference to review point coverage", 11, MUTED, 80)
        reference.add_widget(self.coverage_note)
        self.residual_review = Field(
            text="Fit registration to review each point's image error", readonly=True, multiline=True, height=dp(150)
        )
        self.focal = Field(text="", hint_text="Intrinsic prior: fx fy cx cy (pixels)")
        fitting.add_widget(self.focal)
        self.lens_button = Action("Edit lens model…", self.edit_lens)
        fitting.add_widget(self.lens_button)
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        actions.add_widget(Action("Load calibration", self.load))
        actions.add_widget(Action("Fit registration", self.fit))
        self.save_button = Action("Save calibration", self.save)
        actions.add_widget(self.save_button)
        self.overlay_button = Action("Show stock overlay", self.toggle_overlay)
        actions.add_widget(self.overlay_button)
        fitting.add_widget(actions)
        # Keep fitting/exchange actions above the optional per-point detail.
        # Native short windows otherwise require scrolling past an empty table
        # just to reach Fit/Save.
        fitting.add_widget(self.residual_review)
        self.note = label(
            "Image calibration, bed registration and stock placement each need evidence. An outline is a setup preview.",
            11,
            MUTED,
            64,
        )
        self.add_widget(self.note)
        self.points.bind(text=self._refresh_review)
        self.focal.bind(text=self._refresh_review)
        self.sections.bind(height=self._size_reference)
        reference.bind(minimum_height=self._size_reference)
        self.select_section(names[0])

    def _refresh_review(self, *_):
        lines = [line for line in self.points.text.splitlines() if line.strip()]
        reference = self.reference
        image = (
            f"Frame {reference.frame.sequence} · {reference.frame.size[0]} × {reference.frame.size[1]} px"
            if reference
            else "No reference image · open Reference to capture"
        )
        current = self.registration is not None and self.fit_identity == self._input_identity()
        if self.running:
            state = "Calibration operation in progress"
        elif current:
            state = "Current registration · save available" if reference else "Legacy registration · no image bound"
        elif self.registration is not None:
            state = "Inputs changed · refit before saving"
        elif self._lens_reference_mismatch():
            state = "Lens prior belongs to another image size or source · review lens model before fitting"
        else:
            state = "Enter intrinsics and measured correspondences, then fit"
        self.review_note.text = f"{image} · {len(lines)}/128 correspondences\n{state}"
        self.save_button.disabled = self.running or not current
        self.lens_button.disabled = self.running or reference is None
        self._refresh_coverage(current)
        undo = self._pick_undo
        self.undo_pick_button.disabled = (
            self.running or undo is None or undo[:2] != (self.reference_revision, self.points.text)
        )

    def _refresh_coverage(self, current):
        if self.reference is None:
            self.coverage_note.text = "Capture a reference to review point coverage"
            self.residual_review.text = "No frozen reference image available"
            return
        try:
            size = self.reference.frame.size
            observations = parse_correspondences(self.points.text, size)
            registration = self.registration if current and isinstance(self.registration, CameraRegistration) else None
            review = review_coverage(observations, size, registration)
            heights = review.z_range_mm
            height_note = (
                "No entered heights"
                if heights is None
                else f"All entered points at Z {heights[0]:g} mm; raised stock needs separate height/datum checks"
                if abs(heights[1] - heights[0]) < 1e-5
                else f"Entered Z {heights[0]:g} to {heights[1]:g} mm; height accuracy is unqualified"
            )
            self.coverage_note.text = (
                f"Point hull covers {review.image_fraction * 100:.1f}% of image area · {len(observations)} points\n"
                + height_note
                + "\nCoverage describes point distribution, not calibration accuracy."
            )
            self.residual_review.text = (
                "Point · image error (pixels) · >3 px flagged\n"
                + "\n".join(
                    f"{i + 1:3d} · {value:.3f} px" + (" · inspect" if value > 3 else "")
                    for i, value in enumerate(review.residuals_px)
                )
                if registration
                else "Fit the current inputs to review per-point image errors"
            )
        except (ValueError, ArithmeticError) as exc:
            self.coverage_note.text = str(exc)
            self.residual_review.text = "Review correspondences before fitting"

    def _refresh_pointer_trace(self):
        self.pointer_button.text = "Stop pointer trace" if self.pointer_trace.active else "Trace pointer · 30 s"
        self.pointer_note.text = self.pointer_trace.summary()

    def _toggle_pointer_trace(self):
        if self.pointer_trace.active:
            self.pointer_trace.stop()
        else:
            self.pointer_trace.start()

    def _pointer_parent(self, _panel, parent):
        if parent is None:
            self.pointer_trace.stop("Panel detached")

    def select_section(self, name):
        if self.sections.current != name:
            self.pointer_trace.stop("Reference section left")
            release_screen_focus(self.sections.current_screen)
        self.sections.current = name
        self._refresh_review()
        for key, button in self.section_buttons.items():
            selected = key == name
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()

    def _size_reference(self, *_):
        size = self.reference.frame.size if self.reference else (16, 9)
        # Preserve a useful image for measured picking; metadata can scroll.
        # Squeezing to fit every control made the native reference only 100 dp.
        controls = (
            sum(control.height for control in self._reference_primary_controls) + 3 * self._reference_content.spacing
        )
        available = max(dp(180), self.sections.height - controls)
        height = max(dp(180), min(dp(420), self.reference_view.width * size[1] / size[0], available))
        if abs(self.reference_view.height - height) > 0.1:
            self.reference_view.height = height

    def toggle_point_pick(self):
        if self.running or self.reference is None:
            self.note.text = "Capture a reference before selecting a measured point."
            return
        self.picking_reference = not self.picking_reference
        self.pick_button.text = "Cancel point pick" if self.picking_reference else "Pick image point"
        if self.picking_reference:
            self.note.text = "Pick mode: enter measured X Y Z, then click its frozen image location. Scroll zooms; double click fits."

    def _pick_reference(self, _view, touch):
        if not self.picking_reference or self.reference is None or self.running:
            return False
        if getattr(touch, "button", "left") != "left" or getattr(touch, "is_double_tap", False):
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
            previous = self.points.text
            updated = "\n".join(lines)
            self._pick_undo = (self.reference_revision, updated, previous)
            self.points.text = updated
            self.picking_reference = False
            self.pick_button.text = "Pick image point"
            self.note.text = f"Correspondence {len(lines)} added · U {pixel[0]:.2f}, V {pixel[1]:.2f} px"
        except ValueError as exc:
            self.note.text = str(exc)
        return True

    def undo_point_pick(self):
        undo = self._pick_undo
        if self.running or undo is None or undo[:2] != (self.reference_revision, self.points.text):
            self.note.text = "Undo unavailable: reference or correspondences changed."
            return
        self._pick_undo = None
        self.points.text = undo[2]
        self.note.text = "Last image pick undone; earlier correspondences retained."
        self._refresh_review()

    def _draw_reference_points(self, *_):
        if self.reference is None:
            self.reference_view.set_overlay((), None)
            return
        segments = []
        try:
            observations = parse_correspondences(self.points.text, self.reference.frame.size)
            hull = review_coverage(observations, self.reference.frame.size).hull
            if len(hull) >= 3:
                segments.extend(zip(hull, hull[1:] + hull[:1]))
            for observation in observations:
                u, v = observation.pixel
                segments.extend((((u - 3, v), (u + 3, v)), ((u, v - 3), (u, v + 3))))
        except ValueError:
            pass
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
        self._pick_undo = None
        self.picking_reference = False
        self.pick_button.text = "Pick image point"
        self.reference_view.reset_framing()
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

        self._refresh_review()

    def _input_identity(self):
        return (
            self.reference_revision,
            self.points.text,
            self.focal.text,
            self.lens_distortion,
            self.lens_model_size,
            self.lens_model_source,
        )

    def _lens_reference_mismatch(self):
        reference = self.reference
        return reference is not None and (
            self.lens_model_size is not None
            and self.lens_model_size != reference.frame.size
            or self.lens_model_source is not None
            and self.lens_model_source != reference.source_sha256
        )

    def edit_lens(self):
        from carveracontroller.desktop_camera_lens import open_camera_lens

        if self.running:
            self.note.text = "Wait for the current calibration operation before editing its lens model."
            return None
        return open_camera_lens(self)

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
            if self._lens_reference_mismatch():
                raise ValueError(
                    "Lens prior image size or camera source differs. Review and apply the lens model "
                    "for this reference before fitting; pixel values are not automatically scaled."
                )
            frame = reference.frame
            values = [float(value) for value in self.focal.text.replace(",", " ").split()]
            if len(values) != 4:
                raise ValueError("Enter fx fy cx cy, or load measured intrinsics")
            intrinsics = CameraIntrinsics(*frame.size, *values, self.lens_distortion)
            observations = parse_correspondences(self.points.text, frame.size)
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self._refresh_review()
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
            self._refresh_review()
            if identity != self._input_identity() or owner != self._owner_identity():
                self.note.text = (
                    "Fit discarded: inputs, camera source or connection changed. Fit the reviewed reference again."
                )
                return
            if error:
                self.note.text = "Registration not applied: " + error
                return
            self.result, self.registration, self.intrinsics = result, result.registration, intrinsics
            self.lens_model_size = reference.frame.size
            self.lens_model_source = reference.source_sha256
            self.fit_identity = self._input_identity()
            self._refresh_review()
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
                low = setup.stock_origin_mm
                high = tuple(a + b for a, b in zip(low, setup.stock_size_mm))
                # Observations are entered in the bed frame. Calibration is
                # valid at the recorded table pose; bed movement is accounted
                # for using the declared C1 table translation.
                shift = self.reference_machine_y - pose.machine_mm[1]
                corners = []
                for z in (low[2], high[2]):
                    for y in (low[1], high[1]):
                        for x in (low[0], high[0]):
                            # Match the stock mesh: rotate about its program-space
                            # center, then apply WCS and the observed table shift.
                            mx, my, mz = setup.machine_point(setup.stock_point((x, y, z)))
                            corners.append((mx, my + shift, mz))
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
        self._refresh_review()
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
            self._refresh_review()
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

        # The file picker is asynchronous; reconnects or other input changes can
        # occur while it is open. Keep the reviewed fit bound to this request.
        identity, owner, reviewed_registration = self._input_identity(), self._owner_identity(), self.registration

        def selected(path):
            if (
                identity != self._input_identity()
                or owner != self._owner_identity()
                or self.registration is not reviewed_registration
                or self.fit_identity != identity
            ):
                self.note.text = "Calibration changed while choosing a file; review and save again. No file written."
                return
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
            self.lens_distortion = (0.0, 0.0, 0.0, 0.0, 0.0)
            self.lens_model_size = self.lens_model_source = None
            self.registration = self.intrinsics = self.reference = self.reference_machine_y = None
            self.observations = ()
            self.focal.text = self.points.text = ""
            self.fit_identity = None
            self._show_reference()
            self.note.text = "No camera calibration retained in this job."
        else:
            registration, observations, reference, reference_y = result
            self.registration, self.intrinsics, self.observations = registration, registration.intrinsics, observations
            self.lens_distortion = registration.intrinsics.distortion
            self.lens_model_size = (registration.intrinsics.width, registration.intrinsics.height)
            self.lens_model_source = reference.source_sha256 if reference else None
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
