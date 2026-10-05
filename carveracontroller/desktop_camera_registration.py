"""Measured camera correspondences and an explicitly draft 3D stock overlay."""

import json
import threading
import time
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Field, Surface, label
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraRegistration,
    RegistrationObservation,
    fit_camera_pose,
)


class CameraRegistrationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.registration = None
        self.result = None
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
        self.points = Field(
            text="", hint_text="X Y Z U V · one correspondence per line", multiline=True, height=dp(110)
        )
        self.add_widget(self.points)
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
            frame = self.workspace.camera_client.snapshot()[1]
            if frame is None:
                raise ValueError("Receive a camera frame before fitting calibration")
            if frame.age() is None or frame.age() > 2:
                raise ValueError("Calibration needs a fresh captured image")
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
                observations.append(RegistrationObservation(tuple(values[:3]), tuple(values[3:])))
            if len(observations) > 128:
                raise ValueError("Fit at most 128 well-spread correspondences")
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.note.text = "Fitting camera pose and calculating reprojection residuals…"
        pose = getattr(self.workspace.machine.controller, "observed_pose", None)
        reference_y = pose.machine_mm[1] if pose and pose.fresh(time.monotonic()) else None

        def run():
            try:
                result = fit_camera_pose(intrinsics, observations)
                error = None
            except (ValueError, ArithmeticError) as exc:
                result, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def finish(result, error):
            self.running = False
            if error:
                self.note.text = "Registration not applied: " + error
                return
            self.result, self.registration, self.intrinsics = result, result.registration, intrinsics
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
        if self.overlay_enabled and self.registration:
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

    def save(self):
        if self.registration is None:
            self.note.text = "Fit or load registration before saving."
            return

        def selected(path):
            data = {
                "schema": 1,
                "registration": self.registration.to_dict(),
                "observations": [o.to_dict() for o in self.observations],
                "reference_machine_y_mm": self.reference_machine_y,
                "physical_qualification": "unqualified",
            }
            try:
                Path(path).write_text(json.dumps(data, indent=2))
                self.note.text = "Saved calibration · " + path
            except OSError as exc:
                self.note.text = str(exc)

        self.workspace.choose_profile_file(selected, save=True, extension=".cvcal", title="Save camera calibration")

    def load(self):
        def selected(path):
            try:
                source = Path(path)
                if source.stat().st_size > 512 * 1024:
                    raise ValueError("Calibration file exceeds 512 KB")
                data = json.loads(source.read_text())
                if data.get("schema") != 1:
                    raise ValueError("Unsupported camera calibration schema")
                registration = CameraRegistration.from_dict(data["registration"])
                observations = tuple(RegistrationObservation.from_dict(o) for o in data.get("observations", []))
                raw_reference = data.get("reference_machine_y_mm")
                reference_y = float(raw_reference) if raw_reference is not None else None
                if (reference_y is not None and not -1000 <= reference_y <= 1000) or len(observations) > 128:
                    raise ValueError("Invalid registration metadata")
                self.registration, self.intrinsics, self.observations = (
                    registration,
                    registration.intrinsics,
                    observations,
                )
                self.reference_machine_y = reference_y
                self.focal.text = " ".join(
                    f"{value:g}"
                    for value in (
                        registration.intrinsics.fx,
                        registration.intrinsics.fy,
                        registration.intrinsics.cx,
                        registration.intrinsics.cy,
                    )
                )
                self.points.text = "\n".join(" ".join(f"{v:g}" for v in (*o.world_mm, *o.pixel)) for o in observations)
                self.note.text = (
                    "Loaded registration · source image size and physical setup must match; qualification remains open."
                )
                self.update_overlay()
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.note.text = "Calibration not applied: " + str(exc)

        self.workspace.choose_asset_file(selected, suffixes=(".cvcal",))
