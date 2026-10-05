import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_slot_inventory import SlotInventoryPanel
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.slot_inventory import SlotInventory
from tests.integration.conftest import pump_frames


def wait_storage(panel):
    deadline = time.monotonic() + 5
    while panel.storage_busy and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.storage_busy


@pytest.mark.parametrize("width", [360, 650])
def test_saved_receipt_review_never_restores_current_evidence_or_queries(tmp_path, width):
    from kivy.core.window import Window
    from kivy.metrics import dp

    inventory = SlotInventory()
    now = time.monotonic()
    inventory.begin(1, now, {"model": "C1", "firmware": "2.1.0c", "address": "192.168.0.79"})
    for line in ("Tool Slots Configuration:", "Tool 0: X=-100 Y=-20 Z=-50", "Tool 2: X=-100 Y=-40 Z=-50", "ok"):
        inventory.feed(line, 1, now)
    original = inventory.receipt
    controller = SimpleNamespace(
        _adaptive_lock=threading.RLock(),
        _connection_generation=1,
        observed_pose=ObservedPose(now, "Idle", (0, 0, 0), (0, 0, 0), 1, 50),
        slot_inventory=inventory,
        query_slot_inventory=Mock(),
        executeCommand=Mock(),
    )
    pick = Mock()
    ws = SimpleNamespace(
        connected=True,
        choose_profile_file=pick,
        machine=SimpleNamespace(controller=controller, gcode_viewer=SimpleNamespace(library_tool_table_mm={})),
        tool_comparison=SimpleNamespace(focus=Mock(), choose=Mock()),
    )
    panel = SlotInventoryPanel(ws)
    panel.size_hint = (None, None)
    panel.width = dp(width)
    Window.add_widget(panel)
    assert panel.saved_selector.disabled
    path = tmp_path / "configuration.cvatc"
    panel.export_receipt()
    assert pick.call_args.kwargs["save"] is True
    pick.call_args.args[0](path)
    wait_storage(panel)
    assert "Saved and read back" in panel.storage_note.text
    assert ws.last_atc_export["sha256"]
    inventory.reset()
    controller._connection_generation = 2
    panel.review_saved()
    pick.call_args.args[0](path)
    wait_storage(panel)
    assert tuple(panel.saved_selector.values) == ("T0", "T2")
    panel.saved_selector.text = "T2"
    assert "Historical T2" in panel.saved_note.text
    assert "-100.000, -40.000, -50.000" in panel.saved_note.text
    assert "2.1.0c" in panel.saved_note.text
    assert inventory.receipt is None and not panel.overlay_rows()
    saved = panel.saved_receipt
    path.write_text('{"payload":{}}')
    panel.review_saved()
    pick.call_args.args[0](path)
    wait_storage(panel)
    assert panel.saved_receipt is saved
    assert "Invalid" in panel.storage_note.text
    controller.query_slot_inventory.assert_not_called()
    controller.executeCommand.assert_not_called()
    assert original.source == (("address", "192.168.0.79"), ("firmware", "2.1.0c"), ("model", "C1"))
    from carveracontroller.machine.slot_exchange import export_file

    many = SlotInventory()
    many.begin(3, time.monotonic())
    many.feed("Tool Slots Configuration:", 3, time.monotonic())
    for number in range(256):
        many.feed(f"Tool {number}: X=-100 Y=-40 Z=-50", 3, time.monotonic())
    many.feed("ok", 3, time.monotonic())
    many_path = tmp_path / "full-range.cvatc"
    export_file(many.receipt, many_path)
    panel.review_saved()
    pick.call_args.args[0](many_path)
    wait_storage(panel)
    assert len(panel.saved_selector.values) == 6
    panel.saved_next.dispatch("on_release")
    assert panel.saved_selector.values[0] == "T6"
    panel.change_saved_page(100)
    assert panel.saved_page == 42 and len(panel.saved_selector.values) == 4
    assert panel.saved_next.disabled
    panel.saved_selector.text = "T255"
    assert "Historical T255" in panel.saved_note.text
    assert inventory.receipt is None
    pump_frames(5)
    panel.export_to_png(f"/tmp/carvera-atc-historical-{width}.png")
    assert panel.saved_selector.width <= panel.width
    Window.remove_widget(panel)
