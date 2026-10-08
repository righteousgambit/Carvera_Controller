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


def test_bench_separates_scope_updates_live_freshness_and_reuses_unchanged_cards(tmp_path, monkeypatch):
    from carveracontroller import desktop_calibration_bench

    source, store, assembly = comparison(tmp_path)
    # Test packet age explicitly; rendering time must not expire the synthetic
    # packet during scope navigation on a loaded hosted runner.
    clock = [source.workspace.machine.controller.observed_pose.timestamp + 0.1]
    monkeypatch.setattr(desktop_calibration_bench, "time", SimpleNamespace(monotonic=lambda: clock[0]))
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
    clock[0] += 10
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
    bench.section.text = "Latest report"
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


def test_trend_selects_exact_receipts_filters_metric_and_preserves_unchanged_view(tmp_path):
    source, store, assembly = comparison(tmp_path)
    before = store.path.read_bytes()
    bench = CalibrationBench(source)
    chart = bench.trend
    assert len(chart.plot.points) == 2 and chart.plot.segments == []
    chart.group.text = next(iter(chart.groups))
    assert chart.plot.segments == [(0, 1)]
    chart.select(0)
    assert chart.previous.disabled and not chart.following.disabled
    chart.step(1)
    assert chart.index == 1 and chart.following.disabled
    chart.step(-1)
    assert chart.index == 0 and "Applied TLO: 28 mm" in chart.detail.text
    assert bench._rows[0]["receipt"]["id"] in chart.detail.text
    assert "Raw samples: 28, 28.01" in chart.detail.text
    chart.metric.text = "Computed sample range"
    assert chart.plot.points[0]["value_mm"] == pytest.approx(0.01)
    selected = chart.index
    bench.refresh()
    assert chart.index == selected
    assert store.path.read_bytes() == before
    source.workspace.machine.controller.executeCommand.assert_not_called()


def test_trend_pages_all_receipts_and_accepts_real_plot_selection(tmp_path):
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch
    from kivy.uix.floatlayout import FloatLayout

    from carveracontroller.desktop_calibration_trend import CalibrationTrend
    from carveracontroller.machine.calibration_bench import sample_statistics

    rows = [
        {
            "revision_id": "revision",
            "previous_receipt_id": f"r{i - 1}" if i else None,
            "applied_change_mm": 0.01 if i else None,
            "statistics": sample_statistics({"measurements": [28], "applied": 28 + i * 0.01}),
            "receipt": {
                "id": f"r{i}",
                "endpoint": "machine",
                "tool_number": 1,
                "report": {"timestamp": 100 + i, "measurements": [28]},
            },
        }
        for i in range(130)
    ]
    chart = CalibrationTrend(size_hint=(None, None), width=400)
    host = FloatLayout()
    host.add_widget(chart)
    Window.add_widget(host)
    try:
        chart.show(rows)
        pump_frames(5)
        assert chart.start == 70 and len(chart.plot.points) == 60
        chart.page(-1)
        assert chart.start == 10
        chart.page(-1)
        assert chart.start == 0 and chart.older.disabled
        touch = UnitTestTouch(chart.plot.x + 12, chart.plot.center_y)
        touch.scale_for_screen(Window.width, Window.height)
        assert chart.plot.on_touch_down(touch)
        assert chart.index == 0 and "Receipt r0" in chart.detail.text
        chart.page(1)
        chart.page(1)
        assert chart.newer.disabled and chart.start == 70
    finally:
        Window.remove_widget(host)


def test_new_receipts_preserve_selected_chart_context_and_sections_release_focus(tmp_path):
    source, store, assembly = comparison(tmp_path)
    bench = CalibrationBench(source)
    bench.trend.group.text = next(iter(bench.trend.groups))
    bench.trend.select(0)
    selected_id = bench._rows[0]["receipt"]["id"]
    event = store.capture(1, TloReport((28, 28.01), 0.01, 28.03, 102), "machine")
    store.link(event["id"], assembly["id"], "Operator attribution")
    before = store.path.read_bytes()
    bench.refresh()
    assert selected_id in bench.trend.detail.text
    assert bench.trend.index == 0 and len(bench.trend.plot.points) == 3
    bench.trend.metric.focus = True
    bench.section.text = "Latest report"
    assert not bench.trend.metric.focus
    assert bench.content.children == [bench.metrics]
    bench.section.text = "Receipt history"
    assert bench.content.children == [bench.history]
    bench.section.text = "Trends"
    assert selected_id in bench.trend.detail.text and bench.content.children == [bench.trend]
    assert store.path.read_bytes() == before
    source.workspace.machine.controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [400, 1200])
def test_trend_sections_render_at_narrow_and_wide_widths(tmp_path, width):
    from kivy.core.window import Window
    from kivy.uix.floatlayout import FloatLayout

    source, store, assembly = comparison(tmp_path)
    for index in range(2, 12):
        event = store.capture(1, TloReport((28, 28.01), 0.01, 28 + index * 0.002, 100 + index), "machine")
        store.link(event["id"], assembly["id"], "Synthetic chart rendering fixture")
    before = store.path.read_bytes()
    bench = CalibrationBench(source)
    bench.size_hint_x = None
    bench.width = width
    host = FloatLayout()
    host.add_widget(bench)
    Window.add_widget(host)
    try:
        bench.trend.group.text = next(iter(bench.trend.groups))
        pump_frames(8)
        assert bench.content.children == [bench.trend]
        assert bench.trend.plot.width > 0 and bench.trend.plot.right <= bench.right
        assert len(bench.trend.plot.points) == 12
        texture = bench.export_as_image().texture
        Image.frombytes("RGBA", texture.size, texture.pixels).save(tmp_path / f"calibration-trend-{width}.png")
        assert store.path.read_bytes() == before
        source.workspace.machine.controller.executeCommand.assert_not_called()
    finally:
        Window.remove_widget(host)


def test_session_local_duplicate_timestamps_do_not_alias_chart_selection(tmp_path):
    source, store, assembly = comparison(tmp_path)
    history = source.workspace.machine.tool_history
    history.add_report(1, TloReport((30,), 0, 30, 100))
    bench = CalibrationBench(source)
    bench.scope.text = "Selected tool number"
    bench.trend.select(1)
    history.add_report(1, TloReport((31,), 0, 31, 100))
    bench.refresh()
    assert bench.trend.index == 1 and "capture #2" in bench.trend.detail.text
    assert bench.trend.plot.segments == []
    assert "session-local" in bench.trend.detail.text
    source.workspace.machine.controller.executeCommand.assert_not_called()
