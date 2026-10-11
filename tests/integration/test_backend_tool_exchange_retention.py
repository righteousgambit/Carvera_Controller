import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action
from carveracontroller.machine.probe_settings_workflow import load_journal
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401 - fixture dependency
from tests.integration.test_backend_tool_exchange import exchange_workbench, prepared  # noqa: F401 - fixture


def test_failed_result_retention_keeps_original_response_and_pending_intent(exchange_workbench, monkeypatch):  # noqa: F811
    import carveracontroller.desktop_tool_exchange as module

    panel, _backend, _ws, state, requests = exchange_workbench
    review = prepared(panel)
    original = module.append_journal

    def journal(path, record, **kwargs):
        if record["phase"] == "exchange_acknowledged":
            raise OSError("synthetic result retention failure")
        return original(path, record, **kwargs)

    monkeypatch.setattr(module, "append_journal", journal)
    panel.exchange(review)
    wait_for(lambda: not panel.busy)
    assert state.exchange_commands == [b"M6 T2\n"]
    assert panel.latest_record["response"]["original_ipc_bytes_base64"]
    assert panel.latest_record["result_durability"] == "unconfirmed"
    assert load_journal(panel.journal_path)[-1]["record"]["phase"] == "exchange_pending"
    assert panel.observation_review is panel.review is None
    assert not panel.receipt_action.disabled
    panel.exchange(review)
    assert len([m for m, p in requests if m == "operation" and p["operation"] == "tool.change"]) == 1


@pytest.mark.parametrize("width", [320, 650, 1100])
def test_collapsible_exchange_controls_mount_in_actual_workbench_without_operator_writes(
    kivy_app, tmp_path, monkeypatch, width
):
    ws = kivy_app.root.desktop_workspace
    operator = Path.home() / ".carvera" / "tool-exchanges"
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in operator.glob("*.jsonl")}
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Setup")
    ws.setup_tasks.show("Tools")
    deck = ws.setup_tasks
    toggle = next(
        widget
        for widget in deck.sections["Tools"].walk()
        if isinstance(widget, Action)
        and widget.text in ("Review physical rack exchange", "Hide reviewed rack exchange")
    )
    if ws.tool_exchange_panel is not None and ws.tool_exchange_panel.parent is not None:
        toggle.dispatch("on_release")
    toggle.dispatch("on_release")
    panel = ws.tool_exchange_panel
    assert panel is not None and panel.parent is not None
    parent = deck.parent
    parent.remove_widget(deck)
    popup = Popup(content=deck, size_hint=(None, None), size=(dp(width + 28), dp(760)))
    popup.open(animation=False)
    try:
        pump_frames(12)
        assert panel.identity_action.disabled and panel.review_action.disabled
        assert panel.identity_action.width >= dp(100)
        for widget in (panel.summary, panel.note):
            assert widget.height >= widget.texture_size[1]
        deck.export_to_png(str(tmp_path / f"tool-exchange-{width}.png"))
        toggle.dispatch("on_release")
        assert panel.parent is None
        toggle.dispatch("on_release")
        assert ws.tool_exchange_panel is panel and panel.parent is not None
        send.assert_not_called()
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in operator.glob("*.jsonl")}
        assert before == after
    finally:
        if panel.parent is not None:
            toggle.dispatch("on_release")
        popup.dismiss(animation=False)
        if deck.parent is not None:
            deck.parent.remove_widget(deck)
        parent.add_widget(deck)
