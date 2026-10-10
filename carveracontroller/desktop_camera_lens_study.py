"""Captured multi-view lens study; one cancellable worker and explicit draft apply."""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, Choice, Field, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.camera_coverage import parse_correspondences, review_coverage
from carveracontroller.machine.camera_lens_study import (
    CameraLensStudy,
    LensCapture,
    read_lens_study,
    write_lens_study,
)
from carveracontroller.machine.camera_registration import CalibrationResult, CameraIntrinsics, calibrate_camera


class CameraLensStudyPanel(BoxLayout):
    def __init__(self, panel, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(8), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.panel = panel
        self.study: CameraLensStudy | None = None
        self.revision = 0
        self.result: tuple[CameraIntrinsics, tuple[CalibrationResult, ...]] | None = None
        self.result_identity = None
        self.result_owner = None
        self.cancel_event: threading.Event | None = None
        self.disposed = False
        self.add_widget(
            content_label(
                "Measure a rigid calibration target in 3–12 distinctly tilted views. "
                "Capture each image in Reference, enter 8–100 known X Y Z U V points, then Add view here. "
                "The measurements must describe the target in its own coordinate frame."
            )
        )
        self.summary = content_label("No lens study · a lens prior and measured reference are required")
        self.add_widget(self.summary)
        self.distortion_choice = Choice(
            text="Fit lens distortion", values=("Fit lens distortion", "Keep prior distortion")
        )
        self.distortion_choice.bind(text=lambda *_: self.refresh())
        self.add_widget(self.distortion_choice)
        actions = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.add_button = Action("Add reference view", self.add_reference)
        self.prior_button = Action("Use current lens prior", self.use_prior)
        actions.add_widget(self.add_button)
        actions.add_widget(self.prior_button)
        self.add_widget(actions)
        self.capture_choice = Choice(text="No views", values=())
        self.capture_choice.bind(text=lambda *_: self.refresh())
        self.add_widget(self.capture_choice)
        review = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.review_button = Action("Review selected image…", self.review_selected)
        self.remove_button = Action("Remove selected view", self.remove_selected)
        review.add_widget(self.review_button)
        review.add_widget(self.remove_button)
        self.add_widget(review)
        self.detail = Field(readonly=True, multiline=True, height=dp(150))
        self.add_widget(self.detail)
        fit = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.fit_button = Action("Calibrate lens", self.fit)
        self.cancel_button = Action("Cancel calculation", self.cancel)
        fit.add_widget(self.fit_button)
        fit.add_widget(self.cancel_button)
        self.add_widget(fit)
        self.apply_button = Action("Apply fitted lens draft", self.apply)
        self.add_widget(self.apply_button)
        exchange = AdaptiveGrid(max_cols=2, min_width=130, row_height=34, spacing=dp(6))
        self.load_button = Action("Load lens study", self.load)
        self.save_button = Action("Save measured study", self.save)
        exchange.add_widget(self.load_button)
        exchange.add_widget(self.save_button)
        self.add_widget(exchange)
        self.add_widget(label("Lens and target accuracy / exposure synchronization remain unqualified.", 11, MUTED, 40))
        self.refresh()

    def _identity(self):
        return (self.revision, self.distortion_choice.text, self.panel.focal.text, self.panel.lens_distortion)

    def _selected(self) -> int | None:
        if self.study is None or self.capture_choice.text not in self.capture_choice.values:
            return None
        return self.capture_choice.values.index(self.capture_choice.text)

    def _current(self):
        return (
            self.result is not None
            and self.result_identity == self._identity()
            and self.result_owner == self.panel._owner_identity()
        )

    def refresh(self, *_):
        if self.disposed:
            return
        panel = self.panel
        study = self.study
        count = len(study.captures) if study else 0
        self.summary.text = (
            f"{count}/12 captured views · {study.prior.width} × {study.prior.height} px · "
            f"source {study.source_sha256[:12]}\n"
            f"Prior fx {study.prior.fx:.4f} · fy {study.prior.fy:.4f} · "
            f"cx {study.prior.cx:.4f} · cy {study.prior.cy:.4f}"
            if study
            else "No lens study · a lens prior and measured reference are required"
        )
        selected = self._selected()
        if selected is None or study is None:
            self.detail.text = "Add or load measured views. At least three different target tilts are required."
        else:
            capture = study.captures[selected]
            coverage = review_coverage(capture.observations, capture.reference.frame.size)
            lines = [
                f"View {selected + 1} · frame {capture.reference.frame.sequence} · {len(capture.observations)} points",
                f"Image SHA-256 {capture.image_sha256[:16]} · coverage {coverage.image_fraction:.1%}",
            ]
            if self.result is not None:
                if self._current():
                    intrinsic, fits = self.result
                    result = fits[selected]
                    lines.extend(
                        [
                            f"RMS {result.rms_px:.4f} px · max {result.max_px:.4f} px · "
                            f"{len(result.outlier_indices)} outliers above 3 px",
                            f"Fitted fx {intrinsic.fx:.6f} · fy {intrinsic.fy:.6f}",
                            f"Fitted cx {intrinsic.cx:.6f} · cy {intrinsic.cy:.6f}",
                            "Distortion " + " ".join(f"{v:.8g}" for v in intrinsic.distortion),
                            *result.warnings,
                        ]
                    )
                else:
                    lines.append("Inputs or camera owner changed · calibrate again before applying")
            self.detail.text = "\n".join(lines)
        running = panel.running
        for button in (self.add_button, self.prior_button, self.load_button):
            button.disabled = running
        self.distortion_choice.disabled = running
        self.remove_button.disabled = running or selected is None
        self.review_button.disabled = running or selected is None
        self.fit_button.disabled = running or count < 3
        self.cancel_button.disabled = self.cancel_event is None
        self.apply_button.disabled = running or not self._current()
        self.save_button.disabled = running or study is None

    def _set_study(self, study: CameraLensStudy | None):
        self.study = study
        self.revision += 1
        self.result = self.result_identity = self.result_owner = None
        count = len(study.captures) if study else 0
        self.capture_choice.values = tuple(f"View {i + 1}" for i in range(count))
        self.capture_choice.text = f"View {count}" if count else "No views"
        self.refresh()

    def _prior(self):
        panel = self.panel
        if panel.reference is None or panel._lens_reference_mismatch():
            raise ValueError("Capture a reference and verify a lens prior for its source and image size")
        values = [float(v) for v in panel.focal.text.replace(",", " ").split()]
        if len(values) != 4:
            raise ValueError("Enter the intrinsic prior fx fy cx cy in Fit & exchange")
        width, height = panel.reference.frame.size
        fx, fy, cx, cy = values
        return CameraIntrinsics(width, height, fx, fy, cx, cy, panel.lens_distortion)

    def add_reference(self):
        if self.panel.running or self.disposed:
            return
        try:
            reference = self.panel.reference
            if reference is None:
                raise ValueError("Capture and measure a reference image before adding a lens view")
            capture = LensCapture(reference, parse_correspondences(self.panel.points.text, reference.frame.size))
            prior = self.study.prior if self.study else self._prior()
            captures = (*self.study.captures, capture) if self.study else (capture,)
            study = CameraLensStudy(prior, captures, self.distortion_choice.text == "Fit lens distortion")
            self._set_study(study)
            self.panel.reference_for_lens = True
            self.panel._refresh_review()
            self.panel.update_overlay()
            self.panel.note.text = f"View {len(captures)} retained with its exact image and measured points."
        except (ValueError, TypeError) as exc:
            self.panel.note.text = f"View not added: {exc}"

    def use_prior(self):
        if self.panel.running or self.disposed or self.study is None:
            return
        try:
            if self.panel.reference.source_sha256 != self.study.source_sha256:
                raise ValueError("Current reference belongs to another camera source")
            self._set_study(CameraLensStudy(self._prior(), self.study.captures, self.study.fit_distortion))
            self.panel.note.text = "Study prior updated from the current lens draft. Calibrate again."
        except (ValueError, TypeError, AttributeError) as exc:
            self.panel.note.text = f"Prior not updated: {exc}"

    def remove_selected(self):
        index = self._selected()
        study = self.study
        if self.panel.running or self.disposed or index is None or study is None:
            return
        captures = study.captures[:index] + study.captures[index + 1 :]
        self._set_study(CameraLensStudy(study.prior, captures, study.fit_distortion) if captures else None)
        self.panel.note.text = "Selected lens view removed locally; saved studies are unchanged."

    def review_selected(self):
        index = self._selected()
        if self.panel.running or self.disposed or index is None or self.study is None:
            return None
        from carveracontroller.desktop_camera_correspondences import open_camera_correspondences

        capture = self.study.captures[index]
        registration = self.result[1][index].registration if self.result is not None and self._current() else None
        return open_camera_correspondences(capture.reference, capture.observations, registration)

    def fit(self):
        panel = self.panel
        if panel.running or self.disposed or self.study is None:
            return
        try:
            study = CameraLensStudy(
                self.study.prior, self.study.captures, self.distortion_choice.text == "Fit lens distortion"
            )
            if len(study.captures) < 3:
                raise ValueError("Calibrate needs at least three distinctly tilted views")
        except ValueError as exc:
            panel.note.text = str(exc)
            return
        identity, owner = self._identity(), panel._owner_identity()
        event = threading.Event()
        self.cancel_event = event
        panel.running = True
        panel.note.text = "Calibrating lens in the background · Cancel stops refinement cooperatively."
        panel._refresh_review()
        self.refresh()

        def worker():
            result, error = None, None
            try:
                result = calibrate_camera(
                    study.prior,
                    tuple(capture.observations for capture in study.captures),
                    fit_distortion=study.fit_distortion,
                    cancelled=event.is_set,
                )
            except (InterruptedError, ValueError, ArithmeticError) as exc:
                error = str(exc)

            def publish(_dt):
                self.cancel_event = None
                panel.running = False
                if self.disposed:
                    return
                if event.is_set():
                    panel.note.text = "Lens calculation cancelled; captured measurements retained."
                elif identity != self._identity() or owner != panel._owner_identity():
                    panel.note.text = "Lens result withheld: study inputs or camera owner changed during calculation."
                elif error:
                    panel.note.text = f"Lens calculation failed: {error}"
                else:
                    self.result = result
                    self.result_identity, self.result_owner = identity, owner
                    panel.note.text = (
                        "Lens calculation complete. Review each view's residuals before applying the draft."
                    )
                panel._refresh_review()
                self.refresh()

            Clock.schedule_once(publish, 0)

        try:
            threading.Thread(target=worker, name="camera-lens-calibration", daemon=True).start()
        except (RuntimeError, OSError) as exc:
            self.cancel_event = None
            panel.running = False
            panel.note.text = f"Lens worker did not start: {exc}"
            panel._refresh_review()
            self.refresh()

    def cancel(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.panel.note.text = "Cancellation requested · waiting for the owned calculation to stop."

    def dispose(self):
        self.disposed = True
        self.cancel()

    def apply(self):
        panel = self.panel
        if panel.running or self.disposed or self.study is None or self.result is None or not self._current():
            panel.note.text = "Calibrate the current measured study before applying its lens draft."
            return
        reference = panel.reference
        intrinsic = self.result[0]
        if (
            reference is None
            or reference.source_sha256 != self.study.source_sha256
            or reference.frame.size != (intrinsic.width, intrinsic.height)
            or panel.workspace.camera_client.calibration_snapshot()[3] != self.study.source_sha256
        ):
            panel.note.text = (
                "Lens draft not applied: current reference or camera source / size differs from the study."
            )
            return
        if any(c.reference.frame.jpeg == reference.frame.jpeg for c in self.study.captures):
            panel.reference_for_lens = True
        panel.lens_distortion = intrinsic.distortion
        panel.lens_model_size = reference.frame.size
        panel.lens_model_source = reference.source_sha256
        panel.focal.text = " ".join(repr(value) for value in (intrinsic.fx, intrinsic.fy, intrinsic.cx, intrinsic.cy))
        self.result_identity = self._identity()
        panel._refresh_review()
        panel.update_overlay()
        panel.note.text = "Fitted lens draft applied locally. Refit bed registration with a new bed reference and measured bed-frame coordinates."
        self.refresh()

    def load(self):
        if self.panel.running or self.disposed:
            return
        identity, owner = self._identity(), self.panel._owner_identity()

        def selected(path):
            if self.disposed or identity != self._identity() or owner != self.panel._owner_identity():
                self.panel.note.text = "Study or camera owner changed while choosing a file; reopen Load."
                return

            def finish(study):
                if self.disposed or identity != self._identity():
                    return
                self.distortion_choice.text = "Fit lens distortion" if study.fit_distortion else "Keep prior distortion"
                self._set_study(study)
                self.panel.note.text = (
                    "Measured study loaded with exact images. Calibrate before applying; no cached fit trusted."
                )

            self.panel._background(lambda: read_lens_study(path), finish)
            self.refresh()

        self.panel.workspace.choose_profile_file(selected, save=False, extension=".cvlens", title="Load lens study")

    def save(self):
        if self.panel.running or self.disposed or self.study is None:
            return
        identity, owner = self._identity(), self.panel._owner_identity()
        study = CameraLensStudy(
            self.study.prior, self.study.captures, self.distortion_choice.text == "Fit lens distortion"
        )

        def selected(path):
            if self.disposed or identity != self._identity() or owner != self.panel._owner_identity():
                self.panel.note.text = "Study or camera owner changed while choosing a file; reopen Save."
                return

            def finish(digest):
                if not self.disposed:
                    self.panel.note.text = (
                        f"Measured study saved and read back · SHA-256 {digest[:16]} · refit on import."
                    )
                    self.refresh()

            self.panel._background(lambda: write_lens_study(path, study), finish)
            self.refresh()

        self.panel.workspace.choose_profile_file(selected, save=True, extension=".cvlens", title="Save lens study")
