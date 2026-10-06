"""Dimensioned CAD slices calculated off the UI thread from rendered snapshots."""

import threading
import time
from math import floor, log10
from pathlib import Path

from kivy.clock import Clock
from kivy.graphics import Color, Line, Mesh
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    BORDER,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    QuantityField,
    Surface,
    label,
)
from carveracontroller.machine.section_view import SectionCancelled, SectionClip, section_geometry, section_svg


class SectionPlot(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.result = None
        self.mesh = None
        self.meshes = []
        self.scale_bar = None
        self.scale_mm = None
        self.horizontal_axis = label("", 11, height=18, size_hint_x=None, width=dp(70), halign="right")
        self.vertical_axis = label("", 11, height=18, size_hint_x=None, width=dp(70))
        self.scale_caption = label("", 11, height=18, size_hint_x=None, width=dp(110))
        for caption in (self.horizontal_axis, self.vertical_axis, self.scale_caption):
            caption.text_size = caption.size
            self.add_widget(caption)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        result = self.result
        # Height dispatch can invoke redraw recursively. Settle it before
        # clearing instructions so an outer redraw cannot append duplicate batches.
        self.height = dp(250) if result and result.bounds else 0
        self.canvas.before.clear()
        self.mesh = None
        self.meshes = []
        self.scale_bar = self.scale_mm = None
        for caption in (self.horizontal_axis, self.vertical_axis, self.scale_caption):
            caption.text = ""
        if not result or not result.bounds:
            return
        (u0, u1), (v0, v1) = result.bounds
        margin = dp(28)
        scale = min(
            max(1, self.width - 2 * margin) / max(u1 - u0, 1e-6), max(1, self.height - 2 * margin) / max(v1 - v0, 1e-6)
        )
        # Property callbacks may precede cached center alias invalidation.
        # Derive the center from the dimensions supplied to this redraw.
        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        horizontal, vertical = result.captions
        self.horizontal_axis.text = f"{horizontal} right"
        self.horizontal_axis.pos = (self.right - dp(78), self.y + dp(2))
        self.vertical_axis.text = f"{vertical} up"
        self.vertical_axis.pos = (self.x + dp(6), self.top - dp(22))
        target_mm = min(dp(80), max(dp(10), self.width / 3)) / scale
        magnitude = 10 ** floor(log10(target_mm))
        self.scale_mm = max(value * magnitude for value in (1, 2, 5, 10) if value * magnitude <= target_mm)
        self.scale_caption.text = f"{self.scale_mm:g} mm"
        self.scale_caption.width = max(0, min(dp(110), self.width - dp(92)))
        self.scale_caption.pos = (self.x + dp(8), self.y + dp(1))
        bar_x, bar_y = self.x + dp(8), self.y + dp(23)
        vertices = []
        for segment in result.segments:
            for point in segment:
                u, v = result.project(point)
                vertices.extend((cx + (u - (u0 + u1) / 2) * scale, cy + (v - (v0 + v1) / 2) * scale, 0, 0))
        with self.canvas.before:
            Color(*BORDER)
            Line(rectangle=(self.x + margin, self.y + margin, self.width - 2 * margin, self.height - 2 * margin))
            Color(*ACCENT)
            self.scale_bar = Line(points=(bar_x, bar_y, bar_x + self.scale_mm * scale, bar_y), width=1)
            Line(points=(bar_x, bar_y - dp(3), bar_x, bar_y + dp(3)), width=1)
            Line(
                points=(bar_x + self.scale_mm * scale, bar_y - dp(3), bar_x + self.scale_mm * scale, bar_y + dp(3)),
                width=1,
            )
            # Kivy uses 16-bit mesh indices. Preserve every segment by batching
            # rather than wrapping indices or dropping dense plate contours.
            for start in range(0, len(vertices), 64000 * 4):
                batch = vertices[start : start + 64000 * 4]
                self.meshes.append(Mesh(vertices=batch, indices=list(range(len(batch) // 4)), mode="lines"))
            self.mesh = self.meshes[0]


class SectionPanel(Surface):
    def __init__(self, inspector, text_factory, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.inspector = inspector
        self.snapshot = ()
        self.selection = None
        self.generation = 0
        self.cancel_event = None
        self.running = False
        self.export_running = False
        self._restoring_cutaway = False
        self.heading = label("Dimensioned section", 13, height=26, bold=True)
        self.add_widget(self.heading)
        self.note = text_factory(
            "Choose a plane through the selected component. CAD dimensions in mm; placement is a draft."
        )
        self.add_widget(self.note)
        self.coordinate_caption = label("Plane position · mm", 11, height=22)
        self.add_widget(self.coordinate_caption)
        row = self.coordinate_row = AdaptiveGrid(max_cols=2, min_width=240, row_height=54, spacing=dp(5))
        self.axis = Choice(text="Z", values=("X", "Y", "Z"))
        self.coordinate = QuantityField(
            text="0", hint_text="Plane position · mm", kind="length", minimum=-1e7, maximum=1e7
        )
        self.axis.bind(text=self._axis_changed)
        self.coordinate.input.bind(on_text_validate=lambda *_: self.calculate())
        row.add_widget(self.axis)
        row.add_widget(self.coordinate)
        self.center_action = Action("Midplane", self.center_plane)
        self.add_widget(row)
        self.alignment = Choice(text="Axis plane", values=("Axis plane", "Custom normal"))
        self.add_widget(self.alignment)
        normal_row = self.normal_row = AdaptiveGrid(max_cols=3, min_width=80, row_height=60, spacing=dp(5))
        self.normal_fields = []
        for axis, value in zip("XYZ", ("0", "0", "1")):
            cell = BoxLayout(orientation="vertical", spacing=dp(2))
            cell.add_widget(label(f"Normal {axis}", 11, height=20))
            field = Field(text=value, hint_text=axis, multiline=False, disabled=True)
            self.normal_fields.append(field)
            cell.add_widget(field)
            normal_row.add_widget(cell)
            field.bind(text=self._plane_changed)
        self.alignment.bind(text=self._alignment_changed)
        self.cutaway = Choice(text="Full component", values=("Full component", "Keep below plane", "Keep above plane"))
        self.cutaway.bind(text=self._cutaway_changed)
        self.cutaway.size_hint_y = None
        self.cutaway.height = dp(34)
        self.add_widget(self.cutaway)
        self.cutaway_note = text_factory("Cutaway changes the 3D view only; the CAD slice and setup remain intact.")
        self.add_widget(self.cutaway_note)
        actions = AdaptiveGrid(max_cols=4, min_width=100, row_height=34, spacing=dp(5))
        self.calculate_action = Action("Calculate section", self.calculate)
        self.export_action = Action("Export SVG…", self.export, disabled=True)
        self.cancel_action = Action("Cancel", self.cancel, disabled=True)
        self.face_action = Action("Use picked face", self.use_picked_face)
        actions.add_widget(self.face_action)
        actions.add_widget(self.center_action)
        actions.add_widget(self.calculate_action)
        actions.add_widget(self.export_action)
        actions.add_widget(self.cancel_action)
        self.add_widget(actions)
        self.export_status = text_factory()
        self.add_widget(self.export_status)
        self.dimensions = text_factory()
        self.add_widget(self.dimensions)
        self.plot = SectionPlot()
        self.add_widget(self.plot)
        self.coordinate.bind(text=self._plane_changed)

    def _alignment_changed(self, *_):
        custom = self.alignment.text == "Custom normal"
        if custom and self.normal_row.parent is None:
            self.add_widget(self.normal_row, index=self.children.index(self.alignment))
        elif not custom and self.normal_row.parent is self:
            self.remove_widget(self.normal_row)
        for field in self.normal_fields:
            field.disabled = self.alignment.text == "Axis plane"
        self.axis.disabled = self.alignment.text != "Axis plane"
        self.coordinate_caption.text = (
            "Signed normal distance · mm" if self.alignment.text == "Custom normal" else "Plane position · mm"
        )
        self.coordinate.hint_text = self.coordinate_caption.text
        self._plane_changed()

    def plane(self, coordinate_mm=None):
        normal = None
        if self.alignment.text == "Custom normal":
            normal = tuple(float(field.text) for field in self.normal_fields)
        return SectionClip(
            "XYZ".index(self.axis.text),
            self.coordinate.value() if coordinate_mm is None else coordinate_mm,
            normal=normal,
        )

    def use_picked_face(self):
        if self.running:
            return
        hit = self.inspector.workspace.scene_interaction.selected_surface()
        if hit is None or hit.component != self.selection:
            self.note.text = "Pick a current rendered face on this component first."
            return
        # Capture the nominal pre-motion point/normal, not live placement or a
        # measured datum. Guard callbacks while replacing the whole plane.
        self._restoring_cutaway = True
        try:
            for field, value in zip(self.normal_fields, hit.normal):
                field.text = f"{value:.12g}"
            self.alignment.text = "Custom normal"
            self.coordinate.text = f"{sum(a * b for a, b in zip(hit.component_point_mm, hit.normal)):.12g}"
        finally:
            self._restoring_cutaway = False
        self._plane_changed()
        self.note.text = "Plane aligned to picked CAD face; nominal geometry, physical placement unverified."

    def _plane_changed(self, *_):
        self._cutaway_changed()
        if self.plot.result:
            self.plot.result = None
            self.plot.redraw()
            self.dimensions.text = ""
            self.note.text = "Plane changed; calculate the new section."
            self.export_action.disabled = True
            self.export_status.text = ""
        if not self._restoring_cutaway and not self.running and self.snapshot:
            try:
                self.plane()
            except (ValueError, TypeError) as exc:
                self.note.text = f"Invalid section plane: {exc}"
            else:
                self.note.text = "Plane changed; calculate the new section."

    def _cutaway_changed(self, *_):
        if self.selection is None or self._restoring_cutaway:
            return
        if not self.snapshot:
            self.cutaway_note.text = "Cutaway unavailable until this component has rendered CAD geometry."
            return
        viewer = self.inspector.workspace.machine.gcode_viewer
        try:
            plane = self.plane() if self.cutaway.text != "Full component" else None
            clip = (
                SectionClip(plane.axis, plane.coordinate_mm, self.cutaway.text == "Keep above plane", plane.normal)
                if plane
                else None
            )
            viewer.set_component_cutaway(self.selection, clip)
        except (ValueError, TypeError) as exc:
            if self.selection != "cutter":
                viewer.set_component_cutaway(self.selection, None)
            self.cutaway_note.text = f"Cutaway withheld: {exc}. Full component is shown."
            return
        self.cutaway_note.text = (
            f"{'Custom normal' if clip.normal else 'XYZ'[clip.axis]} · distance {clip.coordinate_mm:g} mm · nominal CAD; open cut, no cap."
            + (" Below/above follows the negative/positive normal direction." if clip.normal else "")
            if clip
            else "Full component shown. The CAD slice and setup remain intact."
        )

    def _axis_changed(self, *_):
        self.center_plane()
        self._plane_changed()

    def refresh(self):
        viewer = self.inspector.workspace.machine.gcode_viewer
        selection = self.inspector.selected
        snapshot = viewer.inspected_component_geometry(selection)
        if selection == self.selection and snapshot == self.snapshot:
            return
        self.generation += 1
        self.cancel()
        self.snapshot, self.selection = snapshot, selection
        self.plot.result = None
        self.plot.redraw()
        self.export_action.disabled = True
        self.export_status.text = ""
        self.dimensions.text = ""
        self.note.text = (
            "Select Calculate section to slice the current CAD snapshot."
            if snapshot
            else "No rendered triangle geometry for this component."
        )
        self.calculate_action.disabled = self.running or not snapshot
        self.cutaway.disabled = not snapshot
        clip = viewer.component_cutaways.get(selection)
        self._restoring_cutaway = True
        try:
            if clip:
                for field, value in zip(self.normal_fields, clip.normal or (0, 0, 1)):
                    field.text = f"{value:.12g}"
                self.alignment.text = "Custom normal" if clip.normal else "Axis plane"
                self.axis.text = "XYZ"[clip.axis]
                self.coordinate.text = f"{clip.coordinate_mm:g}"
                self.cutaway.text = "Keep above plane" if clip.keep_above else "Keep below plane"
            else:
                self.alignment.text = "Axis plane"
                self.cutaway.text = "Full component"
                self.center_plane()
        finally:
            self._restoring_cutaway = False
        self._cutaway_changed()

    def center_plane(self):
        bounds = self.inspector.workspace.machine.gcode_viewer.inspected_component_bounds(self.inspector.selected)
        if bounds:
            try:
                plane = self.plane(0)
                center = tuple((bounds[0][i] + bounds[1][i]) / 2 for i in range(3))
                self.coordinate.text = f"{sum(a * b for a, b in zip(center, plane.direction)):.6g}"
            except (ValueError, TypeError):
                self.note.text = "Enter a valid plane normal before choosing Midplane."

    def cancel(self):
        if self.cancel_event:
            self.cancel_event.set()

    def _reveal_result(self, result):
        from carveracontroller.desktop_scroll_navigation import queue_reveal

        generation = self.generation
        queue_reveal(
            self.heading,
            active=lambda: (
                generation == self.generation
                and self.plot.result is result
                and self.inspector.workspace.active_section == "Scene"
            ),
            align_top=True,
        )

    def export(self):
        result = self.plot.result
        if self.export_running or self.running or result is None or not result.bounds:
            return
        from carveracontroller.machine.scene_inspection import COMPONENT_TITLES

        title = COMPONENT_TITLES[self.selection]

        def save(path):
            if self.plot.result is not result or self.running:
                self.export_status.text = "Section changed; export the newly calculated section."
                return
            self.export_running = True
            self.export_action.disabled = True
            self.export_status.text = "Exporting captured section drawing…"

            def run():
                error = None
                temporary = None
                try:
                    # Large plate contours are encoded/written off the UI thread.
                    from tempfile import NamedTemporaryFile

                    target = Path(path)
                    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        stream.write(section_svg(result, title))
                    temporary.replace(target)
                except (OSError, ValueError, TypeError) as exc:
                    error = exc
                except Exception as exc:
                    Logger.exception("Section: drawing export worker failed")
                    error = RuntimeError(f"Unexpected export failure ({type(exc).__name__}); see controller log.")
                finally:
                    if temporary is not None:
                        try:
                            temporary.unlink(missing_ok=True)
                        except OSError as exc:
                            Logger.exception("Section: temporary drawing cleanup failed")
                            if error is None:
                                error = exc
                Clock.schedule_once(lambda _dt: finish(error), 0)

            def finish(error):
                self.export_running = False
                self.export_action.disabled = self.running or self.plot.result is None or not self.plot.result.bounds
                if self.plot.result is result:
                    self.export_status.text = (
                        f"Drawing export failed: {error}" if error else f"Saved {title} section: {Path(path).name}"
                    )
                    self._reveal_result(result)

            threading.Thread(target=run, daemon=True).start()

        self.inspector.workspace.choose_profile_file(
            save, save=True, extension=".svg", title="Export captured section drawing"
        )

    def calculate(self):
        if self.running or not self.snapshot:
            return
        try:
            plane = self.plane()
        except (ValueError, TypeError) as exc:
            self.note.text = f"Invalid section plane: {exc}"
            return
        axis, coordinate = plane.axis, plane.coordinate_mm
        generation, snapshot = self.generation, self.snapshot
        self.running = True
        event = self.cancel_event = threading.Event()
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.axis.disabled = self.coordinate.disabled = self.center_action.disabled = True
        self.alignment.disabled = self.face_action.disabled = True
        for field in self.normal_fields:
            field.disabled = True
        self.plot.result = None
        self.plot.redraw()
        self.export_action.disabled = True
        self.export_status.text = ""
        self.dimensions.text = ""
        self.note.text = "Calculating triangle intersections…"

        def run():
            result, error = None, None
            last = 0

            def progress(count):
                nonlocal last
                if time.monotonic() - last > 0.15:
                    last = time.monotonic()
                    Clock.schedule_once(lambda _dt: update(count), 0)

            try:
                result = section_geometry(
                    snapshot, axis, coordinate, normal=plane.normal, cancelled=event.is_set, progress=progress
                )
            except (ValueError, TypeError, OverflowError) as exc:
                error = exc
            except Exception as exc:
                # Unexpected worker failures must release disabled controls and
                # withhold results too; retain diagnostics in the controller log.
                Logger.exception("Section: CAD calculation worker failed")
                error = RuntimeError(f"Section calculation failed ({type(exc).__name__}); see controller log.")
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def update(count):
            if generation == self.generation and self.running and event is self.cancel_event:
                self.note.text = f"Intersecting CAD · {count:,} triangles checked…"

        def finish(result, error):
            self.running = False
            self.coordinate.disabled = self.center_action.disabled = False
            self.alignment.disabled = self.face_action.disabled = False
            self.axis.disabled = self.alignment.text != "Axis plane"
            for field in self.normal_fields:
                field.disabled = self.alignment.text == "Axis plane"
            self.cancel_action.disabled = True
            self.calculate_action.disabled = not self.snapshot
            self.refresh()
            if generation != self.generation:
                return
            try:
                unchanged_plane = self.plane() == plane
            except (ValueError, TypeError):
                unchanged_plane = False
            if not unchanged_plane:
                self.note.text = "Plane changed; calculate the new section."
                return
            if event.is_set() or error:
                self.note.text = (
                    "Cancelled; no section applied."
                    if event.is_set() or isinstance(error, SectionCancelled)
                    else str(error)
                )
                return
            self.plot.result = result
            self.plot.redraw()
            self.export_action.disabled = self.export_running or not result.bounds
            self.note.text = f"{result.plane_label} · {result.triangle_count:,} CAD triangles · {len(result.segments):,} intersection segments"
            self.dimensions.text = (
                (
                    "\n".join(
                        f"{caption}: {low:.3f} to {high:.3f} mm · span {high - low:.3f} mm"
                        for caption, (low, high) in zip(result.captions, result.bounds)
                    )
                    if result.bounds
                    else "Plane does not intersect this component."
                )
                + "\nHorizontal / vertical axes: "
                + " / ".join(result.captions)
                + "\nNominal CAD frame before live joint transforms. Open meshes remain open; no solid area or measured clearance inferred."
            )
            self._reveal_result(result)

        threading.Thread(target=run, daemon=True).start()
