import json
import threading
import time
from types import SimpleNamespace

import pytest

from carveracontroller.machine.commissioning_capture import load_capture
from carveracontroller.machine.commissioning_compare import hal_differences
from carveracontroller.machine.commissioning_exchange import decode_comparison, read_comparison, write_comparison
from carveracontroller.machine.slot_exchange import canonical, digest
from tests.unit.test_linuxcnc_hal import make_capture, parameter_module


def saved(tmp_path):
    api = parameter_module()
    path = make_capture(tmp_path, api)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    lines[1]["hal"]["parameters"][0]["value"] = 150.5
    path.write_text("\n".join(json.dumps(line) for line in lines))
    capture = load_capture(path)
    target = tmp_path / "review.cvcompare"
    result = write_comparison(capture, 0, 1, "HAL parameters", target)
    return capture, target, result


def test_portable_receipt_roundtrip_preserves_entire_capture_and_recomputes_changes(tmp_path):
    capture, target, result = saved(tmp_path)
    assert result.capture.sha256 == capture.sha256
    assert result.raw_capture == open(capture.source, "rb").read()
    changes, _ = hal_differences(result.capture.hal_observations[0], result.capture.hal_observations[1], result.group)
    assert "raw delta +30.0" in changes[0].summary()
    result2 = write_comparison(
        result.capture,
        result.reference,
        result.selected,
        result.group,
        tmp_path / "second.cvcompare",
        result.raw_capture,
    )
    assert result2.capture.sha256 == capture.sha256
    previous = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_comparison(capture, 0, 1, "HAL parameters", target)
    assert target.read_bytes() == previous


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_available", True),
        ("reference", True),
        ("selected", 100),
        ("capture_sha256", "0" * 64),
        ("schema", True),
        ("kind", "live_tuning"),
        ("group", "Analog inputs"),
        ("saved_at", "2026-10-06T00:00:00"),
        ("saved_at", "x" * 129),
    ],
)
def test_forged_rehashed_semantics_reject(tmp_path, field, value):
    _, target, _ = saved(tmp_path)
    record = json.loads(target.read_bytes())
    record["payload"][field] = value
    record["payload_sha256"] = digest(record["payload"])
    with pytest.raises(ValueError):
        decode_comparison(canonical(record), "forged")


def test_payload_tampering_source_changes_and_oversize_reject(tmp_path, monkeypatch):
    import carveracontroller.machine.commissioning_exchange as exchange

    capture, target, _ = saved(tmp_path)
    record = json.loads(target.read_bytes())
    record["payload"]["selected"] = 0
    with pytest.raises(ValueError, match="digest"):
        decode_comparison(canonical(record), "tampered")
    from pathlib import Path

    Path(capture.source).write_text("changed")
    with pytest.raises(ValueError, match="changed since import"):
        write_comparison(capture, 0, 1, "HAL parameters", tmp_path / "changed.cvcompare")
    assert not (tmp_path / "changed.cvcompare").exists()
    monkeypatch.setattr(exchange, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="64 MiB"):
        read_comparison(target)


def wait_idle(panel):
    from kivy.clock import Clock

    end = time.monotonic() + 3
    while panel.busy and time.monotonic() < end:
        Clock.tick()
        time.sleep(0.005)
    assert not panel.busy


@pytest.mark.parametrize("width", [360, 650])
def test_background_open_save_restore_reference_and_clear_rejects_late_delivery(tmp_path, width):
    from kivy.clock import Clock
    from kivy.uix.floatlayout import FloatLayout

    from carveracontroller.desktop_commissioning import CommissioningPanel

    capture, target, _ = saved(tmp_path)
    paths = []

    def choose(callback, **kwargs):
        paths.append(kwargs)
        callback(str(tmp_path / "UI-export.cvcompare" if kwargs.get("save") else target))

    panel = CommissioningPanel(SimpleNamespace(choose_profile_file=choose))
    root = FloatLayout(size_hint=(None, None), size=(width, 2000))
    root.add_widget(panel)
    panel.width = width
    try:
        panel.open_comparison()
        wait_idle(panel)
        assert panel.cursor == 1 and panel.reference_cursor == 0
        assert panel.hal_mode.text == "Changed since reference"
        assert "raw delta +30.0" in panel.channel_values.text
        assert "Historical comparison" in panel.storage_note.text
        panel.save_comparison()
        wait_idle(panel)
        assert "Saved and read back" in panel.storage_note.text
        assert read_comparison(tmp_path / "UI-export.cvcompare").capture.sha256 == capture.sha256
        entered, release = threading.Event(), threading.Event()
        delivered = []

        def held():
            entered.set()
            release.wait(2)
            return "late"

        panel.storage_job(held, delivered.append)
        assert entered.wait(1)
        panel.clear()
        release.set()
        for _ in range(10):
            Clock.tick()
            time.sleep(0.005)
        assert not delivered and panel.capture is None and not panel.comparison_raw
        assert not panel.storage_note.text
        assert paths[0]["extension"] == ".cvcompare" and paths[1]["save"] is True
    finally:
        panel.clear()
        root.remove_widget(panel)


def test_failed_import_preserves_existing_review(tmp_path):
    from carveracontroller.desktop_commissioning import CommissioningPanel

    capture, target, _ = saved(tmp_path)
    panel = CommissioningPanel(SimpleNamespace(choose_profile_file=lambda callback, **kwargs: callback(str(target))))
    try:
        panel.open_comparison()
        wait_idle(panel)
        previous = (panel.capture, panel.comparison_raw, panel.cursor, panel.reference_cursor)
        target.write_text("invalid comparison")
        panel.open_comparison()
        wait_idle(panel)
        assert (panel.capture, panel.comparison_raw, panel.cursor, panel.reference_cursor) == previous
        assert "existing review retained" in panel.storage_note.text
        assert panel.capture.sha256 == capture.sha256
        assert not panel.export_comparison_button.disabled
    finally:
        panel.clear()


def test_partial_capture_is_not_promoted_to_complete_by_export(tmp_path):
    capture, _, _ = saved(tmp_path)
    from pathlib import Path

    path = Path(capture.source)
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:2]))
    partial = load_capture(path)
    assert not partial.complete
    result = write_comparison(partial, 0, 1, "HAL parameters", tmp_path / "partial.cvcompare")
    assert not result.capture.complete
    assert result.capture.sha256 == partial.sha256
