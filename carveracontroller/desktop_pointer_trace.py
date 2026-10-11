"""Opt-in, bounded input diagnostics; observers never consume or reroute input."""

from collections import deque

from kivy.clock import Clock
from kivy.core.window import Window


class PointerTrace:
    def __init__(self, panes, changed, window=Window, clock=Clock):
        self.panes = panes
        self.changed = changed
        self.window = window
        self.clock = clock
        self.events = deque(maxlen=128)
        self.active = False
        self.reason = "Not recording"
        self._timeout = None
        self._paint = clock.create_trigger(lambda _dt: changed(), 0)
        self._bindings = {
            "on_mouse_down": self._mouse_down,
            "on_mouse_move": self._mouse_move,
            "on_mouse_up": self._mouse_up,
            "on_touch_down": self._touch_down,
            "on_touch_move": self._touch_move,
            "on_touch_up": self._touch_up,
        }

    def start(self):
        if self.active:
            return
        self.events.clear()
        self.reason = "Recording for up to 30 seconds / 128 events"
        self.active = True
        self.window.bind(**self._bindings)
        self._timeout = self.clock.schedule_once(lambda _dt: self.stop("30-second limit reached"), 30)
        self._paint()

    def stop(self, reason="Stopped"):
        if self.active:
            self.window.unbind(**self._bindings)
        self.active = False
        if self._timeout is not None:
            self._timeout.cancel()
            self._timeout = None
        self.reason = reason
        self._paint()

    def record(self, route, position, button=""):
        if not self.active:
            return False
        panes = []
        for name, pane in () if route.startswith("raw") else self.panes.items():
            if pane.get_root_window() is not None and not pane.disabled:
                local = pane.to_widget(*position)
                if pane.collide_point(*local):
                    panes.append(name)
        self.events.append({"route": route, "position": tuple(position), "button": button, "panes": panes})
        if len(self.events) >= self.events.maxlen:
            self.stop("128-event limit reached")
        self._paint()
        return False

    def _mouse(self, route, x, y, button=""):
        # Keep raw SDL/window coordinates alongside the actual transformed touch.
        # No speculative normalization is used to claim the receiving pane.
        return self.record(route, (x, y), button)

    def _mouse_down(self, _window, x, y, button, _modifiers):
        return self._mouse("raw down", x, y, button)

    def _mouse_move(self, _window, x, y, _modifiers):
        return self._mouse("raw move", x, y)

    def _mouse_up(self, _window, x, y, button, _modifiers):
        return self._mouse("raw up", x, y, button)

    def _touch_down(self, _window, touch):
        return self.record("touch down", touch.pos, getattr(touch, "button", ""))

    def _touch_move(self, _window, touch):
        return self.record("touch move", touch.pos, getattr(touch, "button", ""))

    def _touch_up(self, _window, touch):
        return self.record("touch up", touch.pos, getattr(touch, "button", ""))

    def summary(self):
        lines = [f"{self.reason} · {len(self.events)} events"]
        lines.append(f"Window {tuple(self.window.size)} · system {tuple(self.window.system_size)}")
        for event in list(self.events)[-5:]:
            x, y = event["position"]
            if event["route"].startswith("raw"):
                panes = "raw top-left coordinates"
            else:
                panes = "under: " + " / ".join(event["panes"]) if event["panes"] else "outside media"
            lines.append(f"{event['route']} {event['button']} · {x:.1f}, {y:.1f} · {panes or 'outside media'}")
        return "\n".join(lines)
