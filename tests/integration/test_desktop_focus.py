"""Keyboard workflows remain within the displayed editor and never jog while editing."""

from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen, ScreenManager

from carveracontroller.desktop_components import Action, Choice, Field, QuantityField, displayed_control
from tests.integration.conftest import pump_frames


@pytest.fixture
def focus_dialog(kivy_app):
    dialog = ModalView(size_hint=(0.7, 0.7))
    body = BoxLayout(orientation="vertical")
    dialog.add_widget(body)
    dialog.open(animation=False)
    pump_frames(3)
    yield body
    dialog.dismiss(animation=False)
    pump_frames(3)


def test_tab_skips_hidden_screen_and_disabled_ancestors_and_stays_in_dialog(kivy_app, focus_dialog):
    first, last = Field(text="first"), Action("Last")
    manager = ScreenManager()
    active, hidden = Screen(name="active"), Screen(name="hidden")
    inside, invisible = Choice(text="One", values=("One", "Two")), Field(text="hidden")
    active.add_widget(inside)
    hidden.add_widget(invisible)
    manager.add_widget(active)
    manager.add_widget(hidden)
    disabled_group = BoxLayout(disabled=True)
    excluded = Field(text="disabled ancestor")
    disabled_group.add_widget(excluded)
    for widget in (first, manager, disabled_group, last):
        focus_dialog.add_widget(widget)
    pump_frames(3)
    assert displayed_control(first)
    assert not displayed_control(invisible) and not displayed_control(excluded)
    assert not displayed_control(kivy_app.root.desktop_workspace.tab_buttons["Preview"])
    first.focus = True
    first.keyboard_on_key_down(None, (9, "tab"), "", [])
    assert inside.focus and not first.focus
    inside.keyboard_on_key_down(None, (9, "tab"), "", [])
    assert last.focus
    last.keyboard_on_key_down(None, (9, "tab"), "", ["shift"])
    assert inside.focus
    inside.keyboard_on_key_down(None, (9, "tab"), "", ["shift"])
    assert first.focus
    first.keyboard_on_key_down(None, (9, "tab"), "", ["shift"])
    assert last.focus  # Wrap inside the dialog, not into machine controls.


def test_keyboard_activation_is_once_per_press_and_excludes_jog_buttons(focus_dialog):
    callback = Mock()
    action = Action("Apply draft", callback)
    focus_dialog.add_widget(action)
    action.focus = True
    for _ in range(2):
        action.keyboard_on_key_down(None, (13, "enter"), "", [])
        pump_frames(2)
    callback.assert_called_once_with()
    assert action._focus_color.a == 1
    action.keyboard_on_key_up(None, (13, "enter"))
    action.keyboard_on_key_down(None, (13, "enter"), "", [])
    pump_frames(2)
    assert callback.call_count == 2
    action.disabled = True
    assert not action.focus
    action.keyboard_on_key_down(None, (13, "enter"), "", [])
    pump_frames(2)
    assert callback.call_count == 2
    jog = Action("X+", keyboard_activation=False)
    pressed = Mock()
    jog.bind(on_press=pressed)
    focus_dialog.add_widget(jog)
    jog.focus = True
    jog.keyboard_on_key_down(None, (13, "enter"), "", [])
    pump_frames(2)
    pressed.assert_not_called()


def test_escape_restores_edit_and_quantity_validation_stays_visible(focus_dialog):
    field = QuantityField(text="1/4 in", maximum=100)
    focus_dialog.add_widget(field)
    field.input.focus = True
    field.text = "10 rpm"
    assert field.input.validation_error and field.input._border_color.rgba[0] > 0.7
    field.input._paint()  # A focus/size repaint must not erase invalid state.
    assert field.input._border_color.rgba[0] > 0.7
    field.input.keyboard_on_key_down(None, (27, "escape"), "", [])
    assert field.text == "1/4 in" and field.value() == pytest.approx(6.35)
    assert not field.error and not field.input.validation_error and not field.input.focus


