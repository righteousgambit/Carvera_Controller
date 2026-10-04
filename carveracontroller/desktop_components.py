"""Shared desktop surfaces, inputs and responsive layout primitives."""

import math

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput

from carveracontroller.machine.quantities import CANONICAL, QuantityError, format_quantity, parse_quantity

BG = (0.045, 0.055, 0.075, 1)
PANEL = (0.075, 0.090, 0.118, 1)
RAISED = (0.115, 0.135, 0.172, 1)
TEXT = (0.91, 0.94, 0.98, 1)
MUTED = (0.57, 0.65, 0.75, 1)
ACCENT = (0.27, 0.80, 0.73, 1)
DANGER = (0.77, 0.22, 0.29, 1)
AMBER = (0.98, 0.72, 0.32, 1)
BORDER = (0.16, 0.19, 0.24, 1)


class DesktopScrollView(ScrollView):
    """Desktop content scrolling with an operable, visible drag target."""

    def __init__(self, **kwargs):
        kwargs.setdefault("scroll_type", ["content", "bars"])
        kwargs.setdefault("bar_width", dp(9))
        kwargs.setdefault("bar_color", MUTED)
        kwargs.setdefault("bar_inactive_color", (*MUTED[:3], 0.35))
        kwargs.setdefault("always_overscroll", False)
        super().__init__(**kwargs)

    def on_scroll_start(self, touch, check_children=True):
        # Kivy visits nested scroll views before testing this viewport. A
        # scrolled-out child can otherwise capture a sibling toolbar click.
        if not self.collide_point(*touch.pos):
            touch.ud[self._get_uid("svavoid")] = True
            return False
        return super().on_scroll_start(touch, check_children)


class Surface(BoxLayout):
    def __init__(self, color=PANEL, radius=10, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*color)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
            Color(*BORDER)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, dp(radius)), width=0.65)
        self._radius = dp(radius)
        self.bind(pos=self._update_shape, size=self._update_shape)

    def _update_shape(self, *_):
        self._shape.pos, self._shape.size = self.pos, self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, self._radius)


def label(text, size=14, color=TEXT, height=26, **kwargs):
    kwargs.setdefault("halign", "left")
    item = Label(
        text=text,
        font_name="Roboto",
        font_size=sp(size),
        color=color,
        size_hint_y=None,
        height=dp(height),
        valign="middle",
        **kwargs,
    )
    item.bind(size=lambda obj, value: setattr(obj, "text_size", value))
    return item


class Action(Button):
    hovered = BooleanProperty(False)

    def __init__(self, text, action=None, primary=False, danger=False, **kwargs):
        self.base_color = DANGER if danger else ACCENT if primary else RAISED
        kwargs.setdefault("height", dp(36))
        super().__init__(
            text=text,
            font_name="Roboto",
            font_size=sp(12),
            background_normal="",
            background_down="",
            background_disabled_normal="",
            background_color=(0, 0, 0, 0),
            color=BG if primary else TEXT,
            disabled_color=MUTED,
            size_hint_y=None,
            **kwargs,
        )
        with self.canvas.before:
            self._fill = Color(*self.base_color)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        self.bind(pos=self._paint, size=self._paint, state=self._paint, disabled=self._paint, hovered=self._paint)
        if action:
            self.bind(on_release=lambda _: action())

    def _paint(self, *_):
        factor = 0.48 if self.disabled else 0.85 if self.state == "down" else 1.13 if self.hovered else 1
        self._fill.rgba = tuple(c * factor for c in self.base_color[:3]) + (1,)
        self._shape.pos, self._shape.size = self.pos, self.size


class Field(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_size", sp(13))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(38))
        kwargs.setdefault("padding", (dp(10), dp(9)))
        super().__init__(**kwargs)
        self.background_normal = self.background_active = ""
        self.background_color = (0, 0, 0, 0)
        self.foreground_color, self.cursor_color = TEXT, ACCENT
        self.hint_text_color = MUTED
        with self.canvas.before:
            Color(*BG)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            self._border_color = Color(*BORDER)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, dp(6)), width=1)
            # TextInput glyph textures inherit the current canvas tint.
            Color(1, 1, 1, 1)
        self.bind(pos=self._paint, size=self._paint, focus=self._paint)

    def _paint(self, *_):
        self._shape.pos, self._shape.size = self.pos, self.size
        self._border_color.rgba = ACCENT if self.focus else BORDER
        self._border.rounded_rectangle = (*self.pos, *self.size, dp(6))


