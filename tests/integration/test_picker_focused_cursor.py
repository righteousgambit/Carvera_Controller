"""Focused and recycled rows activate the current cursor without machine effects."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_file_picker import ArtifactBrowser
from carveracontroller.desktop_program_picker import ProgramBrowser
from tests.integration.conftest import pump_frames
from tests.integration.test_desktop_file_picker import wait_for
from tests.integration.test_program_picker_inspection import wait_for_inspection, wait_for_listing


@pytest.fixture
def machine_effects(kivy_app, monkeypatch):
    machine = kivy_app.root.desktop_workspace.machine
    effects = []
    for owner, name in (
        (machine.controller, "executeCommand"),
        (machine, "view_local_file"),
        (machine, "check_and_upload"),
        (machine, "check_and_download"),
        (machine.file_popup.remote_rv, "list_dir"),
    ):
        effect = Mock(name=name)
        monkeypatch.setattr(owner, name, effect)
        effects.append(effect)
    return effects


def click_and_focus_row(browser, entry):
    from kivy.tests.common import UnitTestTouch

    pump_frames(6)
    row = next(row for row in browser.rows.children if row.entry == entry)
    pointer = UnitTestTouch(*row.to_window(*row.center))
    pointer.touch_down()
    pointer.touch_up()
    pump_frames(12, sleep=0.01)
    # Selecting publishes fresh row data; reacquire the row that now renders A.
    row = next(row for row in browser.rows.children if row.entry == entry)
    # Exercise the actual FocusBehavior owner, as retained after a pointer or
    # keyboard traversal, rather than dispatching against an unfocused row.
    row.focus = True
    pump_frames(2)
    assert row.focus and row.entry == entry
    return row


def press(route, row, code, name):
    from kivy.core.window import Window

    if route == "window":
        assert Window.dispatch("on_key_down", code, 0, "", [])
        Window.dispatch("on_key_up", code, 0)
    else:
        assert row.keyboard_on_key_down(Window, (code, name), "", [])
        row.keyboard_on_key_up(Window, (code, name))


def tab_to_row_without_selection(browser):
    from kivy.core.window import Window
    from kivy.uix.behaviors import FocusBehavior

    from carveracontroller.desktop_file_picker import ArtifactRow

    browser.search.focus = True
    for _ in range(40):
        Window.dispatch("on_key_down", 9, 0, "", [])
        Window.dispatch("on_key_up", 9, 0)
        pump_frames(2)
        owner = next(
            (
                item
                for item in FocusBehavior._keyboards.values()
                if isinstance(item, ArtifactRow)
                and item.focus
                and item.browser is browser
                and item.parent is browser.files._viewport
            ),
            None,
        )
        if owner is not None:
            return owner
    raise AssertionError("Tab traversal did not reach a current picker row")


@pytest.mark.parametrize("route", ["window", "focused-row"])
@pytest.mark.parametrize("rebind", [False, True], ids=["retained-focus", "recycled-focus"])
def test_artifact_enter_chooses_current_cursor_once(kivy_app, tmp_path, monkeypatch, machine_effects, route, rebind):
    from kivy.core.window import Window

    for name in ("a.cvmap", "b.cvmap", "c.cvmap"):
        (tmp_path / name).write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
    browser.path = tmp_path
    row = None
    try:
        browser.open()
        wait_for(lambda: browser.ready)
        first, current, other = browser.visible_entries
        row = click_and_focus_row(browser, first)
        assert browser.selected_path == first.path
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        pump_frames(3)
        assert browser.selected_path == current.path and row.focus
        assert browser.filename.text == current.name
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        row.entry = other if rebind else first
        press(route, row, 13, "enter")
        wait_for(lambda: browser.closed)
        selected.assert_called_once_with(current)
        chosen.assert_called_once_with(current.path)
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("route", ["window", "focused-row"])
@pytest.mark.parametrize("rebind", [False, True], ids=["retained-focus", "recycled-focus"])
def test_artifact_space_marks_current_cursor_without_choosing(
    kivy_app, tmp_path, monkeypatch, machine_effects, route, rebind
):
    from kivy.core.window import Window

    for name in ("a.cvmap", "b.cvmap", "c.cvmap"):
        (tmp_path / name).write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
    browser.path = tmp_path
    row = None
    try:
        browser.open()
        wait_for(lambda: browser.ready)
        first, current, other = browser.visible_entries
        row = click_and_focus_row(browser, first)
        assert browser.selected_path == first.path
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        pump_frames(3)
        assert browser.selected_path == current.path and row.focus
        selected = Mock(wraps=browser.select)
        choose = Mock(wraps=browser.choose)
        monkeypatch.setattr(browser, "select", selected)
        monkeypatch.setattr(browser, "choose", choose)
        row.entry = other if rebind else first
        press(route, row, 32, "spacebar")
        pump_frames(3)
        selected.assert_called_once_with(current)
        assert browser.selected_path == current.path
        assert browser.filename.text == current.name
        assert not browser.closed and not browser.choosing
        choose.assert_not_called()
        chosen.assert_not_called()
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("route", ["window", "focused-row"])
@pytest.mark.parametrize("rebind", [False, True], ids=["retained-focus", "recycled-focus"])
def test_program_space_inspects_current_cursor_without_preview_or_transfer(
    kivy_app, tmp_path, monkeypatch, machine_effects, route, rebind
):
    from kivy.core.window import Window

    for index, name in enumerate(("a.nc", "b.nc", "c.nc"), 1):
        (tmp_path / name).write_text(f"G21 G90 G54\nT{index}\nG0 X0 Y0 Z5\nG1 X{index} F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    row = None
    try:
        browser.open()
        wait_for_listing(browser)
        first, current, other = browser.visible_entries
        row = click_and_focus_row(browser, first)
        wait_for_inspection(browser)
        assert browser.selected == first
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        pump_frames(3)
        assert browser.cursor_path == current.path and row.focus
        assert browser.selected == first  # Arrow movement alone performs no inspection.
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        row.entry = other if rebind else first
        press(route, row, 32, "spacebar")
        wait_for_inspection(browser)
        selected.assert_called_once_with(current)
        assert browser.selected == current
        assert browser.cursor_path == current.path
        assert browser.inspection.digest == hashlib.sha256((tmp_path / "b.nc").read_bytes()).hexdigest()
        assert browser.inspection.tool_ids == (2,)
        assert browser._reference_visible and browser.popup.parent is not None
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("code, name", [(13, "enter"), (32, "spacebar")])
def test_program_actions_require_the_visible_inspected_cursor(
    kivy_app, tmp_path, monkeypatch, machine_effects, code, name
):
    from kivy.core.window import Window

    for index, filename in enumerate(("a.nc", "b.nc", "c.nc"), 1):
        (tmp_path / filename).write_text(f"G21 G90 G54\nT{index}\nG0 X0 Y0 Z5\nG1 X{index} F100\n")
    workspace = kivy_app.root.desktop_workspace
    browser = ProgramBrowser(workspace)
    # Make Upload eligibility observable without connecting the app or changing
    # its live state. Every transfer/command entry point remains a fixture spy.
    browser.workspace = SimpleNamespace(
        connected=True,
        app=SimpleNamespace(state="Idle"),
        selected_machine_profile=workspace.selected_machine_profile,
        loaded_toolset=workspace.loaded_toolset,
    )
    monkeypatch.setattr(browser, "_remote_allowed", lambda: True)
    saved = Mock(wraps=browser._queue_place_save)
    monkeypatch.setattr(browser, "_queue_place_save", saved)
    browser.local_path = str(tmp_path)
    row = None
    try:
        browser.open()
        wait_for_listing(browser)
        first, current, _other = browser.visible_entries
        row = click_and_focus_row(browser, first)
        wait_for_inspection(browser)
        actions = (browser.preview_button, browser.upload_button, browser.favorite_button)
        assert browser.selected == first and all(not action.disabled for action in actions)
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        pump_frames(3)
        assert browser.cursor_path == current.path and browser.selected == first
        assert all(action.disabled for action in actions)
        saved.reset_mock()
        browser.preview()
        browser.upload()
        browser.toggle_favorite()
        saved.assert_not_called()
        for effect in machine_effects:
            effect.assert_not_called()
        assert browser._reference_visible and browser._pending_upload is None

        press("window", row, code, name)
        wait_for_inspection(browser)
        assert browser.selected == current and browser.cursor_path == current.path
        assert all(not action.disabled for action in actions)
        browser.search.text = "c.nc"
        pump_frames(3)
        assert current not in browser.visible_entries
        assert all(action.disabled for action in actions)
        saved.reset_mock()
        browser.preview()
        browser.upload()
        browser.toggle_favorite()
        saved.assert_not_called()
        assert browser._reference_visible and browser._pending_upload is None
        browser.search.text = "b.nc"
        pump_frames(3)
        assert browser.visible_entries == [current]
        assert browser.selected == current and all(not action.disabled for action in actions)
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("action_name", ["Cancel", "Choose file"])
@pytest.mark.parametrize("code, name", [(13, "enter"), (32, "spacebar")])
def test_artifact_focused_button_owns_activation_without_reselecting(
    kivy_app, tmp_path, monkeypatch, machine_effects, action_name, code, name
):
    from carveracontroller.desktop_components import Action

    artifact = tmp_path / "a.cvmap"
    artifact.write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
    browser.path = tmp_path
    button = None
    try:
        browser.open()
        wait_for(lambda: browser.ready)
        entry = browser.visible_entries[0]
        row = click_and_focus_row(browser, entry)
        assert browser.selected_path == entry.path
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        button = next(
            widget for widget in browser.popup.walk() if isinstance(widget, Action) and widget.text == action_name
        )
        released = Mock(return_value=False)  # Observe without consuming the original on_release callback.
        button.bind(on_release=released)
        button.focus = True
        pump_frames(2)
        assert button.focus and not row.focus
        press("window", button, code, name)
        wait_for(lambda: browser.closed)
        released.assert_called_once_with(button)
        selected.assert_not_called()
        if action_name == "Choose file":
            chosen.assert_called_once_with(str(artifact))
        else:
            chosen.assert_not_called()
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if button is not None:
            button.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("code, name", [(13, "enter"), (32, "spacebar")])
def test_program_focused_detail_tab_owns_activation_without_reinspection(
    kivy_app, tmp_path, monkeypatch, machine_effects, code, name
):
    (tmp_path / "a.nc").write_text("G21 G90 G54\nT1\nG0 X0 Y0 Z5\nG1 X1 F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    button = None
    try:
        browser.open()
        wait_for_listing(browser)
        entry = browser.visible_entries[0]
        row = click_and_focus_row(browser, entry)
        wait_for_inspection(browser)
        inspection = browser.inspection
        selected = Mock(wraps=browser.select)
        detail = Mock(wraps=browser.choose_detail)
        monkeypatch.setattr(browser, "select", selected)
        monkeypatch.setattr(browser, "choose_detail", detail)
        button = browser.detail_tab_buttons["Source"]
        button.focus = True
        pump_frames(2)
        assert button.focus and not row.focus
        press("window", button, code, name)
        pump_frames(3)
        detail.assert_called_once_with("Source")
        selected.assert_not_called()
        assert browser.detail_view == "Source" and browser.inspection is inspection
        assert browser.selected == entry and browser._reference_visible
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if button is not None:
            button.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("kind", ["artifact", "program"])
def test_picker_search_owns_typed_space_without_cursor_activation(
    kivy_app, tmp_path, monkeypatch, machine_effects, kind
):
    from kivy.core.window import Window

    chosen = Mock()
    if kind == "artifact":
        (tmp_path / "a file.cvmap").write_text("{}")
        browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
        browser.path = tmp_path
    else:
        (tmp_path / "a file.nc").write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X1 F100\n")
        browser = ProgramBrowser(kivy_app.root.desktop_workspace)
        browser.local_path = str(tmp_path)
    try:
        browser.open()
        if kind == "artifact":
            wait_for(lambda: browser.ready)
        else:
            wait_for_listing(browser)
        entry = browser.visible_entries[0]
        row = click_and_focus_row(browser, entry)
        if kind == "program":
            wait_for_inspection(browser)
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        browser.search.text = "a"
        browser.search.focus = True
        browser.search.cancel_selection()
        browser.search.cursor = (1, 0)
        pump_frames(2)
        assert browser.search.focus and not row.focus
        # SDL sends a physical key event and its separate textinput event.
        Window.dispatch("on_key_down", 32, 0, " ", [])
        Window.dispatch("on_textinput", " ")
        Window.dispatch("on_key_up", 32, 0)
        pump_frames(3)
        assert browser.search.text == "a "
        assert browser.visible_entries == [entry]
        selected.assert_not_called()
        chosen.assert_not_called()
        assert browser.popup.parent is not None
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        browser.search.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("kind", ["artifact", "program"])
@pytest.mark.parametrize("code, name", [(13, "enter"), (32, "spacebar")])
def test_tab_first_picker_row_activates_without_an_existing_cursor(
    kivy_app, tmp_path, monkeypatch, machine_effects, kind, code, name
):
    chosen = Mock()
    if kind == "artifact":
        for filename in ("a.cvmap", "b.cvmap", "c.cvmap"):
            (tmp_path / filename).write_text("{}")
        browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
        browser.path = tmp_path
    else:
        for index, filename in enumerate(("a.nc", "b.nc", "c.nc"), 1):
            (tmp_path / filename).write_text(f"G21 G90 G54\nT{index}\nG0 X0 Y0 Z5\nG1 X{index} F100\n")
        browser = ProgramBrowser(kivy_app.root.desktop_workspace)
        browser.local_path = str(tmp_path)
    row = None
    try:
        browser.open()
        if kind == "artifact":
            wait_for(lambda: browser.ready)
        else:
            wait_for_listing(browser)
        row = tab_to_row_without_selection(browser)
        entry = row.entry
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        if kind == "artifact":
            assert browser.selected_path is None and browser.filename.text == ""
        else:
            assert browser.cursor_path is None and browser.selected is None and browser.inspection is None
        press("window", row, code, name)
        if kind == "artifact" and code == 13:
            wait_for(lambda: browser.closed)
            chosen.assert_called_once_with(entry.path)
        elif kind == "artifact":
            pump_frames(3)
            assert browser.selected_path == entry.path and browser.filename.text == entry.name
            assert not browser.closed and not browser.choosing
            chosen.assert_not_called()
        else:
            wait_for_inspection(browser)
            assert browser.selected == entry and browser.cursor_path == entry.path
            assert browser.inspection.digest == hashlib.sha256((tmp_path / entry.name).read_bytes()).hexdigest()
            assert browser._reference_visible
        selected.assert_called_once_with(entry)
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)


@pytest.mark.parametrize("route", ["window", "focused-row"])
@pytest.mark.parametrize("code, name", [(13, "enter"), (32, "spacebar")])
def test_tab_first_program_row_rejects_stale_listing_token(
    kivy_app, tmp_path, monkeypatch, machine_effects, route, code, name
):
    (tmp_path / "a.nc").write_text("G21 G90 G54\nT1\nG0 X0 Y0 Z5\nG1 X1 F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    row = None
    try:
        browser.open()
        wait_for_listing(browser)
        row = tab_to_row_without_selection(browser)
        entry = row.entry
        assert browser.cursor_path is None and browser.selected is None
        assert row.listing_token == browser._listing_token()
        browser._local_generation += 1  # A retained row has not received the replacement listing's token.
        selected = Mock(wraps=browser.select)
        monkeypatch.setattr(browser, "select", selected)
        press(route, row, code, name)
        pump_frames(3)
        selected.assert_not_called()
        assert browser.cursor_path is None and browser.selected is None and browser.inspection is None
        assert browser._reference_visible
        row.listing_token = browser._listing_token()
        press(route, row, code, name)
        wait_for_inspection(browser)
        selected.assert_called_once_with(entry)
        assert browser.selected == entry and browser.cursor_path == entry.path
        assert browser.inspection.tool_ids == (1,)
        for effect in machine_effects:
            effect.assert_not_called()
    finally:
        if row is not None:
            row.focus = False
        browser.dismiss()
        pump_frames(3)
