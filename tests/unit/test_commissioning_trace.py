from dataclasses import replace
from types import SimpleNamespace

import pytest

from carveracontroller.machine.commissioning_trace import joint_trace
from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader
from tests.unit.test_linuxcnc_status import Status


def observations(count=3):
    base = LinuxCNCStatusReader("test", Status()).poll(10.0)
    return tuple(
        replace(
            base,
            observed_at=10 + index * index / 10,
            sequence=index + 1,
            joints=(
                replace(base.joints[0], commanded=index * 2.0, actual=index * 1.5, following_error=0.5, velocity=-3.0),
                base.joints[1],
            ),
        )
        for index in range(count)
    )


def test_trace_retains_every_sample_raw_units_and_nonuniform_times():
    rows = observations()
    trace = joint_trace(rows, 1, 0, "Command / feedback")
    assert trace.names == ("Commanded", "Actual")
    assert [point.values for point in trace.points] == [(0, 0), (2, 1.5), (4, 3)]
    assert [point.elapsed for point in trace.points] == pytest.approx([0, 0.1, 0.4])
    assert trace.segments == ((0, 1), (1, 2))
    assert "raw units" in trace.unit and "per mm" in trace.unit
    assert joint_trace(rows, 1, 1, "Velocity").unit.endswith("per degree)/s")
    assert joint_trace(rows, 1, 0, "Following error").points[0].values == (0.5,)
    assert joint_trace(rows, 1, 0, "Velocity").points[0].values == (-3,)


def test_bounded_pages_preserve_all_samples_and_final_partial_page():
    rows = observations(401)
    pages = [joint_trace(rows, index, 0, "Velocity") for index in (0, 200, 400)]
    assert [len(page.points) for page in pages] == [200, 200, 1]
    assert [point.sample for page in pages for point in page.points] == list(range(401))
    assert (pages[-1].first, pages[-1].last, pages[-1].total) == (400, 401, 401)
    assert joint_trace(rows, 999, 0, "Velocity") == pages[-1]


@pytest.mark.parametrize("change", ["missing", "unit", "kind", "topology", "generation", "clock"])
def test_trace_never_bridges_a_missing_or_incompatible_sample(change):
    rows = list(observations())
    middle = rows[1]
    if change == "missing":
        middle = replace(middle, joints=())
    elif change == "unit":
        middle = replace(middle, joints=(replace(middle.joints[0], units_per_mm_or_degree=1.0), middle.joints[1]))
    elif change == "kind":
        middle = replace(middle, joints=(replace(middle.joints[0], kind="angular"), middle.joints[1]))
    elif change == "topology":
        middle = replace(middle, axis_mask=7)
    elif change == "generation":
        middle = replace(middle, generation=1)
    else:
        middle = replace(middle, observed_at=rows[0].observed_at)
    rows[1] = middle
    trace = joint_trace(tuple(rows), 0, 0, "Command / feedback")
    assert (0, 1) not in trace.segments
    if change != "clock":
        assert trace.segments == ()


def test_missing_joint_empty_capture_and_invalid_selection():
    assert not joint_trace(observations(), 0, 50, "Velocity").points
    assert joint_trace((), 0, 0, "Velocity").total == 0
    for cursor, joint, metric in ((True, 0, "Velocity"), (0, False, "Velocity"), (0, 0, "Effort")):
        with pytest.raises(ValueError):
            joint_trace(observations(), cursor, joint, metric)


def test_plot_selects_by_elapsed_time_and_clear_releases_data():
    pytest.importorskip("kivy")
    from carveracontroller.desktop_commissioning_trace import JointTracePlot

    selected = []
    plot = JointTracePlot(selected.append, pos=(0, 0), size=(224, 170))
    trace = joint_trace(observations(), 0, 0, "Command / feedback")
    plot.show(trace, 0)
    # Half the plotted time range is closer to sample 1 (0.1 s) than sample 2 (0.4 s).
    assert plot.on_touch_down(SimpleNamespace(pos=(112, 80), x=112))
    assert selected == [1]
    plot.show(None, 0)
    assert plot.trace is None


def test_panel_trace_page_and_metric_controls_do_not_mutate_machine():
    pytest.importorskip("kivy")
    from carveracontroller.desktop_commissioning import CommissioningPanel

    rows = observations(401)
    capture = SimpleNamespace(
        observations=rows,
        transitions=tuple(() for _ in rows),
        utc_times=("2026-10-06T10:00:00Z",) * 401,
        complete=True,
        failure="",
        sha256="a" * 64,
        ini_sha256="b" * 64,
    )
    from kivy.core.window import Window

    from tests.integration.conftest import pump_frames

    panel = CommissioningPanel(SimpleNamespace(), size_hint_x=None, width=360)
    Window.add_widget(panel)
    try:
        panel.deliver(0, capture, None)
        pump_frames(8)
        assert panel.trace_older.disabled and not panel.trace_newer.disabled
        panel.trace_newer.dispatch("on_release")
        assert panel.cursor == 200 and panel.trace_plot.trace.first == 200
        panel.trace_newer.dispatch("on_release")
        assert panel.cursor == 400 and panel.trace_newer.disabled
        panel.trace_choice.text = "Velocity"
        assert panel.trace_plot.trace.names == ("Velocity",)
        assert "raw units" in panel.trace_note.text
        panel.trace_choice.is_open = True
        panel.clear()
        assert not panel.trace_choice.is_open and panel.trace_plot.trace is None
    finally:
        Window.remove_widget(panel)
