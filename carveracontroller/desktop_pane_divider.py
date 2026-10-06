"""Mouse and keyboard resizing for the media/workbench columns."""

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import ACCENT, MUTED


def set_media_share(workspace, share):
    share = min(0.75, max(0.25, float(share)))
    workspace.media_column.size_hint_x = share
    workspace.inspector.size_hint_x = 1 - share
    workspace.workspace_media_share = share
    if hasattr(workspace, "layout_panel"):
        workspace.layout_panel.share.text = f"{share * 100:g}"


class PaneDivider(FocusBehavior, Widget):
    hovered = BooleanProperty(False)

    def __init__(self, workspace, **kwargs):
        super().__init__(size_hint_x=None, width=dp(12), **kwargs)
        self.workspace = workspace
        self._drag_touch = None
        with self.canvas:
            self.track_ink = Color(*ACCENT[:3], 0)
            self.track = RoundedRectangle(radius=[dp(4)])
            self.ink = Color(*MUTED)
            self.line = Line(width=dp(1))
            self.grip = Line(width=dp(2))
        self.bind(pos=self._paint, size=self._paint, focus=self._paint, hovered=self._paint)
        self._paint()
        Clock.schedule_once(self._paint, 0)

    def _paint(self, *_):
        self.track_ink.rgba = (*ACCENT[:3], 0.14 if self.focus or self.hovered else 0)
        self.track.pos, self.track.size = self.pos, self.size
        self.ink.rgba = ACCENT if self.focus or self.hovered else (*MUTED[:3], 0.5)
        # Paint from base geometry; alias-property notifications may still be
        # queued during the first parent layout pass.
        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        self.line.points = (cx, self.y + dp(16), cx, self.y + self.height - dp(16))
        self.grip.points = (cx, cy - dp(24), cx, cy + dp(24))

    def _resize(self, x):
        body = self.workspace.body
        flex = body.width - body.padding[0] - body.padding[2] - 2 * body.spacing - self.width
        if flex > 0:
            set_media_share(self.workspace, (x - body.x - body.padding[0] - body.spacing - self.width / 2) / flex)

    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos) or getattr(touch, "is_mouse_scrolling", False):
            return super().on_touch_down(touch)
        self.focus = True
        FocusBehavior.ignored_touch.append(touch)
        if getattr(touch, "is_double_tap", False):
            set_media_share(self.workspace, 0.5)
            return True
        touch.grab(self)
        self._drag_touch = touch
        return True

    def on_touch_move(self, touch):
        # Kivy first dispatches movement normally, then to grabbed widgets.
        # Consume the ordinary dispatch too, before it reaches the 3D viewer.
        if touch is self._drag_touch:
            self._resize(touch.x)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch is self._drag_touch:
            touch.ungrab(self)
            self._drag_touch = None
            return True
        return super().on_touch_up(touch)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        name = keycode[1]
        if name in ("left", "right", "home"):
            share = getattr(self.workspace, "workspace_media_share", 0.5)
            step = 0.05 if "shift" in modifiers else 0.01
            set_media_share(self.workspace, 0.5 if name == "home" else share + (step if name == "right" else -step))
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)
