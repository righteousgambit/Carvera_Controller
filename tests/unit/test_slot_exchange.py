import copy
import json

import pytest

from carveracontroller.machine.slot_exchange import MAX_BYTES, bundle, canonical, decode, digest, export_file, read_file
from carveracontroller.machine.slot_inventory import SlotInventory


@pytest.fixture
def receipt():
    inventory = SlotInventory()
    source = {"model": "C1", "firmware": "2.1.0c", "address": "192.168.0.79", "protocol": "text"}
    inventory.begin(2, 10, source)
    source["model"] = "changed after dispatch"
    for line in ("Tool Slots Configuration:", "Tool 0: X=-100 Y=-20 Z=-50", "Tool 1: X=-100 Y=-40 Z=-50", "ok"):
        inventory.feed(line, 2, 10.2)
    return inventory.receipt


def test_receipt_roundtrip_retains_attributed_configuration_not_live_evidence(receipt, tmp_path):
    value = bundle(receipt)
    assert value["payload"]["source"]["model"] == "C1"
    assert "observed_at" not in value["payload"]  # process monotonic time cannot be portable freshness
    assert value["payload"]["contents"] == "unknown"
    assert value["payload"]["slots"][0]["number"] == 0
    path = tmp_path / "receipt.cvatc"
    result = export_file(receipt, path)
    restored, file_hash = read_file(path)
    assert restored == value and file_hash == result["sha256"]
    assert result["pockets"] == 2
    with pytest.raises(FileExistsError):
        export_file(receipt, path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", True),
        ("contents", "occupied"),
        ("coordinate_frame", "WCS"),
        ("completed_at", "2026-10-05T12:00:00"),
        ("generation", True),
        ("source", {"credentials": "not supported"}),
        ("response_sha256", "0" * 64),
        ("slots", [{"number": 1, "position_mm": [0, 0, 0]}]),
    ],
)
def test_rehashed_corrupt_semantics_cannot_import(receipt, field, value):
    envelope = copy.deepcopy(bundle(receipt))
    envelope["payload"][field] = value
    envelope["payload_sha256"] = digest(envelope["payload"])
    with pytest.raises(ValueError):
        decode(canonical(envelope))


def test_corruption_duplicate_fields_and_size_limits(receipt):
    value = bundle(receipt)
    value["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        decode(json.dumps(value).encode())
    with pytest.raises(ValueError):
        decode(b'{"payload":{},"payload":{}}')
    with pytest.raises(ValueError, match="size"):
        decode(b" " * (MAX_BYTES + 1))
