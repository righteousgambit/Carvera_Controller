"""Snapshot cancellation and integrity preserve the complete residual occupancy."""

import base64
import hashlib
import random
import zlib

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3


def stock():
    value = StockVolume(AABB(Vec3(0, 0, 0), Vec3(128, 128, 32)), 1)
    rng = random.Random(308)
    value._occupied = bytearray(rng.randrange(2) for _ in value._occupied)
    value._remaining_count = sum(value._occupied)
    return value


def cancellation(stop):
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] >= stop

    return cancelled, calls


@pytest.mark.parametrize("stop", [1, 3, 5, 8, 10])
def test_cancel_export_keeps_original_cells_and_count(stop):
    value = stock()
    before = bytes(value._occupied), value.remaining_volume_mm3
    cancelled, calls = cancellation(stop)
    with pytest.raises(InterruptedError):
        value.snapshot(cancelled=cancelled)
    assert calls[0] == stop
    assert (bytes(value._occupied), value.remaining_volume_mm3) == before


@pytest.mark.parametrize("stop", [1, 3, 5, 10, 15])
def test_cancel_import_keeps_supplied_snapshot(stop):
    value = stock()
    snapshot = value.snapshot()
    before = dict(snapshot)
    cancelled, calls = cancellation(stop)
    with pytest.raises(InterruptedError):
        StockVolume.from_snapshot(snapshot, cancelled=cancelled)
    assert calls[0] == stop
    assert snapshot == before


def test_complete_streamed_snapshot_matches_previous_encoding_and_large_roundtrip():
    value = stock()
    raw = bytes(value._occupied)
    encoded = value.snapshot(cancelled=lambda: False)
    assert encoded["occupancy_zlib_base64"] == base64.b64encode(zlib.compress(raw)).decode("ascii")
    assert encoded["occupancy_sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(base64.b64decode(encoded["occupancy_zlib_base64"])) > 65536
    restored = StockVolume.from_snapshot(encoded, cancelled=lambda: False)
    assert bytes(restored._occupied) == raw
    assert restored.remaining_volume_mm3 == value.remaining_volume_mm3
    assert restored.snapshot() == encoded


@pytest.mark.parametrize("corruption", ["trailing", "member", "overflow", "invalid", "truncated", "digest"])
def test_integrity_limits_remain_enforced_across_chunks(corruption):
    value = stock()
    snapshot = value.snapshot()
    payload = base64.b64decode(snapshot["occupancy_zlib_base64"])
    if corruption == "trailing":
        payload += b"garbage"
    elif corruption == "member":
        payload += zlib.compress(b"extra")
    elif corruption == "overflow":
        payload = zlib.compress(bytes(value._occupied) + b"\x01")
    elif corruption == "invalid":
        payload = zlib.compress(b"\x02" + bytes(value._occupied)[1:])
    elif corruption == "truncated":
        payload = payload[:-3]
    else:
        snapshot["occupancy_sha256"] = "bad"
    snapshot["occupancy_zlib_base64"] = base64.b64encode(payload).decode("ascii")
    with pytest.raises(ValueError):
        StockVolume.from_snapshot(snapshot, cancelled=lambda: False)
