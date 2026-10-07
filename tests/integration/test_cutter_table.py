import json
import threading
from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.cutter_table import export_tsv
from carveracontroller.machine.desktop_profiles import ProfileStore, validate_library
from tests.integration.conftest import pump_frames


def finish_review(paste):
    for _ in range(100):
        pump_frames(1, sleep=0.01)
        if not paste.review_action.disabled:
            return
    raise AssertionError("Review worker did not finish")


def finish_save(paste):
    for _ in range(100):
        pump_frames(1, sleep=0.01)
        if not paste.saving:
            return
    raise AssertionError("Atomic save worker did not finish")


def make_store(tmp_path, count=1000):
    data = validate_library(
        {
            "schema": 1,
            "machines": [],
            "toolsets": [],
            "tools": [
                {
                    "id": f"cutter-{i}",
                    "name": f"Cutter {i:04}",
                    "number": i + 1,
                    "diameter": 6.35 if i % 2 else 3.175,
                    "shank_diameter": 6.35,
                    "length": 76.2,
                    "flute_length": 25.4,
                    "stickout": 30,
                    "vendor": "Titan" if i % 2 else "Helical",
                    "product_id": f"part-{i}",
                }
                for i in range(count)
            ],
        }
    )
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data))
    return ProfileStore(path)


def test_table_toolbar_reflows_without_losing_selection_or_editor_draft(kivy_app, tmp_path, monkeypatch):
    from tests.integration.conftest import set_window_viewport

    original_size = Window.width, Window.height
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    store = make_store(tmp_path, count=20)
    original_bytes = store.path.read_bytes()
    library = ProfileLibrary(ws, store=store, size_hint=(None, None), size=(dp(600), dp(780)))
    Window.add_widget(library)
    try:
        library.select_kind("tools")
        library.fields["name"].text = "Unsaved cutter draft"
        library.table_button.dispatch("on_release")
        table = library.table_popup
        table.select("cutter-1")
        for width, expected_columns in ((360, 2), (600, 4), (1200, 4), (360, 2)):
            set_window_viewport(dp(width), dp(780))
            pump_frames(12)
            assert table.table_actions.cols == expected_columns
            assert table.search.width > dp(width * 0.8)
            # Narrow windows wrap both action groups; retain three full data rows.
            assert table.grid.height >= dp(3 * 38)
            assert table.selection.ids == {"cutter-1"}
            assert library.fields["name"].text == "Unsaved cutter draft"
            for action in table.table_actions.children:
                assert action.width >= dp(110)
                left, _ = action.to_window(*action.pos)
                right, _ = action.to_window(action.right, action.top)
                assert left >= table.content.x and right <= table.content.right + dp(1)
                assert action.top <= table.search.y and action.y >= table.grid.top
        # Native1340x792 high-density window: fixed controls exceed its height.
        # Body scrolling must preserve the row area and visible footer actions.
        set_window_viewport(dp(670), dp(393))
        pump_frames(12)
        assert table.grid.height >= dp(3 * 38)
        assert table.table_body.height > table.body_scroll.height
        close = next(action for action in table.footer_actions.children if action.text == "Close")
        assert close.y >= 0 and close.top <= Window.height
        assert table.body_scroll.top <= table.content.top
        table.body_scroll.scroll_y = 0
        pump_frames(8)
        _, bottom = table.grid.to_window(*table.grid.pos)
        _, top = table.grid.to_window(table.grid.right, table.grid.top)
        assert bottom >= table.body_scroll.y - dp(1)
        assert top <= table.body_scroll.top + dp(1)
        assert table.selection.ids == {"cutter-1"}
        assert library.fields["name"].text == "Unsaved cutter draft"
        set_window_viewport(dp(1200), dp(780))
        pump_frames(8)
        table.search.text = "Titan"
        pump_frames(10, sleep=0.02)
        select = next(action for action in table.table_actions.children if action.text == "Select results")
        select.dispatch("on_release")
        assert table.selection.ids == {f"cutter-{i}" for i in range(1, 20, 2)}
        clear = next(action for action in table.table_actions.children if action.text == "Clear")
        clear.dispatch("on_release")
        assert not table.selection.ids
        assert store.path.read_bytes() == original_bytes
        send.assert_not_called()
        table.dismiss(animation=False)
        pump_frames(4)
        closed_size = table.size
        set_window_viewport(*original_size)
        pump_frames(4)
        assert table.size == closed_size and not table.resize_trigger.is_triggered
    finally:
        if getattr(library, "table_popup", None):
            library.table_popup.dismiss()
        Window.remove_widget(library)
        set_window_viewport(*original_size)
        pump_frames(6)