class QuantityField(FloatLayout):
    """Editable expression plus a live canonical interpretation; never applies it."""

    text = StringProperty("")
    hint_text = StringProperty("")
    focus = BooleanProperty(False)

    def __init__(self, kind="length", minimum=None, maximum=None, integer=False, optional=False, step=None, **kwargs):
        self.kind, self.minimum, self.maximum = kind, minimum, maximum
        self.integer, self.optional = integer, optional
        self.step = step if step is not None else {"length": 0.1, "feed": 10, "angle": 1, "rpm": 100, "scalar": 1}[kind]
        self.error = ""
        self.interpretation = None
        self.step_buttons = []
        kwargs.setdefault("height", dp(54))
        kwargs.setdefault("size_hint_y", None)
        initial_text = kwargs.pop("text", "")
        super().__init__(**kwargs)
        self.input = Field(text=initial_text, size_hint=(None, None), padding=(dp(10), dp(7), dp(62), dp(23)))
        self.input.hint_text = self.hint_text
        self.bind(hint_text=lambda _, text: setattr(self.input, "hint_text", text))
        self.add_widget(self.input)
        self.text = initial_text
        self.input.bind(text=lambda _, text: setattr(self, "text", text))
        self.bind(text=lambda _, text: setattr(self.input, "text", text))
        self.input.bind(focus=lambda _, value: setattr(self, "focus", value))
        self.bind(focus=lambda _, value: setattr(self.input, "focus", value))
        self.bind(focus=self._paint)
        self.interpretation = label("", 9, MUTED, 16, size_hint_x=None, shorten=True, shorten_from="right")
        # The editor owns its redraw canvas; feedback and buttons are siblings.
        self.add_widget(self.interpretation, canvas="after")
        for direction, title in ((-1, "−"), (1, "+")):
            button = Action(
                title, lambda direction=direction: self.adjust(direction), size_hint_x=None, width=dp(22), height=dp(22)
            )
            self.step_buttons.append(button)
            self.add_widget(button, canvas="after")
        self.bind(text=self._interpret, pos=self._position_interpretation, size=self._position_interpretation)
        self._position_interpretation()
        self._interpret()

    def value(self):
        if self.optional and not self.text.strip():
            return None
        return parse_quantity(self.text, self.kind, minimum=self.minimum, maximum=self.maximum, integer=self.integer)

    def _interpret(self, *_):
        try:
            value = self.value()
            self.error = ""
            self.interpretation.text = (
                "Optional · no value" if value is None else "= " + format_quantity(value, self.kind)
            )
            self.interpretation.color = MUTED
        except QuantityError as exc:
            self.error = str(exc)
            self.interpretation.text = self.error
            self.interpretation.color = DANGER
        self._paint()

    def _position_interpretation(self, *_):
        self.input.pos, self.input.size = self.pos, self.size
        self.interpretation.pos = (self.x + dp(10), self.y + dp(2))
        self.interpretation.width = max(1, self.width - dp(20))
        for index, button in enumerate(self.step_buttons):
            button.pos = (self.x + self.width - dp(54 - index * 26), self.y + dp(27))

    def adjust(self, direction):
        """An explicit draft edit, in displayed canonical units, without dispatch."""
        try:
            current = self.value()
            if current is None:
                raise QuantityError("Enter a starting value before adjusting")
            candidate = current + self.step * direction
            expression = f"{candidate:.12g} {CANONICAL[self.kind]}".strip()
            parse_quantity(expression, self.kind, minimum=self.minimum, maximum=self.maximum, integer=self.integer)
            self.text = expression
        except QuantityError as exc:
            self.error = str(exc)
            self.interpretation.text, self.interpretation.color = self.error, DANGER
            self._paint()

    def _paint(self, *_):
        self.input._paint()
        if self.error:
            self.input._border_color.rgba = DANGER


class ChoiceOption(SpinnerOption):
    """Readable desktop menu rows, including long names at narrow widths."""

    def __init__(self, **kwargs):
        kwargs.setdefault("font_size", sp(12))
        super().__init__(**kwargs)
        self.background_normal = self.background_down = ""
        self.background_color = RAISED
        self.color = TEXT
        self.halign = "left"
        self.valign = "middle"
        self.padding = (dp(10), dp(8))
        self.bind(width=self._wrap, texture_size=self._fit_height)
        self._wrap()

    def _wrap(self, *_):
        self.text_size = (max(dp(1), self.width - dp(20)), None)

    def _fit_height(self, *_):
        self.height = max(dp(36), self.texture_size[1] + dp(16))


class Choice(Spinner):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(36))
        kwargs.setdefault("font_size", sp(12))
        kwargs.setdefault("option_cls", ChoiceOption)
        super().__init__(**kwargs)
        self.background_normal = self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT
        self.shorten = True
        self.shorten_from = "right"
        with self.canvas.before:
            Color(*RAISED)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            Color(*BORDER)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, dp(6)), width=0.7)
            Color(1, 1, 1, 1)
        self.bind(pos=self._paint, size=self._paint)

    def _paint(self, *_):
        self._shape.pos, self._shape.size = self.pos, self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, dp(6))
        self.text_size = (max(0, self.width - dp(20)), self.height)
        self.valign = "middle"


class AdaptiveGrid(GridLayout):
    """Equal-height cards that stack instead of squeezing their controls."""

    def __init__(self, max_cols=2, min_width=360, row_height=240, **kwargs):
        self.max_cols, self.min_width, self.row_height = max_cols, dp(min_width), dp(row_height)
        kwargs.setdefault("spacing", dp(12))
        super().__init__(cols=max_cols, size_hint_y=None, **kwargs)
        self.bind(width=self._reflow, children=self._reflow)
        self._reflow()

    def _reflow(self, *_):
        gap = self.spacing[0]
        self.cols = max(1, min(self.max_cols, int((self.width + gap) / (self.min_width + gap))))
        rows = math.ceil(len(self.children) / self.cols)
        self.height = rows * self.row_height + max(0, rows - 1) * self.spacing[1]
        self.row_force_default = True
        self.row_default_height = self.row_height


class Fold(Surface):
    def __init__(self, title, content, body_height=380, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None, **kwargs)
        self.title, self.content, self.body_height = title, content, dp(body_height)
        self.expanded = False
        self.toggle = Action("+  " + title, self.switch, height=dp(32))
        self.toggle.halign = "left"
        self.add_widget(self.toggle)
        self.height = dp(48)

    def switch(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self, value):
        self.expanded = bool(value)
        self.toggle.text = ("−  " if value else "+  ") + self.title
        if value and self.content.parent is None:
            self.add_widget(self.content)
        elif not value and self.content.parent is self:
            self.remove_widget(self.content)
        self.height = dp(54) + self.body_height if value else dp(48)
