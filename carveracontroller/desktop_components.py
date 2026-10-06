"""Shared desktop surfaces, inputs and responsive layout primitives."""

import math
import sys
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput

from carveracontroller.machine.clipboard_text import ClipboardReadError, read_text
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


def release_screen_focus(screen):
    """Release outgoing keyboard owners without walking a potentially large page.

    Kivy keeps one focused owner per keyboard, including multi-keyboard setups.
    Copy the owners because clearing focus changes that registry. Toolbar and
    modal owners outside this screen retain their focus.
    """
    for owner in list(FocusBehavior._keyboards.values()):
        current = owner
        while current is not None:
            if current is screen:
                owner.focus = False
                break
            parent = current.parent
            if parent is current:  # Kivy Window terminates its chain with itself.
                break
            current = parent


def displayed_control(widget):
    """Exclude hidden screens and disabled ancestors from keyboard traversal."""
    current = widget
    while current is not None:
        if (
            getattr(current, "disabled", False)
            or getattr(current, "opacity", 1) <= 0
            or current.height <= 0
            or current.width <= 0
        ):
            return False
        if isinstance(current, Screen) and current.manager and current.manager.current != current.name:
            return False
        parent = current.parent
        if parent is current:
            break
        current = parent
    if current is not Window:
        return False
    modal = next((item for item in Window.children if isinstance(item, ModalView) and item._is_open), None)
    return modal is None or widget in modal.walk()


class DesktopFocus:
    """Shared focus order for fields, buttons and selectors in the active scope."""

    def _get_focus_next(self, focus_dir):
        scope, current = self, self
        while current.parent is not None and hasattr(current.parent, "walk"):
            current = current.parent
            scope = current
            if isinstance(current, ModalView) or getattr(current, "desktop_focus_scope", False):
                break
        controls = [
            item
            for item in scope.walk()
            if isinstance(item, FocusBehavior) and item.is_focusable and displayed_control(item)
        ]
        if self not in controls or len(controls) < 2:
            return None
        direction = 1 if focus_dir == "focus_next" else -1
        return controls[(controls.index(self) + direction) % len(controls)]

    def _desktop_focus_changed(self, _widget, focused):
        if not focused:
            self._activation_key = None
            return
        if not displayed_control(self):
            self.focus = False
            return
        app = App.get_running_app()
        root = getattr(app, "root", None)
        if root is not None and getattr(root, "keyboard_jog_control", False):
            root.toggle_keyboard_jog_control(disable=True)
        current = self.parent
        while current is not None:
            if isinstance(current, ScrollView):
                current.scroll_to(self, padding=dp(12), animate=False)
                break
            parent = current.parent
            if parent is current:
                break
            current = parent

    def keyboard_on_key_up(self, window, keycode):
        if getattr(self, "_activation_key", None) == keycode[1]:
            self._activation_key = None
            return True
        return super().keyboard_on_key_up(window, keycode)

    def keyboard_on_textinput(self, window, text):
        if not displayed_control(self):
            self.focus = False
            return True
        return super().keyboard_on_textinput(window, text)