def test_focusing_controls_disables_keyboard_jog_and_arrow_handler_rechecks(kivy_app, monkeypatch, focus_dialog):
    root = kivy_app.root
    disable = Mock()
    monkeypatch.setattr(root, "keyboard_jog_control", True)
    monkeypatch.setattr(root, "toggle_keyboard_jog_control", disable)
    field = Field(text="edit")
    focus_dialog.add_widget(field)
    field.focus = True
    disable.assert_called_once_with(disable=True)
    # A user may re-enable the setting while a workbench control retains focus.
    # Recheck at the actual keyboard dispatch boundary as well.
    focus_dialog.parent.dismiss(animation=False)
    pump_frames(3)
    ws = root.desktop_workspace
    monkeypatch.setattr(root, "is_jogging_enabled", lambda: True)
    monkeypatch.setattr(root.controller, "jog", Mock())
    monkeypatch.setattr(root.manual_cmd, "focus", False)
    action = ws.tab_buttons["Preview"]
    action.focus = True
    assert action.focus and ws.has_keyboard_focus
    root._keyboard_jog_keydown(None, 275, None, None, [])
    root.controller.jog.assert_not_called()
    action.focus = False


def test_tab_departure_clears_focus_preserves_scroll_and_unfinished_text(kivy_app):
    ws = kivy_app.root.desktop_workspace
    ws.select("Setup")
    view = ws.inspector_pages.current_screen.children[0]
    content = view.children[0]
    field = Field(text="unfinished fixture note")
    content.add_widget(field)
    try:
        pump_frames(3)
        field.focus = True
        view.scroll_y = 0.37
        ws.select("Job")
        assert not field.focus
        ws.select("Setup")
        pump_frames(3)
        assert view.scroll_y == pytest.approx(0.37)
        assert field.text == "unfinished fixture note"
    finally:
        content.remove_widget(field)
        ws.select("Job")


def test_selector_keyboard_preview_commit_cancel_and_tab(focus_dialog):
    first = Choice(text="One", values=("One", "Two", "Three"))
    second = Field(text="next")
    focus_dialog.add_widget(first)
    focus_dialog.add_widget(second)
    pump_frames(3)
    first.focus = True
    changes = Mock()
    first.bind(text=changes)
    first.keyboard_on_key_down(None, (274, "down"), "", [])
    assert first.is_open and first._keyboard_choice_index == 1
    assert first.text == "One"  # Highlight is not applied selection.
    assert next(row for row in first._dropdown.container.children if row.text == "Two").background_color[1] > 0.7
    changes.assert_not_called()
    first.keyboard_on_key_down(None, (27, "escape"), "", [])
    assert not first.is_open and first.text == "One"
    first.keyboard_on_key_up(None, (27, "escape"))
    assert first.focus
    first.keyboard_on_key_down(None, (274, "down"), "", [])
    first.keyboard_on_key_down(None, (13, "enter"), "", [])
    assert first.text == "Two" and not first.is_open
    assert changes.call_count == 1
    first.keyboard_on_key_up(None, (13, "enter"))
    first.keyboard_on_key_down(None, (13, "enter"), "", [])
    assert first.is_open
    first.keyboard_on_key_down(None, (9, "tab"), "", [])
    assert not first.is_open and second.focus


def test_window_escape_dispatch_cancels_dropdown_and_retains_selector_focus(focus_dialog):
    selector = Choice(text="C1", values=("C1", "CA1"))
    focus_dialog.add_widget(selector)
    pump_frames(3)
    selector.focus = True
    Window.dispatch("on_key_down", 274, 0, "", [])
    assert selector.is_open and selector._keyboard_choice_index == 1
    Window.dispatch("on_key_down", 27, 0, "", [])
    Window.dispatch("on_key_up", 27, 0)
    assert not selector.is_open and selector.text == "C1"
    assert selector.focus and focus_dialog.parent._is_open
    Window.dispatch("on_key_down", 274, 0, "", [])
    assert selector.is_open  # Can reopen immediately through the real event route.


def test_pointer_selection_survives_scrollview_delayed_release(focus_dialog):
    from kivy.tests.common import UnitTestTouch

    selector = Choice(text="One", values=("One", "Two", "Three"))
    focus_dialog.add_widget(selector)
    pump_frames(3)
    selector.focus = True
    selector.is_open = True
    pump_frames(3)
    row = next(row for row in selector._dropdown.container.children if row.text == "Two")
    x, y = row.to_window(*row.center)
    touch = UnitTestTouch(x, y)
    touch.touch_down()
    touch.touch_up()
    pump_frames(20, sleep=0.01)
    assert selector.text == "Two"
    assert not selector.is_open
    assert selector.focus
    selector.is_open = True
    pump_frames(3)
    outside = UnitTestTouch(2, 2)
    outside.touch_down()
    outside.touch_up()
    pump_frames(3)
    assert not selector.is_open
    assert not selector.focus


