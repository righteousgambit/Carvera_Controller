"""Complete-prefix and partial-sweep material, including every repeated stock."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.machine.contact_pose_view import prepare_path_pose_view
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_playback_material import ProgramMaterialCursor, prepare_program_material
from carveracontroller.machine.program_stock_evolution import review_stock_evolution
from carveracontroller.machine.program_surface_clearance import review_program_surfaces
from carveracontroller.machine.scene_joint_clearance import capture_scene_clearance
from tests.unit.test_program_stock_evolution import stock_example
from tests.unit.test_scene_joint_clearance import scene_viewer


def frame(report, index, sample, **kwargs):
    view = prepare_path_pose_view(report, int(report.body_review.segments[index].tool_id), index, sample)
    return prepare_program_material(report, view, **kwargs)


@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("rotation,tilt", [(0, (0, 0)), (31, (20, -10))])
def test_partial_remaining_matches_independent_full_prefix_sweeps_and_final_history(repeat, rotation, tilt):
    _, _, report, _ = stock_example(ball=True, rotation=rotation, tilt=tilt, repeat=repeat)
    material = frame(report, 1, F(1, 2))
    inputs = report.stock_evolution.inputs
    assert set(material.snapshots) == set(inputs.stocks)
    for name, (offset, snapshot) in inputs.stocks.items():
        stock = StockVolume.from_snapshot(snapshot)
        segment = report.body_review.segments[1]
        end = segment.start + (segment.end - segment.start).scaled(0.5)
        stock.subtract(
            SweptTool(segment.start - Vec3(*offset), end - Vec3(*offset), inputs.tools[int(segment.tool_id)])
        )
        assert dict(material.snapshots[name]) == stock.snapshot()
        assert material.remaining_mm3[name] == stock.remaining_volume_mm3
    assert [b.name for b in material.view.bodies if b.kind == "remaining"] == list(inputs.stocks)
    assert not any(b.kind == "cad" and b.name in inputs.stocks for b in material.view.bodies)
    final = frame(report, len(report.body_review.segments) - 1, F(1))
    assert final.snapshots == report.stock_evolution.final_snapshots


def test_cursor_partial_never_commits_incomplete_prefix_and_backwards_seek_rebuilds():
    _, _, report, _ = stock_example(ball=True, repeat=True)
    cursor = ProgramMaterialCursor(report)
    for index, sample in (
        (1, F(1, 2)),
        (1, F(3, 4)),
        (1, F(1)),
        (3, F(1, 2)),
        (0, F(0)),
        (len(report.body_review.segments) - 1, F(1)),
    ):
        cached = frame(report, index, sample, cursor=cursor)
        assert cached.view == frame(report, index, sample).view
        assert cached.snapshots == frame(report, index, sample).snapshots
        assert cursor.next_move == index + (sample == 1)


def test_history_work_cancellation_and_source_mismatch_withhold_complete_frame():
    _, _, report, _ = stock_example()
    cursor = ProgramMaterialCursor(report)
    accepted = frame(report, 1, F(1), cursor=cursor)
    checkpoint = cursor.checkpoint
    with pytest.raises(ValueError, match="work budget"):
        frame(report, 2, F(1), cursor=cursor, max_cell_work=1)
    with pytest.raises(InterruptedError):
        frame(report, 2, F(1), cursor=cursor, cancelled=lambda: True)
    assert cursor.checkpoint is checkpoint and cursor.next_move == 2
    corrupt = replace(
        report,
        stock_evolution=replace(
            report.stock_evolution, steps=tuple(replace(s, remaining_mm3=999) for s in report.stock_evolution.steps)
        ),
    )
    with pytest.raises(ValueError, match="history"):
        frame(corrupt, 1, F(1, 2))
    with pytest.raises(ValueError, match="source"):
        prepare_program_material(report, replace(accepted.view, source_sha256="other"))


def test_uncertified_curve_partial_and_full_sweeps_retain_complete_material():
    _, _, report, _ = stock_example(ball=True)
    body = replace(report.body_review, curve_enclosures=((5, "G2", 0.01),))
    history = review_stock_evolution(body, report.stock_evolution.inputs, report.rotating_envelopes)
    report = replace(report, body_review=body, stock_evolution=history)
    for sample in (F(1, 2), F(1)):
        material = frame(report, 1, sample)
        assert sum(material.remaining_mm3.values()) == 8
        assert all(
            s["occupancy_sha256"] == history.final_snapshots[n]["occupancy_sha256"]
            for n, s in material.snapshots.items()
        )


def test_multiple_tool_profiles_replay_shared_stock_and_select_matching_assembly():
    source, offsets, report, captures = stock_example(ball=True)
    first = captures[1]
    second = replace(first.definition, number=2, tool_type=ToolType.FLAT_END_MILL)
    viewer = scene_viewer()
    viewer.machine_setup = first.setup
    viewer.library_tool_table_mm = {1: first.definition, 2: second}
    captures[2] = capture_scene_clearance(
        first.profile,
        first.components,
        first.setup,
        first.placement,
        second,
        2,
        None,
        capture_context(viewer, None, verify_assets=False),
    )
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nT2 M6\nG1 X0"))
    report = review_program_surfaces(source, captures, offsets, grouped=True, stock_resolution_mm=0.5)
    cursor = ProgramMaterialCursor(report)
    first_material = frame(report, 1, F(1), cursor=cursor)
    assert first_material.view.pose.tool == 1 and sum(first_material.remaining_mm3.values()) == 0.25
    final = frame(report, len(report.body_review.segments) - 1, F(1), cursor=cursor)
    assert final.view.pose.tool == 2 and sum(final.remaining_mm3.values()) == 0
    assert final.snapshots == report.stock_evolution.final_snapshots
    assert any(b.name == "T2 cutter" for b in final.view.bodies)
    assert not any(b.name == "T1 cutter" for b in final.view.bodies)


def test_shared_cell_limit_refuses_before_any_grid_allocation(monkeypatch):
    _, _, report, _ = stock_example()
    view = prepare_path_pose_view(report, 1, 1, F(1, 2))
    inputs = report.stock_evolution.inputs
    stock = next(iter(inputs.stocks))
    offset, snapshot = inputs.stocks[stock]
    changed = dict(snapshot, minimum=(0, 0, 0), maximum=(1000, 1000, 1000), resolution_mm=0.05)
    report = replace(
        report,
        stock_evolution=replace(report.stock_evolution, inputs=replace(inputs, stocks={stock: (offset, changed)})),
    )
    monkeypatch.setattr(
        StockVolume, "from_snapshot", lambda *a, **kw: pytest.fail("Allocated an over-budget stock grid")
    )
    with pytest.raises(ValueError, match="before grid allocation"):
        prepare_program_material(report, view)