class DesktopScrollView(ScrollView):
    """Desktop content scrolling with an operable, visible drag target."""

    def __init__(self, **kwargs):
        kwargs.setdefault("scroll_type", ["content", "bars"])
        kwargs.setdefault("bar_width", dp(9))
        kwargs.setdefault("bar_color", MUTED)
        kwargs.setdefault("bar_inactive_color", (*MUTED[:3], 0.35))
        kwargs.setdefault("always_overscroll", False)
        super().__init__(**kwargs)

    def scroll_page(self, direction):
        """Move one overlapping viewport without inertial overshoot."""
        viewport = self._viewport
        overflow = viewport.height - self.height if viewport else 0
        if not self.do_scroll_y or overflow <= 0:
            return
        target = max(0, min(1, self.scroll_y + direction * self.height * 0.8 / overflow))
        if self.effect_y:
            self.effect_y.velocity = 0
            self.effect_y.is_manual = False
            self.effect_y.value = -overflow * target
        self.scroll_y = target

    def on_scroll_start(self, touch, check_children=True):
        # Kivy visits nested scroll views before testing this viewport. A
        # scrolled-out child can otherwise capture a sibling toolbar click.
        if not self.collide_point(*touch.pos):
            touch.ud[self._get_uid("svavoid")] = True
            return False
        if "button" in touch.profile and touch.button in ("scrollup", "scrolldown"):
            if self.disabled:
                return True
            # Give a nested viewport first refusal, using the same coordinate
            # transformation as Kivy. Editable text still receives clicks.
            if check_children:
                touch.push()
                try:
                    touch.apply_transform_2d(self.to_local)
                    if self.dispatch_children("on_scroll_start", touch):
                        return True
                finally:
                    touch.pop()
            viewport = self._viewport
            overflow = viewport.height - self.height if viewport else 0
            if self.do_scroll_y and overflow > 0:
                # Kivy's wheel branch depends on effect_x even for a vertical
                # viewport. Set the visible fraction directly so vertical-only
                # panels and disabled horizontal effects behave identically.
                direction = 1 if touch.button == "scrolldown" else -1
                target = max(0, min(1, self.scroll_y + direction * self.scroll_wheel_distance / overflow))
                if target == self.scroll_y:
                    return False  # Allow an enclosing viewport to continue.
                if self.effect_y:
                    self.effect_y.velocity = 0
                    self.effect_y.is_manual = False
                    self.effect_y.value = -overflow * target
                self.scroll_y = target
                touch.ud[self._get_uid("svavoid")] = True
                return True
            return False
        handled = super().on_scroll_start(touch, check_children)
        state = touch.ud.get(self._get_uid())
        if handled and state and (touch.ud.get("in_bar_x") or touch.ud.get("in_bar_y")):
            # A scrollbar is an explicit drag target. Kivy otherwise applies
            # the content-pan threshold before moving its handle, making small
            # desktop adjustments appear inert, especially on near-full bars.
            state["mode"] = "scroll"
            state["desktop_bar_axes"] = (touch.ud.get("in_bar_x", False), touch.ud.get("in_bar_y", False))
        return handled

    def on_scroll_move(self, touch):
        state = touch.ud.get(self._get_uid())
        axes = state.get("desktop_bar_axes") if state else None
        if not axes:
            return super().on_scroll_move(touch)
        # The claimed handle owns this gesture. Child scroll views share
        # Kivy's in_bar flags; dispatching through them can turn the handle
        # into an unstarted content effect or steal its direction.
        touch.ud["in_bar_x"], touch.ud["in_bar_y"] = axes
        for axis, claimed, delta, extent, fraction in (
            ("x", axes[0], touch.dx, self.width, self.hbar[1]),
            ("y", axes[1], touch.dy, self.height, self.vbar[1]),
        ):
            travel = extent * (1 - fraction)
            if not claimed or not getattr(self, "do_scroll_" + axis) or travel <= 0:
                continue
            target = max(0, min(1, getattr(self, "scroll_" + axis) + delta / travel))
            effect = getattr(self, "effect_" + axis)
            if effect:
                effect.velocity = 0
                effect.is_manual = False
                overflow = getattr(self._viewport, "width" if axis == "x" else "height") - extent
                effect.value = -overflow * target
            setattr(self, "scroll_" + axis, target)
            touch.ud["sv.handled"][axis] = True
        state["user_stopped"] = True
        touch.ud["sv.can_defocus"] = False
        return True

    def on_scroll_stop(self, touch):
        state = touch.ud.get(self._get_uid())
        axes = state.get("desktop_bar_axes") if state else None
        if axes:
            touch.ud["in_bar_x"], touch.ud["in_bar_y"] = axes
        return super().on_scroll_stop(touch)


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