def test_virtual_table_keyboard_sort_resize_and_hidden_selection(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, apply = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "apply_tool_profile", apply)
    store = make_store(tmp_path)
    before = store.path.read_bytes()
    library = ProfileLibrary(ws, store=store, size_hint=(None, None), size=(dp(1100), dp(780)))
    Window.add_widget(library)
    try:
        library.select_kind("tools")
        library.fields["name"].text = "Retained draft"
        library.table_button.dispatch("on_release")
        table = library.table_popup
        pump_frames(12)
        assert len(table.grid.data) == 1000
        assert 2 < len(table.layout.children) < 50
        assert table.grid.height > dp(300)
        # Pointer events exercise real header sorting and divider capture.
        from kivy.tests.common import UnitTestTouch

        header = table.header_buttons[2]
        x, y = header.to_window(*header.center)
        pointer = UnitTestTouch(x, y)
        pointer.profile.append("button")
        pointer.button = "left"
        pointer.touch_down()
        pump_frames(4, sleep=0.02)
        pointer.touch_up()
        pump_frames(4, sleep=0.02)
        assert table.sort_key == "diameter"
        grip = table.header_cells[0].children[0]
        x, y = grip.to_window(*grip.center)
        pointer = UnitTestTouch(x, y)
        from types import SimpleNamespace

        from kivy.base import EventLoop

        with monkeypatch.context() as provider_patch:
            provider_patch.setattr(EventLoop, "input_providers", [SimpleNamespace(current_drag=pointer)])
            table.header_scroll._preserve_native_press(Window, 0, 0, [])
        assert not pointer.sync_with_dispatch
        # The native mouse provider queues the same mutable event for begin,
        # update and end. A sub-frame drag can reach its final position before
        # begin is dispatched; opos still identifies the pressed divider.
        pointer.move({"x": (x + dp(50)) / (Window.width - 1), "y": y / (Window.height - 1)})
        pointer.touch_down()
        # A desktop drag must capture immediately, before ScrollView's timeout.
        assert any(target() is grip for target in pointer.grab_list)
        pointer.touch_move(x + dp(50), y)
        pointer.touch_up()
        pump_frames(4, sleep=0.02)
        assert table.widths[0] == pytest.approx(dp(300), abs=dp(1))
        assert table.sort_key == "diameter"
        # Coordinate conversion must also work after horizontal scrolling.
        table.header_scroll.scroll_x = 0.35
        pump_frames(4)
        for index, cell in enumerate(table.header_cells):
            grip = cell.children[0]
            x, y = grip.to_window(*grip.center)
            if table.header_scroll.x + dp(60) < x < table.header_scroll.right - dp(60):
                break
        else:
            raise AssertionError("No visible divider after scrolling")
        width = table.widths[index]
        pointer = UnitTestTouch(x, y)
        pointer.touch_down()
        assert any(target() is grip for target in pointer.grab_list)
        pointer.touch_move(x - dp(40), y)
        pointer.touch_up()
        pump_frames(4)
        assert table.widths[index] == pytest.approx(width - dp(40), abs=dp(1))
        assert table.sort_key == "diameter"
        table.header_scroll.scroll_x = 0
        table.sort_column(0)
        table.grid.focus = True
        table.grid.keyboard_on_key_down(None, (274, "down"), "", [])
        table.grid.keyboard_on_key_down(None, (274, "down"), "", ["shift"])
        assert table.selection.ids == {"cutter-0", "cutter-1"}
        table.sort_column(2)
        assert table.matches[0]["diameter"] == 3.175
        table.sort_column(2)
        assert table.matches[0]["diameter"] == 6.35
        assert table.selection.ids == {"cutter-0", "cutter-1"}
        table.resize_column(0, dp(400))
        pump_frames(8)
        assert table.header_cells[0].width == dp(400)
        for row in table.layout.children:
            assert row.cells[0].width == dp(400)
        table.search.text = "Titan part-999"
        pump_frames(10, sleep=0.02)
        assert table.order == ["cutter-999"]
        assert "2 selected outside filter" in table.status.text
        import carveracontroller.desktop_cutter_table as table_module

        copied = Mock()
        monkeypatch.setattr(table_module.Clipboard, "copy", copied)
        table.copy_selected()
        text = copied.call_args.args[0]
        assert "cutter-0" in text and "cutter-1" in text
        assert "cutter-999" not in text
        table.clear_selection()
        table.select("cutter-999")
        table.edit_action.dispatch("on_release")
        pump_frames(8)
        assert library.selected_id == "cutter-999"
        library.select_record("tools", "cutter-0")
        assert library.fields["name"].text == "Retained draft"
        assert store.path.read_bytes() == before
        send.assert_not_called()
        apply.assert_not_called()
    finally:
        if getattr(library, "table_popup", None):
            library.table_popup.dismiss()
        Window.remove_widget(library)