def test_initial_tab_enters_active_dialog_and_hidden_action_cannot_run(kivy_app, focus_dialog):
    field = Field(text="dialog")
    focus_dialog.add_widget(field)
    pump_frames(3)
    ws = kivy_app.root.desktop_workspace
    for control in focus_dialog.walk():
        if hasattr(control, "focus"):
            control.focus = False
    assert ws._workspace_keydown(None, 9, None, "", [])
    assert field.focus
    hidden = ws.tab_buttons["Preview"]
    hidden.focus = True
    assert not hidden.focus  # Programmatic focus also respects the modal.


def test_dismissed_dialog_cannot_activate_or_edit_retained_controls(focus_dialog):
    callback = Mock()
    action, field = Action("Save", callback), Field(text="original")
    focus_dialog.add_widget(action)
    focus_dialog.add_widget(field)
    pump_frames(3)
    action.focus = True
    focus_dialog.parent.dismiss(animation=False)
    assert not displayed_control(action) and not displayed_control(field)
    action.keyboard_on_key_down(None, (13, "enter"), "", [])
    pump_frames(2)
    callback.assert_not_called()
    assert action.get_focus_next() is None
    field.keyboard_on_textinput(None, "hidden edit")
    assert field.text == "original" and not field.focus


def test_quantity_keyboard_precision_bounds_and_escape(kivy_app, monkeypatch, focus_dialog):
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    field = QuantityField(text="1/4 in", minimum=0, maximum=8)
    focus_dialog.add_widget(field)
    field.input.focus = True
    for name, modifiers, expected in (
        ("up", [], 6.45),
        ("down", ["alt"], 6.44),
        ("up", ["shift"], 7.44),
    ):
        assert field.input.keyboard_on_key_down(None, (273, name), "", modifiers)
        assert field.value() == pytest.approx(expected)
    previous = field.text
    field.input.keyboard_on_key_down(None, (273, "up"), "", ["shift"])
    assert field.text == previous and "Maximum" in field.error
    field.input.keyboard_on_key_down(None, (27, "escape"), "", [])
    assert field.text == "1/4 in" and not field.error
    send.assert_not_called()


def test_quantity_keyboard_rejects_invalid_hidden_and_readonly_drafts(focus_dialog):
    field = QuantityField(text="bad input")
    focus_dialog.add_widget(field)
    field.input.focus = True
    field.input.keyboard_on_key_down(None, (273, "up"), "", [])
    assert field.text == "bad input" and field.error
    field.text = "10"
    field.input.readonly = True
    field.input.keyboard_on_key_down(None, (273, "up"), "", [])
    assert field.text == "10"
    field.input.readonly = False
    focus_dialog.remove_widget(field)
    field.input.focus = True
    assert not field.input.keyboard_on_key_down(None, (273, "up"), "", [])
    assert field.text == "10" and not field.input.focus


def test_integer_quantity_fine_step_stays_integral(focus_dialog):
    field = QuantityField(kind="scalar", integer=True, text="3", minimum=1, maximum=20)
    focus_dialog.add_widget(field)
    field.input.focus = True
    field.input.keyboard_on_key_down(None, (273, "up"), "", ["alt"])
    assert field.value() == 4
    field.input.keyboard_on_key_down(None, (273, "down"), "", ["shift"])
    assert field.value() == 4 and "Minimum" in field.error


def test_quantity_arrow_draft_blocks_machine_keyboard_jog(kivy_app, monkeypatch):
    root = kivy_app.root
    ws = root.desktop_workspace
    ws.select("Setup")
    content = ws.inspector_pages.current_screen.children[0].children[0]
    field = QuantityField(text="10", minimum=0)
    content.add_widget(field)
    try:
        pump_frames(3)
        field.input.focus = True
        jog = Mock()
        monkeypatch.setattr(root.controller, "jog", jog)
        monkeypatch.setattr(root, "keyboard_jog_control", True)
        monkeypatch.setattr(root, "is_jogging_enabled", lambda: True)
        monkeypatch.setattr(root.manual_cmd, "focus", False)
        root._keyboard_jog_keydown(None, 273, None, None, [])
        field.input.keyboard_on_key_down(None, (273, "up"), "", [])
        assert field.value() == pytest.approx(10.1)
        jog.assert_not_called()
        ws.select("Job")
        assert not field.input.focus
    finally:
        content.remove_widget(field)
        ws.select("Job")