class Action(DesktopFocus, FocusBehavior, Button):
    hovered = BooleanProperty(False)
    keyboard_activation = BooleanProperty(True)

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
            self._focus_color = Color(*ACCENT[:3], 0)
            self._focus_border = Line(rounded_rectangle=(*self.pos, *self.size, dp(6)), width=1.4)
            Color(1, 1, 1, 1)
        self.bind(
            pos=self._paint,
            size=self._paint,
            state=self._paint,
            disabled=self._paint,
            hovered=self._paint,
            focus=self._paint,
        )
        self.bind(focus=self._desktop_focus_changed)
        if action:
            self.bind(on_release=lambda _: action())

    def _paint(self, *_):
        factor = 0.48 if self.disabled else 0.85 if self.state == "down" else 1.13 if self.hovered else 1
        self._fill.rgba = tuple(c * factor for c in self.base_color[:3]) + (1,)
        self._shape.pos, self._shape.size = self.pos, self.size
        focus_color = TEXT if self.base_color == ACCENT else ACCENT
        self._focus_color.rgba = (*focus_color[:3], 1 if self.focus and not self.disabled else 0)
        self._focus_border.rounded_rectangle = (*self.pos, *self.size, dp(6))

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if keycode[1] in ("enter", "numpadenter", "spacebar") and not modifiers:
            if (
                self.focus
                and not self.disabled
                and self.keyboard_activation
                and displayed_control(self)
                and getattr(self, "_activation_key", None) is None
            ):
                self._activation_key = keycode[1]
                self.trigger_action(duration=0)
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class Field(DesktopFocus, TextInput):
    validation_error = StringProperty("")
    paste_pending = BooleanProperty(False)
    paste_error = StringProperty("")

    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_size", sp(13))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(38))
        kwargs.setdefault("padding", (dp(10), dp(9)))
        kwargs.setdefault("write_tab", False)
        self._focus_entry_text = kwargs.get("text", "")
        self._paste_cancel = None
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
        self.bind(pos=self._paint, size=self._paint, focus=self._paint, validation_error=self._paint)
        self.bind(focus=self._desktop_focus_changed)
        self.bind(focus=self._remember_entry)
        self.bind(paste_pending=self._paint, paste_error=self._paint)
        self.bind(
            text=self._cancel_paste,
            cursor=self._cancel_paste,
            selection_text=self._cancel_paste,
            focus=self._cancel_paste,
            parent=self._cancel_paste,
            disabled=self._cancel_paste,
            readonly=self._cancel_paste,
        )

    def _cancel_paste(self, *_):
        if self._paste_cancel is not None:
            self._paste_cancel.set()
            self._paste_cancel = None
        self.paste_pending = False
        self.paste_error = ""

    def paste(self):
        if sys.platform != "darwin":
            return super().paste()
        if self.readonly or not self.focus or not displayed_control(self):
            return None
        self._cancel_paste()
        cancel = self._paste_cancel = threading.Event()
        original = (self.text, tuple(self.cursor), self.selection_from, self.selection_to)
        self.paste_pending = True

        def finish(data, error):
            if self._paste_cancel is not cancel:
                return
            current = (self.text, tuple(self.cursor), self.selection_from, self.selection_to)
            self._paste_cancel = None
            self.paste_pending = False
            if cancel.is_set() or current != original or not self.focus or not displayed_control(self) or self.readonly:
                return
            if error:
                self.paste_error = error
                return
            # Use the same editing primitives as TextInput.paste, preserving
            # its selection replacement, filtering and undo semantics.
            self.delete_selection()
            self.insert_text(data if self.multiline else data.replace("\n", " "))

        def read():
            try:
                data, error = read_text(cancel), ""
            except ClipboardReadError as exc:
                data, error = "", str(exc)
            Clock.schedule_once(lambda _dt: finish(data, error), 0)

        threading.Thread(target=read, name="clipboard-text", daemon=True).start()

    def _remember_entry(self, _widget, focused):
        if focused:
            self._focus_entry_text = self.text

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if self.focus and not displayed_control(self):
            self.focus = False
            return False
        if keycode[1] == "escape" and self.focus and not self.readonly:
            self.text = self._focus_entry_text
            self.focus = False
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def _paint(self, *_):
        self._shape.pos, self._shape.size = self.pos, self.size
        self._border_color.rgba = (
            DANGER
            if self.validation_error or self.paste_error
            else AMBER
            if self.paste_pending
            else ACCENT
            if self.focus
            else BORDER
        )
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
        self.input.validation_error = self.error
        self.input._paint()


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


