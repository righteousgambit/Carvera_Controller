"""Mouse and keyboard resizing for the media/workbench columns."""

from kivy.graphics import Color, Line
from kivy.metrics import dp
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
    def __init__(self, workspace, **kwargs):
        super().__init__(size_hint_x=None, width=dp(12), **kwargs)
        self.workspace = workspace
        with self.canvas:
            self.ink = Color(*MUTED)
            self.line = Line(width=dp(1))
            self.grip = Line(width=dp(2))
        self.bind(pos=self._paint, size=self._paint, focus=self._paint)
        self._paint()

    def _paint(self, *_):
        self.ink.rgba = ACCENT if self.focus else (*MUTED[:3], 0.5)
        self.line.points = (self.center_x, self.y + dp(16), self.center_x, self.top - dp(16))
        self.grip.points = (self.center_x, self.center_y - dp(24), self.center_x, self.center_y + dp(24))

    def _resize(self, x):
        body = self.workspace.body
        flex = body.width - body.padding[0] - body.padding[2] - 2 * body.spacing - self.width
        if flex > 0:
            set_media_share(self.workspace, (x - body.x - body.padding[0] - body.spacing - self.width / 2) / flex)

    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos) or getattr(touch, "is_mouse_scrolling", False):
            return super().on_touch_down(touch)
        self.focus = True
        if getattr(touch, "is_double_tap", False):
            set_media_share(self.workspace, 0.5)
            return True
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._resize(touch.x)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
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
