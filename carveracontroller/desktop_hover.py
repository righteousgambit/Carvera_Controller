"""Pointer hit testing prunes hidden branches and clipped scroll content."""

from kivy.core.window import Window
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action


def active_modal():
    return next((item for item in Window.children if isinstance(item, ModalView) and item._is_open), None)


def hovered_actions(scope, position):
    """Resolve displayed actions without visiting disabled/hidden descendants.

    Layouts can intentionally overflow, so only scroll viewports clip children.
    Hit testing uses each widget's transform, including scrolled content.
    """
    pending, hovered = [scope], set()
    while pending:
        item = pending.pop()
        if item.disabled or item.opacity <= 0 or item.width <= 0 or item.height <= 0:
            continue
        if isinstance(item, Screen) and item.manager and item.manager.current != item.name:
            continue
        if isinstance(item, (Action, ScrollView)):
            # ScrollView.to_local enters its translated content space. Its
            # clipping rectangle instead lives in the parent's coordinates.
            transform = item.parent if isinstance(item, ScrollView) and item.parent else item
            inside = item.collide_point(*transform.to_widget(*position))
            if isinstance(item, ScrollView) and not inside:
                continue
            if isinstance(item, Action) and inside:
                hovered.add(item)
        pending.extend(item.children)
    return hovered
