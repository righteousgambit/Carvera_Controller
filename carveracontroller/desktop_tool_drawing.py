"""Responsive dimensioned cutter schematic using the shared procedural profile."""

from dataclasses import replace

from kivy.clock import Clock
from kivy.graphics import Color, Line, Mesh
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.tool_visualization.dimension_drawing import assembly_dimensions
from carveracontroller.addons.tool_visualization.mesh_builder import tool_profile
from carveracontroller.desktop_components import AMBER, MUTED


class ToolDrawing(StencilView):
    def __init__(self, definition, **kwargs):
        super().__init__(**kwargs)
        self.definition = definition
        self.dimensions = assembly_dimensions(definition)
        # Show the complete cutter, including the inserted portion. This schematic
        # uses nominal dimensions; it never pretends to be the manufacturer's CAD.
        self.profile = tool_profile(replace(definition, stickout=None))
        self.annotations = []
        for dimension in self.dimensions:
            item = Label(text=dimension.caption, font_size=dp(12), color=MUTED, size_hint=(None, None))
            self.annotations.append(item)
            self.add_widget(item)
        self.collet_label = Label(text="Collet face", font_size=dp(11), color=AMBER, size_hint=(None, None))
        self.add_widget(self.collet_label)
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.trigger, size=self.trigger)
        self.trigger()

    def redraw(self, *_):
        self.canvas.before.clear()
        length = max(z for z, _ in self.profile) or 1
        radius = max(r for _, r in self.profile) or 1
        left, right = self.x + dp(24), self.right - dp(24)
        row = self.height * 0.52 / 4
        middle = self.top - max(dp(58), self.height * 0.22)
        scale = min(max(1, right - left) / length, max(1, self.height * 0.27) / (2 * radius))
        vertices = []
        for z, r in self.profile:
            vertices.extend((left + z * scale, middle - r * scale, 0, 0))
            vertices.extend((left + z * scale, middle + r * scale, 0, 0))
        indices = []
        for i in range(len(self.profile) - 1):
            a = i * 2
            indices.extend((a, a + 1, a + 2, a + 1, a + 3, a + 2))
        with self.canvas.before:
            Color(0.48, 0.53, 0.58, 0.75)
            Mesh(vertices=vertices, indices=indices, mode="triangles")
            Color(*MUTED)
            Line(
                points=[left - dp(8), middle, left + length * scale + dp(8), middle],
                dash_length=dp(5),
                dash_offset=dp(4),
            )
        stickout = self.definition.stickout
        self.collet_label.opacity = 1 if stickout is not None else 0
        if stickout is not None:
            x = left + stickout * scale
            with self.canvas.before:
                Color(*AMBER)
                Line(points=[x, middle - radius * scale - dp(8), x, middle + radius * scale + dp(8)], width=1.3)
            self.collet_label.size = (dp(110), dp(24))
            self.collet_label.pos = (
                min(max(self.x, x - dp(55)), self.right - dp(110)),
                middle + radius * scale + dp(12),
            )
        for i, (dimension, item) in enumerate(zip(self.dimensions, self.annotations)):
            y = self.y + (4 - i) * row
            item.size = (max(1, self.width - dp(32)), dp(24))
            item.pos = (self.x + dp(16), y - dp(27))
            if dimension.value is None:
                continue
            a, b = left + dimension.start * scale, left + dimension.end * scale
            with self.canvas.before:
                Color(*MUTED)
                Line(points=[a, y, b, y], width=1)
                Line(points=[a, y - dp(5), a, y + dp(5)], width=1)
                Line(points=[b, y - dp(5), b, y + dp(5)], width=1)

    def dispose(self):
        self.trigger.cancel()