def test_paste_review_atomic_save_conflicts_stale_and_layout(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, apply = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "apply_tool_profile", apply)
    store = make_store(tmp_path, 3)
    library = ProfileLibrary(ws, store=store, size_hint=(None, None), size=(dp(1100), dp(780)))
    Window.add_widget(library)
    try:
        library.select_kind("tools")
        library.open_table()
        table = library.table_popup
        pump_frames(12)
        table.open_paste("ID\tStickout\tVendor\ncutter-0\t1.5 in\tUpdated vendor\ncutter-1\t1.5 in\tUpdated vendor")
        paste = table.paste_popup
        pump_frames(8)
        before = store.path.read_bytes()
        paste.review_action.dispatch("on_release")
        finish_review(paste)
        assert not paste.save_action.disabled and len(paste.changes) == 2
        assert "30 -> 38.1 mm" in paste.review_text.text
        assert store.path.read_bytes() == before
        paste.export_to_png(str(tmp_path / "cutter-paste-review.png"))
        paste.save_action.dispatch("on_release")
        finish_save(paste)
        pump_frames(8)
        assert paste.parent is None
        assert [r["stickout"] for r in ProfileStore(store.path).data["tools"]] == pytest.approx([38.1, 38.1, 30])
        assert library.fields["stickout"].value() == pytest.approx(38.1)
        # A conflicting unfinished editor draft disables the reviewed save.
        library.fields["name"].text = "Unfinished"
        table.open_paste("ID\tVendor\ncutter-0\tAnother vendor")
        paste = table.paste_popup
        paste.review()
        finish_review(paste)
        assert paste.save_action.disabled and "drafts conflict" in paste.message.text
        library.revert()
        paste.review()
        finish_review(paste)
        assert not paste.save_action.disabled
        store.save_tool(dict(store.data["tools"][2], name="Concurrent change"))
        paste.save()
        finish_save(paste)
        assert "changed after review" in paste.message.text
        assert paste.save_action.disabled
        paste.review()
        finish_review(paste)
        paste.input.text += "\n"
        assert paste.save_action.disabled and not paste.changes
        paste.dismiss()
        table.search.text = ""
        table.size = (dp(680), dp(580))
        pump_frames(12)
        assert table.grid.height > dp(200)
        assert table.edit_action.right <= table.right
        table.grid.scroll_x = 1
        pump_frames(8)
        assert table.header_scroll.scroll_x == 1
        table.export_to_png(str(tmp_path / "cutter-table-compact.png"))
        table.size = (dp(1250), dp(780))
        table.grid.scroll_x = 0
        pump_frames(12)
        table.export_to_png(str(tmp_path / "cutter-table-wide.png"))
        send.assert_not_called()
        apply.assert_not_called()
    finally:
        if getattr(library, "table_popup", None):
            library.table_popup.dismiss()
        Window.remove_widget(library)


def test_review_worker_invalidation_pages_and_atomic_save_liveness(kivy_app, tmp_path, monkeypatch):
    import carveracontroller.desktop_cutter_table as module

    store = make_store(tmp_path, 95)
    library = ProfileLibrary(kivy_app.root.desktop_workspace, store=store)
    Window.add_widget(library)
    gate, entered = threading.Event(), threading.Event()
    original_review, original_save = module.review_tsv, store.update_tools
    try:
        library.select_kind("tools")
        library.open_table()
        table = library.table_popup
        pump_frames(8)
        text = "ID\tVendor\n" + "\n".join(f"cutter-{i}\tChanged" for i in range(95))
        table.open_paste(text)
        paste = table.paste_popup
        pump_frames(8)

        def delayed_review(*args):
            entered.set()
            assert gate.wait(2)
            return original_review(*args)

        monkeypatch.setattr(module, "review_tsv", delayed_review)
        paste.review()
        assert entered.wait(1)
        paste.input.text = "ID\tVendor\ncutter-0\tNew draft"
        gate.set()
        pump_frames(20, sleep=0.01)
        assert not paste.changes and paste.save_action.disabled
        assert not paste.review_action.disabled
        monkeypatch.setattr(module, "review_tsv", original_review)
        paste.input.text = text
        paste.review()
        finish_review(paste)
        assert len(paste.changes) == 95
        assert "Review 1/4" in paste.page_label.text
        assert "Cutter 0029" in paste.review_text.text
        assert "Cutter 0030" not in paste.review_text.text
        paste.next_action.dispatch("on_release")
        assert "Review 2/4" in paste.page_label.text
        assert "Cutter 0030" in paste.review_text.text
        # Delayed disk work does not block the UI; the atomic commit cannot be
        # silently cancelled once the reviewed save has started.
        gate.clear()
        entered.clear()

        def delayed_save(*args):
            entered.set()
            assert gate.wait(2)
            return original_save(*args)

        monkeypatch.setattr(store, "update_tools", delayed_save)
        paste.save()
        assert entered.wait(1)
        pump_frames(4)
        assert paste.saving and paste.input.disabled and paste.cancel_action.disabled
        paste.dismiss()
        assert paste._is_open
        gate.set()
        finish_save(paste)
        pump_frames(6)
        assert paste.parent is None
        assert {r["vendor"] for r in ProfileStore(store.path).data["tools"]} == {"Changed"}
        # Explicit reload accepts valid external data while retaining editor drafts.
        library.fields["name"].text = "Retained on reload"
        external = store.data
        external["tools"][1]["vendor"] = "Externally updated"
        store.path.write_text(json.dumps(external))
        table.reload_records()
        for _ in range(100):
            pump_frames(1, sleep=0.01)
            if not table.reloading:
                break
        assert not table.reloading
        assert table.records[1]["vendor"] == "Externally updated"
        assert library.fields["name"].text == "Retained on reload"
    finally:
        gate.set()
        if getattr(library, "table_popup", None):
            library.table_popup.dismiss()
        Window.remove_widget(library)
