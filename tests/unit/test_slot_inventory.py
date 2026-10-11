from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.machine.slot_inventory import SlotInventory, inventory_rows


def test_complete_receipt_requires_header_slots_and_boundary_and_never_infers_contents():
    inventory = SlotInventory()
    inventory.begin(4, 10)
    inventory.feed("ok", 4, 10.1)
    assert inventory.pending and inventory.receipt is None
    inventory.feed("Tool Slots Configuration:", 4, 10.2)
    inventory.feed("Tool 17: X=-100 Y=-40 Z=-50", 4, 10.3)
    inventory.feed("<Idle|MPos:0,0,0>", 4, 10.4)
    assert inventory.receipt is None
    inventory.feed("ok", 4, 10.5)
    receipt = inventory.receipt
    assert receipt.slots[0].position == (-100, -40, -50)
    assert len(receipt.response_sha256) == 64
    rows = inventory_rows(
        receipt, {1: SimpleNamespace(description="Declared mill"), 17: SimpleNamespace(description="Declared drill")}
    )
    assert rows[0]["position"] is None
    assert rows[1]["declared_name"] == "Declared drill"
    assert all(row["contents"] == "Unknown" for row in rows)
    inventory.expire(5, 11)
    assert inventory.receipt is None


@pytest.mark.parametrize(
    "lines",
    [
        ["Tool Slots Configuration:", "ok"],
        ["Tool Slots Configuration:", "Tool 1: broken", "ok"],
        ["Tool Slots Configuration:", "Tool 1: X=1 Y=2 Z=3", "version = 2.1.0c", "ok"],
        ["Tool Slots Configuration:", "Tool Slots Configuration:", "ok"],
        ["ERROR: unsupported", "ok"],
    ],
)
def test_failed_or_ambiguous_responses_never_publish(lines):
    inventory = SlotInventory()
    inventory.begin(1, 10)
    for line in lines:
        inventory.feed(line, 1, 10.1)
    assert inventory.receipt is None
    assert not inventory.pending and inventory.error


def test_timeout_duplicate_and_reconnect_boundaries():
    inventory = SlotInventory()
    inventory.begin(1, 10)
    with pytest.raises(ValueError, match="already pending"):
        inventory.begin(1, 11)
    inventory.expire(1, 15)
    assert not inventory.pending and "timed out" in inventory.error
    inventory.feed("Tool Slots Configuration:", 1, 16)
    assert inventory.receipt is None
    inventory.begin(2, 20)
    inventory.feed("Tool Slots Configuration:", 3, 20.1)
    assert not inventory.pending and not inventory.lines


@pytest.fixture
def controller(monkeypatch):
    from carveracontroller import Controller as module
    from carveracontroller.CNC import CNC
    from carveracontroller.machine.observed_pose import ObservedPose

    monkeypatch.setattr(module.time, "monotonic", lambda: 10.1)
    result = module.Controller(CNC(), Mock())
    result.stream = Mock()
    result.comms.encode_command = lambda payload: payload
    result.observed_pose = ObservedPose(10, "Idle", (0, 0, 0), (0, 0, 0), 1, 50)
    result._capability_observations = {"model": "C1", "firmware": "2.1.0c", "has_atc": True}
    return result


def test_actual_dispatch_and_receive_capture_are_exactly_read_only(controller):
    controller.query_slot_inventory()
    controller.stream.send.assert_called_once_with(b"M889\n")
    with pytest.raises(ValueError, match="pending"):
        controller.query_slot_inventory()
    controller._capability_observations["firmware"] = "changed after dispatch"
    for line in ("Tool Slots Configuration:", "Tool 1: X=1 Y=2 Z=3", "ok"):
        controller.parseLine(line)
    assert controller.slot_inventory.receipt.slots[0].number == 1
    assert dict(controller.slot_inventory.receipt.source)["firmware"] == "2.1.0c"
    assert controller.stream.send.call_count == 1


@pytest.mark.parametrize("change", ["stale", "busy", "paused", "disconnected", "unsupported", "no_atc"])
def test_dispatch_rechecks_current_evidence(controller, change):
    from dataclasses import replace

    if change == "stale":
        controller.observed_pose = replace(controller.observed_pose, timestamp=1)
    elif change == "busy":
        controller.observed_pose = replace(controller.observed_pose, state="Run")
    elif change == "paused":
        controller.paused = True
    elif change == "disconnected":
        controller.stream = None
    elif change == "unsupported":
        controller._capability_observations["firmware"] = "9.0.0c"
    else:
        controller._capability_observations["has_atc"] = False
    with pytest.raises(ValueError):
        controller.query_slot_inventory()
    assert not controller.slot_inventory.pending
    if controller.stream:
        controller.stream.send.assert_not_called()


def test_failed_send_is_terminal_without_retry(controller):
    controller.stream.send.side_effect = OSError("closed")
    with pytest.raises(ValueError, match="transport failed"):
        controller.query_slot_inventory()
    assert controller.stream.send.call_count == 1
    assert not controller.slot_inventory.pending and controller.slot_inventory.receipt is None


def test_firmware_default_includes_zero_and_full_supported_range_is_bounded():
    inventory = SlotInventory()
    inventory.begin(1, 10)
    inventory.feed("Tool Slots Configuration:", 1, 10.1)
    for number in range(256):
        inventory.feed(f"Tool {number}: X=-100 Y=-40 Z=-50", 1, 10.2)
    inventory.feed("ok", 1, 10.3)
    assert inventory.receipt is not None
    rows = inventory_rows(inventory.receipt, {})
    assert [row["number"] for row in rows] == list(range(256))
    assert all(row["contents"] == "Unknown" for row in rows)


def test_more_than_firmware_range_cannot_publish():
    inventory = SlotInventory()
    inventory.begin(1, 10)
    inventory.feed("Tool Slots Configuration:", 1, 10.1)
    for number in range(257):
        inventory.feed(f"Tool {number}: X=1 Y=2 Z=3", 1, 10.2)
    inventory.feed("ok", 1, 10.3)
    assert inventory.receipt is None and not inventory.pending
