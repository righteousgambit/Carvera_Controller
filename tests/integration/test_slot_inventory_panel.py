import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_slot_inventory import SlotInventoryPanel
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.slot_inventory import SlotInventory
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_inventory_review_is_bounded_responsive_and_never_changes_tools(width, monkeypatch):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller import desktop_slot_inventory as module

    clock = [10.2]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    inventory = SlotInventory()
    controller = SimpleNamespace(
        _adaptive_lock=threading.RLock(),
        _connection_generation=1,
        observed_pose=ObservedPose(10, "Idle", (0, 0, 0), (0, 0, 0), 1, 50),
        slot_inventory=inventory,
        query_slot_inventory=Mock(),
        executeCommand=Mock(),
    )
    comparison = SimpleNamespace(focus=Mock(), choose=Mock())
    table = {n: SimpleNamespace(description=f"Declared cutter {n}") for n in range(1, 15)}
    ws = SimpleNamespace(
        connected=True,
        machine=SimpleNamespace(controller=controller, gcode_viewer=SimpleNamespace(library_tool_table_mm=table)),
        tool_comparison=comparison,
    )
    panel = SlotInventoryPanel(ws)
    panel.size_hint = (None, None)
    panel.width = dp(width)
    Window.add_widget(panel)
    try:
        pump_frames(4)
        assert len(panel.tiles.children) == 6
        assert all(
            "Coordinates unobserved" in tile.text and "Contents: unknown" in tile.text for tile in panel.tiles.children
        )
        assert all(tile.width <= panel.width for tile in panel.tiles.children)
        controller.query_slot_inventory.assert_not_called()
        panel.read_button.dispatch("on_release")
        controller.query_slot_inventory.assert_called_once()
        controller.query_slot_inventory.side_effect = ValueError("Firmware support is unresolved")
        panel.query()
        panel.refresh()
        assert "Firmware support is unresolved" in panel.note.text
        controller.query_slot_inventory.side_effect = None
        panel.query()
        assert not panel.query_error
        inventory.begin(1, 10.2)
        for line in ("Tool Slots Configuration:", "Tool 1: X=1 Y=2 Z=3", "ok"):
            inventory.feed(line, 1, 10.3)
        clock[0] = 10.4
        panel.refresh()
        assert "current receipt" in panel.note.text
        assert not panel.overlay_rows()
        panel.target_button.dispatch("on_release")
        assert panel.overlay_rows() == ((1, (1, 2, 3)),)
        assert "Hide" in panel.target_button.text
        tile_ids = tuple(id(tile) for tile in panel.tiles.children)
        clock[0] = 10.5
        panel.refresh()
        assert tuple(id(tile) for tile in panel.tiles.children) == tile_ids
        panel.next.dispatch("on_release")
        assert panel.page == 1 and len(panel.tiles.children) == 6
        assert not panel.overlay_rows()
        panel.tiles.children[-1].dispatch("on_release")
        comparison.focus.assert_called_once()
        comparison.choose.assert_called_once_with(7)
        ws.connected = False
        panel.refresh()
        assert panel.read_button.disabled and "historical receipt" in panel.note.text
        controller._connection_generation = 2
        assert not panel.overlay_rows()
        panel.refresh()
        assert inventory.receipt is None and "Not queried" in panel.note.text
        controller.executeCommand.assert_not_called()
        pump_frames(5)
        assert all(tile.y >= panel.y and tile.top <= panel.top for tile in panel.tiles.children)
        assert all(tile.width > dp(100) for tile in panel.tiles.children)
        panel.export_to_png(f"/tmp/carvera-slot-inventory-{width}.png")
    finally:
        Window.remove_widget(panel)
