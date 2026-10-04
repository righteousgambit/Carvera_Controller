"""Dimensioned CAD slices calculated off the UI thread from rendered snapshots."""

import threading
import time

from kivy.clock import Clock
from kivy.graphics import Color, Line, Mesh
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import ACCENT, BORDER, Action, Choice, Field, Surface, label
from carveracontroller.machine.section_view import SectionCancelled, section_geometry


class SectionPlot(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.result = None
        self.mesh = None
        self.meshes = []
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        result = self.result
        # Height dispatch can invoke redraw recursively. Settle it before
        # clearing instructions so an outer redraw cannot append duplicate batches.
        self.height = dp(250) if result and result.bounds else 0
        self.canvas.clear()
        self.mesh = None
        self.meshes = []
        if not result or not result.bounds:
            return
        (u0, u1), (v0, v1) = result.bounds
        margin = dp(20)
        scale = min(
            max(1, self.width - 2 * margin) / max(u1 - u0, 1e-6), max(1, self.height - 2 * margin) / max(v1 - v0, 1e-6)
        )
        # Property callbacks may precede cached center alias invalidation.
        # Derive the center from the dimensions supplied to this redraw.
        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        vertices = []
        for segment in result.segments:
            for point in segment:
                u, v = (point[i] for i in result.axes)
                vertices.extend((cx + (u - (u0 + u1) / 2) * scale, cy + (v - (v0 + v1) / 2) * scale, 0, 0))
        with self.canvas:
            Color(*BORDER)
            Line(rectangle=(self.x + margin, self.y + margin, self.width - 2 * margin, self.height - 2 * margin))
            Color(*ACCENT)
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
        self.add_widget(label("Dimensioned section", 13, height=26, bold=True))
        self.note = text_factory(
            "Choose a plane through the selected component. CAD dimensions in mm; placement is a draft."
        )
        self.add_widget(self.note)
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
        self.axis = Choice(text="Z", values=("X", "Y", "Z"), size_hint_x=None, width=dp(65))
        self.coordinate = Field(text="0", hint_text="Plane position · mm", multiline=False)
        self.axis.bind(text=self._axis_changed)
        self.coordinate.bind(on_text_validate=lambda *_: self.calculate())
        row.add_widget(self.axis)
        row.add_widget(self.coordinate)
        self.center_action = Action("Midplane", self.center_plane, size_hint_x=None, width=dp(90))
        row.add_widget(self.center_action)
        self.add_widget(row)
        actions = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(5))
        self.calculate_action = Action("Calculate section", self.calculate)
        self.cancel_action = Action("Cancel", self.cancel, disabled=True, size_hint_x=None, width=dp(75))
        actions.add_widget(self.calculate_action)
        actions.add_widget(self.cancel_action)
        self.add_widget(actions)
        self.dimensions = text_factory()
        self.add_widget(self.dimensions)
        self.plot = SectionPlot()
        self.add_widget(self.plot)
        self.coordinate.bind(text=self._plane_changed)

    def _plane_changed(self, *_):
        if self.plot.result:
            self.plot.result = None
            self.plot.redraw()
            self.dimensions.text = ""
            self.note.text = "Plane changed; calculate the new section."

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
        self.dimensions.text = ""
        self.note.text = (
            "Select Calculate section to slice the current CAD snapshot."
            if snapshot
            else "No rendered triangle geometry for this component."
        )
        self.calculate_action.disabled = self.running or not snapshot
        self.center_plane()

    def center_plane(self):
        bounds = self.inspector.workspace.machine.gcode_viewer.inspected_component_bounds(self.inspector.selected)
        if bounds:
            axis = "XYZ".index(self.axis.text)
            self.coordinate.text = f"{(bounds[0][axis] + bounds[1][axis]) / 2:.6g}"

    def cancel(self):
        if self.cancel_event:
            self.cancel_event.set()

    def calculate(self):
        if self.running or not self.snapshot:
            return
        try:
            coordinate = float(self.coordinate.text)
            from math import isfinite

            if not isfinite(coordinate):
                raise ValueError()
        except ValueError:
            self.note.text = "Enter a finite plane position in millimeters."
            return
        axis = "XYZ".index(self.axis.text)
        generation, snapshot = self.generation, self.snapshot
        self.running = True
        event = self.cancel_event = threading.Event()
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.axis.disabled = self.coordinate.disabled = self.center_action.disabled = True
        self.plot.result = None
        self.plot.redraw()
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
                result = section_geometry(snapshot, axis, coordinate, cancelled=event.is_set, progress=progress)
            except (ValueError, TypeError, OverflowError) as exc:
                error = exc
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def update(count):
            if generation == self.generation and self.running:
                self.note.text = f"Intersecting CAD · {count:,} triangles checked…"

        def finish(result, error):
            self.running = False
            self.axis.disabled = self.coordinate.disabled = self.center_action.disabled = False
            self.cancel_action.disabled = True
            self.calculate_action.disabled = not self.snapshot
            self.refresh()
            if generation != self.generation:
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
            self.note.text = f"{'XYZ'[axis]} = {coordinate:g} mm · {result.triangle_count:,} CAD triangles · {len(result.segments):,} intersection segments"
            self.dimensions.text = (
                (
                    "\n".join(
                        f"{'XYZ'[i]}: {low:.3f} to {high:.3f} mm · span {high - low:.3f} mm"
                        for i, (low, high) in zip(result.axes, result.bounds)
                    )
                    if result.bounds
                    else "Plane does not intersect this component."
                )
                + "\nHorizontal / vertical axes: "
                + " / ".join("XYZ"[i] for i in result.axes)
                + "\nNominal CAD frame before live joint transforms. Open meshes remain open; no solid area or measured clearance inferred."
            )

        threading.Thread(target=run, daemon=True).start()
