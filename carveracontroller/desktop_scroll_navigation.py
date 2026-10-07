"""Reveal local results after layout settles without changing workspace tabs."""

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView


def queue_preserve_scroll_anchor(widget, *, active, layout_root=None):
    """Keep a visible selector at its screen position after its report resizes.

    A subsequent navigation or explicit scroll wins over this pending correction.
    Clamp at content boundaries rather than adding artificial empty space.
    """
    parent = widget.parent
    visited = set()
    while parent is not None and not isinstance(parent, ScrollView) and id(parent) not in visited:
        visited.add(id(parent))
        parent = parent.parent
    if not isinstance(parent, ScrollView) or parent._viewport is None:
        return
    anchor_y = widget.to_window(widget.x, widget.top)[1]
    bottom = parent.to_window(parent.x, parent.y)[1]
    if not bottom <= anchor_y <= bottom + parent.height:
        return
    original_scroll = parent.scroll_y
    viewport = parent._viewport
    attempts = 0

    def restore(_dt):
        nonlocal attempts
        attempts += 1
        if not active() or parent._viewport is not viewport or abs(parent.scroll_y - original_scroll) > 1e-7:
            return
        ancestor = widget.parent
        visited = set()
        while ancestor is not None and ancestor is not parent and id(ancestor) not in visited:
            visited.add(id(ancestor))
            ancestor = ancestor.parent
        if ancestor is not parent:
            return
        pending = list((layout_root or widget).walk(restrict=True))
        ancestor = widget.parent
        while ancestor is not None and ancestor is not parent:
            pending.append(ancestor)
            ancestor = ancestor.parent
        pending.append(parent)
        if any(
            getattr(item, name, None) is not None and getattr(item, name).is_triggered
            for item in pending
            for name in ("_trigger_texture", "_trigger_layout")
        ):
            if attempts < 120:
                Clock.schedule_once(restore, 0)
            return
        travel = viewport.height - parent.height
        if travel <= 0:
            return
        delta = widget.to_window(widget.x, widget.top)[1] - anchor_y
        target = min(1, max(0, parent.scroll_y + delta / travel))
        Animation.cancel_all(parent, "scroll_y")
        cancel = getattr(parent.parent, "cancel_restore", None)
        if cancel is not None:
            cancel()
        if parent.effect_y is not None:
            parent.effect_y.velocity = 0
            parent.effect_y.is_manual = False
            parent.effect_y.value = -travel * target
        parent.scroll_y = target

    Clock.schedule_once(restore, 0)


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
