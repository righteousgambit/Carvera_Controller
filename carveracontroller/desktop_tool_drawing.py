"""Responsive dimensioned cutter schematic using the shared procedural profile."""

from dataclasses import replace

from kivy.clock import Clock
from kivy.graphics import Canvas, Color, Line, Mesh
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.tool_visualization.dimension_drawing import assembly_dimensions
from carveracontroller.addons.tool_visualization.mesh_builder import tool_profile
from carveracontroller.desktop_components import ACCENT, AMBER, BG, MUTED, RAISED, TEXT, Action


class ToolDrawing(StencilView):
    selected_dimension = StringProperty("")

    def __init__(self, definition, compact=False, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_dimension_selected")
        self.disposed = False
        self.dimension_buttons = {}
        self.compact = compact
        self.definition = definition
        # StencilView owns canvas.before/after. Clearing those destroys its
        # push/pop balance, particularly when nested inside a ScrollView.
        self.ink = Canvas()
        self.canvas.add(self.ink)
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
        self.radial_label = Label(font_size=dp(12), color=ACCENT, size_hint=(None, None), opacity=0)
        self.add_widget(self.radial_label)
        for caption, key in (
            ("Overall", "length"),
            ("Cutting", "flute_length"),
            ("Stickout", "stickout"),
            ("Diameter", "diameter"),
            ("Shank", "shank_diameter"),
        ):
            button = Action(
                caption, lambda key=key: self.dispatch("on_dimension_selected", key), size_hint=(None, None)
            )
            self.dimension_buttons[key] = button
            self.add_widget(button)
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.trigger, size=self.trigger, selected_dimension=self.trigger)
        self.trigger()

    def update_definition(self, definition):
        # Validate before replacing the drawing; callers can suppress invalid drafts.
        dimensions = assembly_dimensions(definition)
        profile = tool_profile(replace(definition, stickout=None))
        self.definition, self.dimensions, self.profile = definition, dimensions, profile
        for dimension, item in zip(dimensions, self.annotations):
            item.text = dimension.caption
        self.trigger()

    def redraw(self, *_):
        self.ink.clear()
        width = max(1, (self.width - dp(16)) / 5)
        for index, (key, button) in enumerate(self.dimension_buttons.items()):
            button.size = (max(1, width - dp(4)), dp(24))
            button.pos = (self.x + dp(8) + index * width, self.top - dp(26))
            button.disabled = self.disposed
            selected = key == self.selected_dimension
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()
        length = max(z for z, _ in self.profile) or 1
        radius = max(r for _, r in self.profile) or 1
        left, right = self.x + dp(24), self.right - dp(24)
        row = self.height * 0.52 / 4
        middle = self.top - max(dp(90), self.height * 0.34)
        scale = min(max(1, right - left) / length, max(1, self.height * 0.27) / (2 * radius))
        vertices = []
        for z, r in self.profile:
            vertices.extend((left + z * scale, middle - r * scale, 0, 0))
            vertices.extend((left + z * scale, middle + r * scale, 0, 0))
        indices = []
        for i in range(len(self.profile) - 1):
            a = i * 2
            indices.extend((a, a + 1, a + 2, a + 1, a + 3, a + 2))
        with self.ink:
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
            with self.ink:
                Color(*AMBER)
                Line(points=[x, middle - radius * scale - dp(8), x, middle + radius * scale + dp(8)], width=1.3)
            self.collet_label.size = (dp(110), dp(24))
            self.collet_label.pos = (
                min(max(self.x, x - dp(55)), self.right - dp(110)),
                middle + radius * scale + dp(12),
            )
        selected_names = {"length": "Overall", "flute_length": "Cutting length", "stickout": "Stickout"}
        selected_name = selected_names.get(self.selected_dimension)
        for i, (dimension, item) in enumerate(zip(self.dimensions, self.annotations)):
            selected = dimension.name == selected_name
            item.opacity = 1 if not self.compact or selected else 0
            item.color = ACCENT if selected else MUTED
            y = self.y + dp(40) if self.compact else self.y + (4 - i) * row
            item.size = (max(1, self.width - dp(32)), dp(24))
            item.pos = (self.x + dp(16), y - dp(27))
            if dimension.value is None or (self.compact and not selected):
                continue
            a, b = left + dimension.start * scale, left + dimension.end * scale
            with self.ink:
                Color(*(ACCENT if selected else MUTED))
                Line(points=[a, y, b, y], width=1.8 if selected else 1)
                Line(points=[a, y - dp(5), a, y + dp(5)], width=1)
                Line(points=[b, y - dp(5), b, y + dp(5)], width=1)

        self.radial_label.opacity = 0
        if self.selected_dimension in ("diameter", "shank_diameter", "tip_diameter"):
            value = getattr(self.definition, self.selected_dimension)
            name = {"diameter": "Diameter", "shank_diameter": "Shank diameter", "tip_diameter": "Tip diameter"}[
                self.selected_dimension
            ]
            self.radial_label.text = f"{name}: unknown" if value is None else f"{name}: {value:g} mm"
            self.radial_label.size = (max(1, self.width - dp(32)), dp(24))
            self.radial_label.pos = (self.x + dp(16), self.y + dp(13))
            self.radial_label.opacity = 1
            if value is not None:
                z = (self.definition.flute_length or length * 0.25) * 0.5
                if self.selected_dimension == "shank_diameter":
                    z = length * 0.85
                elif self.selected_dimension == "tip_diameter":
                    z = 0
                x, half = left + z * scale, value * scale / 2
                with self.ink:
                    Color(*ACCENT)
                    Line(points=[x, middle - half, x, middle + half], width=1.8)
                    for y in (middle - half, middle + half):
                        Line(points=[x - dp(5), y, x + dp(5), y], width=1.8)
        elif self.selected_dimension == "taper_angle_deg":
            value = self.definition.taper_angle_deg
            self.radial_label.text = "Taper half angle: unknown" if value is None else f"Taper half angle: {value:g}°"
            self.radial_label.size = (max(1, self.width - dp(32)), dp(24))
            self.radial_label.pos = (self.x + dp(16), self.y + dp(13))
            self.radial_label.opacity = 1
        elif self.selected_dimension in ("corner_radius", "thread_pitch"):
            extent = (self.definition.flute_length or length * 0.25) * scale
            with self.ink:
                Color(*ACCENT)
                Line(rectangle=(left, middle - radius * scale, extent, radius * scale * 2), width=1.8)

    def on_dimension_selected(self, key):
        """Select in standalone previews; editors additionally reveal the field."""
        if not self.disposed and key in self.dimension_buttons:
            self.selected_dimension = key

    def dispose(self):
        self.disposed = True
        for button in self.dimension_buttons.values():
            button.disabled = True
        self.trigger.cancel()
