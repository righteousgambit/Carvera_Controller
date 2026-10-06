"""Reveal local results after layout settles without changing workspace tabs."""

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView


def queue_reveal(widget, *, active, align_top=False):
    """Retain the caller's identity/visibility guard across pending layouts."""

    def reveal(_dt):
        if not active():
            return
        pending = list(widget.walk(restrict=True))
        parent = widget.parent
        visited = set()
        while parent is not None and not isinstance(parent, ScrollView) and id(parent) not in visited:
            visited.add(id(parent))
            pending.append(parent)
            parent = parent.parent
        if not isinstance(parent, ScrollView):
            return
        pending.append(parent)
        cancel = getattr(parent.parent, "cancel_restore", None)
        if cancel is not None:
            cancel()
        if any(
            getattr(item, name, None) is not None and getattr(item, name).is_triggered
            for item in pending
            for name in ("_trigger_texture", "_trigger_layout")
        ):
            Clock.schedule_once(reveal, 0)
            return
        Animation.cancel_all(parent, "scroll_x", "scroll_y")
        if parent.effect_y is not None:
            parent.effect_y.velocity = 0
        viewport = parent._viewport
        travel = viewport.height - parent.height if viewport else 0
        if align_top and travel > 0:
            top = widget.to_window(widget.x, widget.top)[1] - viewport.to_window(viewport.x, viewport.y)[1]
            parent.scroll_y = min(1, max(0, (top - parent.height + dp(12)) / travel))
            if parent.effect_y is not None:
                parent.effect_y.reset(-travel * parent.scroll_y)
        else:
            parent.scroll_to(widget, padding=dp(12), animate=False)

    return Clock.schedule_once(reveal, 0)
