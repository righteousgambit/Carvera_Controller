from dataclasses import replace

from carveracontroller.desktop_setup_editor import SetupEditor
from tests.integration.test_imported_stock_workflow import settle, stock_record
from tests.integration.test_imported_stock_workflow import stock_case as stock_case


def test_pending_block_draft_is_retained_separately_from_new_imported_stock(stock_case, tmp_path, monkeypatch):
    ws, viewer, _cad, send = stock_case
    monkeypatch.setattr(ws, "selected_machine_profile", None)
    monkeypatch.setattr(ws, "setup_drafts", {}, raising=False)
    block = replace(viewer.machine_setup, stock_model=None, stock_size_mm=(2, 2, 2))
    # Restore the setup patch before stock_case performs scene cleanup.
    with monkeypatch.context() as source_patch:
        source_patch.setattr(viewer, "machine_setup", block)
        previous = SetupEditor(ws, "stock")
        previous.fields["stock_size_mm", 0].text = "9"
        previous.stash()
        previous.keep()
        assert previous.key in ws.setup_drafts
        ws.prepare_stock_model(stock_record(tmp_path))
        settle(ws)
        source = viewer.machine_setup.stock_model
        imported = SetupEditor(ws, "stock")
        try:
            assert imported.key != previous.key and previous.key in ws.setup_drafts
            assert imported.baseline["stock_source"] == source.reference
            assert all(imported.fields["stock_size_mm", i].input.readonly for i in range(3))
            assert all(button.disabled for i in range(3) for button in imported.fields["stock_size_mm", i].step_buttons)
            assert imported.current_matches() and "Imported stock" in imported.intro.text
        finally:
            imported.cancel()
        viewer.machine_setup = block
        resumed = SetupEditor(ws, "stock")
        try:
            assert resumed.key == previous.key and resumed.fields["stock_size_mm", 0].text == "9"
            assert not resumed.fields["stock_size_mm", 0].input.readonly
        finally:
            resumed.cancel()
        send.assert_not_called()