class DesktopDropDown(DropDown):
    """Close synchronously so rapid cancel/reopen cannot attach twice."""

    def on_touch_down(self, touch):
        # ScrollView delays an option's release until after Window's focus
        # cleanup. Keep the owning selector focused while that click resolves;
        # otherwise focus loss dismisses the menu before its option can select.
        if self.collide_point(*touch.pos) and touch not in FocusBehavior.ignored_touch:
            FocusBehavior.ignored_touch.append(touch)
        return super().on_touch_down(touch)

    def on_key_down(self, instance, key, scancode, codepoint, modifiers):
        # DropDown's Window handler runs before the focused selector's keyboard
        # handler. Preserve its Escape keyup consumption through that path too.
        owner = self.attach_to
        if key == 27 and self.get_parent_window() and isinstance(owner, Choice) and owner.focus:
            owner._activation_key = "escape"
            owner.is_open = False
            return True
        return super().on_key_down(instance, key, scancode, codepoint, modifiers)

    def dismiss(self, *args):
        Clock.unschedule(self._real_dismiss)
        if self.parent is not None or self.attach_to is not None:
            self._real_dismiss(*args)


class Choice(DesktopFocus, FocusBehavior, Spinner):
    def __init__(self, **kwargs):
        self._keyboard_choice_index = None
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(36))
        kwargs.setdefault("font_size", sp(12))
        kwargs.setdefault("option_cls", ChoiceOption)
        kwargs.setdefault("dropdown_cls", DesktopDropDown)
        super().__init__(**kwargs)
        self.background_normal = self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT
        self.shorten = True
        self.shorten_from = "right"
        with self.canvas.before:
            Color(*RAISED)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            self._border_color = Color(*BORDER)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, dp(6)), width=0.7)
            Color(1, 1, 1, 1)
        self.bind(pos=self._paint, size=self._paint, focus=self._paint)
        self.bind(focus=self._desktop_focus_changed)
        self.bind(is_open=self._choice_opened, focus=self._choice_focus)
        self.bind(values=lambda *_: self._choice_opened(self, self.is_open))

    def _choice_focus(self, _widget, focused):
        if not focused:
            self.is_open = False

    def _choice_opened(self, _widget, opened):
        self._keyboard_choice_index = self.values.index(self.text) if opened and self.text in self.values else None
        self._highlight_choice()

    def _highlight_choice(self):
        index = self._keyboard_choice_index
        value = self.values[index] if index is not None and 0 <= index < len(self.values) else None
        for row in self._dropdown.container.children:
            row.background_color = ACCENT if row.text == value else RAISED
            row.color = BG if row.text == value else TEXT
            if row.text == value and self.is_open:
                self._dropdown.scroll_to(row, animate=False)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if not self.focus or self.disabled or not displayed_control(self):
            return False
        if keycode[1] == "escape" and self.is_open:
            self._activation_key = "escape"
            self.is_open = False
            return True
        if keycode[1] == "tab":
            self.is_open = False
        if keycode[1] in ("up", "down") and not modifiers:
            if self.values:
                self.is_open = True
                index = self._keyboard_choice_index
                direction = 1 if keycode[1] == "down" else -1
                self._keyboard_choice_index = (index + direction) % len(self.values) if index is not None else 0
                self._highlight_choice()
            return True
        if keycode[1] in ("enter", "numpadenter", "spacebar") and not modifiers:
            if (
                self.focus
                and not self.disabled
                and displayed_control(self)
                and getattr(self, "_activation_key", None) is None
            ):
                self._activation_key = keycode[1]
                if self.is_open:
                    index = self._keyboard_choice_index
                    if index is not None and 0 <= index < len(self.values):
                        self._dropdown.select(self.values[index])
                    else:
                        self.is_open = False
                elif self.values:
                    self.is_open = True
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def _paint(self, *_):
        self._shape.pos, self._shape.size = self.pos, self.size
        self._border_color.rgba = ACCENT if self.focus else BORDER
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
