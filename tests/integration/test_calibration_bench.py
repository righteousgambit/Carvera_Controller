import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PIL import Image, PngImagePlugin

from carveracontroller.desktop_calibration_bench import CalibrationBench, open_calibration_bench
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport, ToolHistory
from tests.integration.conftest import pump_frames


def comparison(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Measured cutter", "Collet", 28)
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=99):
        store.assign("machine", 1, assembly["id"])
    for index in range(2):
        event = store.capture(1, TloReport((28, 28.01), 0.01, 28 + index * 0.01, 100 + index), "machine")
        store.link(event["id"], assembly["id"], "Operator's setup record")
    history = ToolHistory()
    history.add_report(1, TloReport((30, 30.02), 0.02, 30.02, 100))
    controller = SimpleNamespace(
        connection_address="machine",
        observed_pose=ObservedPose(time.monotonic(), "Idle", (0, 0, 0), (0, 0, 0), 1, 28.01),
        executeCommand=Mock(),
    )
    ws = SimpleNamespace(
        connected=True,
        selected_machine_profile={"id": "machine"},
        machine=SimpleNamespace(controller=controller, tool_history=history),
    )
    custody = SimpleNamespace(store=store, selected_id=assembly["id"], selected=lambda: store.assembly(assembly["id"]))
    return SimpleNamespace(workspace=ws, custody=custody, selected=1), store, assembly


def test_bench_separates_scope_updates_live_freshness_and_reuses_unchanged_cards(tmp_path):
    source, store, assembly = comparison(tmp_path)
    bench = CalibrationBench(source)
    assert "current revision" in bench.identity.text
    assert "2 reports" in bench.history.text and "comparable change 0.01 mm" in bench.history.text
    assert "28.01 mm" in bench.observed.text and "fresh status" in bench.observed.text
    assert "within 0.001 mm comparison" in bench.observed.text
    source.workspace.selected_machine_profile = {"id": "other-machine"}
    bench.refresh()
    assert "no post-placement controller receipt" in bench.observed.text
    source.workspace.selected_machine_profile = {"id": "machine"}
    bench.refresh()
    assert "within 0.001 mm comparison" in bench.observed.text
    cards = list(bench.metrics.children)
    source.custody.selected = Mock(side_effect=AssertionError("Unchanged heartbeat copied custody history"))
    bench.refresh()
    assert list(bench.metrics.children) == cards
    source.custody.selected = lambda: store.assembly(assembly["id"])
    source.workspace.machine.controller.observed_pose = ObservedPose(
        time.monotonic() - 10, "Idle", (0, 0, 0), (0, 0, 0), 1, 28.01
    )
    bench.refresh()
    assert "unavailable" in bench.observed.text
    assert list(bench.metrics.children) == cards
    bench.scope.text = "Selected tool number"
    assert "session-local" in bench.identity.text and "1 reports" in bench.history.text
    assert "30.02 mm" in bench.history.text and "comparable change Unknown" in bench.history.text
    bench.scope.text = "Selected assembly"
    store.revise(assembly["id"], assembly["id"], "Reseated cutter", "Collet", 29, "", "Changed seating")
    bench.refresh()
    assert "Reseated cutter" in bench.identity.text
    assert assembly["id"][:8] in bench.history.text  # Old receipt revision is retained.
    source.workspace.machine.controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [400, 1200])
def test_bench_metrics_reflow_and_preserve_raw_samples(tmp_path, width):
    source, store, assembly = comparison(tmp_path)
    before = store.path.read_bytes()
    bench = CalibrationBench(source)
    bench.size_hint_x = None
    bench.width = width
    pump_frames(8)
    assert bench.metrics.cols == (1 if width == 400 else 2)
    assert all(card.width > 0 and card.right <= bench.right for card in bench.metrics.children)
    assert "Samples: 28, 28.01" in bench.history.text
    assert "not seating diagnoses" in bench.history.text
    assert PngImagePlugin is not None and "PNG" in Image.SAVE
    rendered = bench.export_as_image().texture
    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
        tmp_path / f"calibration-bench-{width}.png", format="PNG"
    )
    assert store.path.read_bytes() == before
    source.workspace.machine.controller.executeCommand.assert_not_called()


def test_bench_opens_from_actual_comparison_and_cancels_refresh_on_close(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    source, store, assembly = comparison(tmp_path)
    monkeypatch.setattr(ws.machine, "_tool_custody", store, raising=False)
    monkeypatch.setattr(ws.machine, "tool_history", source.workspace.machine.tool_history)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    comparison_panel = ws.tool_comparison
    comparison_panel.selected = 1
    comparison_panel.custody.selected_id = assembly["id"]
    before = store.path.read_bytes()
    comparison_panel.open_calibration_bench()
    bench = comparison_panel.calibration_bench
    popup = comparison_panel.custody.popup
    try:
        pump_frames(8)
        assert popup._is_open and bench.refresh_event.is_triggered
        assert "Measured cutter" in bench.identity.text and "2 reports" in bench.history.text
        comparison_panel.custody.popup_apply()
        assert not bench.refresh_event.is_triggered
        pump_frames(12, sleep=0.03)
        assert not popup._is_open and not bench.refresh_event.is_triggered
        assert store.path.read_bytes() == before
        send.assert_not_called()
    finally:
        popup.dismiss()
        comparison_panel.custody.selected_id = None
        comparison_panel.selected = None


def test_legacy_invalid_samples_and_large_reports_remain_visible_and_bounded(tmp_path):
    source, store, assembly = comparison(tmp_path)
    history = source.workspace.machine.tool_history
    history.add_report(1, TloReport((True, "invalid", float("nan")), 0, None, 102))
    bench = CalibrationBench(source)
    bench.scope.text = "Selected tool number"
    assert "True, 'invalid', nan" in bench.history.text
    assert "Computed range Unknown" in bench.history.text
    history.add_report(1, TloReport(tuple(float(i) for i in range(100)), 99, 28, 103))
    bench.refresh()
    assert "80 more retained in raw receipt" in bench.history.text
    assert bench._rows[-1]["statistics"]["count"] == 100
    assert len(history.record(1).latest.measurements) == 100
    source.workspace.machine.controller.executeCommand.assert_not_called()
