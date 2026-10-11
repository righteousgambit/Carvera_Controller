"""Pointer transforms, hidden subtree pruning and modal hover ownership."""

import time
from unittest.mock import Mock

from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import Action
from carveracontroller.desktop_hover import hovered_actions
from tests.integration.conftest import pump_frames


def test_hidden_branches_are_pruned_before_pointer_transforms(kivy_app, monkeypatch):
    scope = FloatLayout(size_hint=(None, None), size=(300, 300))
    hidden = FloatLayout(size_hint=(None, None), size=(300, 0))
    target = Action("hidden", size_hint=(None, None), size=(100, 36))
    hidden.add_widget(target)
    for _ in range(10000):
        hidden.add_widget(Widget())
    scope.add_widget(hidden)
    transform = Mock(side_effect=AssertionError("Hidden descendant visited"))
    monkeypatch.setattr(target, "to_widget", transform)
    started = time.perf_counter()
    assert hovered_actions(scope, (20, 20)) == set()
    elapsed = time.perf_counter() - started
    print(f"HOVER hidden 10000 descendants: {elapsed:.6f}s")
    transform.assert_not_called()
    hidden.height = 300
    hidden.disabled = True
    assert hovered_actions(scope, (20, 20)) == set()
    hidden.disabled = False
    hidden.opacity = 0
    assert hovered_actions(scope, (20, 20)) == set()
    transform.assert_not_called()


def test_scroll_view_clips_hover_and_transforms_visible_content(kivy_app):
    scope = FloatLayout(size_hint=(None, None), size=(300, 300))
    viewport = ScrollView(size_hint=(None, None), size=(200, 100), pos=(50, 50), do_scroll_x=False)
    content = FloatLayout(size_hint=(None, None), size=(200, 400))
    top = Action("top", size_hint=(None, None), size=(150, 36), pos=(0, 350))
    bottom = Action("bottom", size_hint=(None, None), size=(150, 36), pos=(0, 0))
    content.add_widget(top)
    content.add_widget(bottom)
    viewport.add_widget(content)
    scope.add_widget(viewport)
    Window.add_widget(scope)
    try:
        pump_frames(5)
        point = top.to_window(top.x + 10, top.y + 10)
        assert hovered_actions(scope, point) == {top}, (
            point,
            top.pos,
            viewport.pos,
            viewport.size,
            top.to_widget(*point),
            viewport.to_widget(*point),
            content.pos,
        )
        assert hovered_actions(scope, bottom.to_window(bottom.x + 10, bottom.y + 10)) == set()
        viewport.scroll_y = 0
        pump_frames(5)
        assert hovered_actions(scope, bottom.to_window(bottom.x + 10, bottom.y + 10)) == {bottom}
        assert hovered_actions(scope, top.to_window(top.x + 10, top.y + 10)) == set()
    finally:
        Window.remove_widget(scope)


def test_workspace_modal_and_removed_controls_release_hover(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    action = Action("hover probe", size_hint=(None, None), size=(180, 36), pos=(20, 20))
    ws.add_widget(action)
    popup = ModalView(size_hint=(None, None), size=(300, 200), auto_dismiss=False)
    modal_action = Action("modal probe", size_hint=(None, None), size=(180, 36))
    popup.add_widget(modal_action)
    try:
        pump_frames(3)
        point = action.to_window(action.x + 10, action.y + 10)
        ws._hover(Window, point)
        assert action.hovered
        popup.open()
        pump_frames(4)
        ws._hover(Window, modal_action.to_window(modal_action.x + 10, modal_action.y + 10))
        assert modal_action.hovered and not action.hovered
        assert not ws.pane_divider.hovered
        popup.dismiss(animation=False)
        pump_frames(3)
        ws._hover(Window, point)
        assert action.hovered and not modal_action.hovered
        ws.remove_widget(action)
        ws._hover(Window, point)
        assert not action.hovered
        send.assert_not_called()
    finally:
        popup.dismiss(animation=False)
        if action.parent:
            action.parent.remove_widget(action)
        ws._hover(Window, (-100, -100))
