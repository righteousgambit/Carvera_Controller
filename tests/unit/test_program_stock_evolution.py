"""Independent ordered-material controls, datum binding and portable recomputation."""

import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_stock_evolution import (
    evolution_record,
    input_record,
    restore_inputs,
    review_stock_evolution,
)
from carveracontroller.machine.program_surface_archive import (
    STOCK_GROUP_METHOD,
    STOCK_METHOD,
    load_surface_review,
    save_surface_review,
    surface_report_record,
)
from carveracontroller.machine.program_surface_clearance import review_program_surfaces
from carveracontroller.machine.repeat_parts import RepeatPartPlan, StockInstance
from carveracontroller.machine.scene_joint_clearance import capture_scene_clearance
from tests.unit.test_scene_joint_clearance import capture, scene_viewer


def stock_example(*, grouped=True, ball=False, rotation=0, tilt=(0, 0), repeat=False, resolution=0.5):
    viewer = scene_viewer()
    viewer.machine_setup = MachineSetup(
        work_offset_mm=(-9, -5, -10),
        stock_origin_mm=(-1, -1, 0),
        stock_size_mm=(2, 2, 2),
        stock_rotation_deg=rotation,
        stock_tilt_deg=tilt,
    )
    viewer.library_tool_table_mm[1] = ToolDefinition(
        1,
        ToolType.BALL_END_MILL if ball else ToolType.FLAT_END_MILL,
        diameter=4,
        shank_diameter=4,
        flute_length=3,
        stickout=6,
    )
    text = "G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG0 X1\nG1 X0 F100\nG0 X1"
    offsets = {"G54": viewer.machine_setup.work_offset_mm}
    if repeat:
        viewer.repeat_stock_plan = RepeatPartPlan(
            (
                StockInstance("First", "G54", (-9, -5, -10), (-1, -1, 0), (2, 2, 2)),
                StockInstance("Second", "G55", (-19, -5, -10), (-1, -1, 0), (2, 2, 2)),
            )
        )
        offsets["G55"] = (-19, -5, -10)
        text += "\nG55\nG0 X0 Y0 Z0\nG1 X1\nG0 X0"
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(text))
    captures = {1: capture(viewer)}
    report = review_program_surfaces(source, captures, offsets, grouped=grouped, stock_resolution_mm=resolution)
    return source, offsets, report, captures


@pytest.mark.parametrize("ball", [False, True])
@pytest.mark.parametrize("rotation", [0, 31])
def test_contact_before_cut_and_no_material_on_later_rapid(ball, rotation):
    _, _, report, _ = stock_example(ball=ball, rotation=rotation)
    evolution = report.stock_evolution
    assert evolution is not None
    before, cutting, after = evolution.steps
    assert before.line == 4 and before.before_mm3 == pytest.approx(8)
    assert before.contacts and all(c.component == "cutter" for c in before.contacts)
    assert before.removed_mm3 == 0
    assert cutting.line == 5 and cutting.contacts == ()
    if ball:
        # Independent spherical lower-cap geometry at every original cell center.
        from math import cos, radians, sin

        angle = radians(rotation)
        remaining = 0
        for x in (-0.75, -0.25, 0.25, 0.75):
            for y in (-0.75, -0.25, 0.25, 0.75):
                px, py = x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)
                dx = px - min(1, max(0, px))
                for z in (0.25, 0.75, 1.25, 1.75):
                    remaining += dx * dx + py * py + (z - 2) ** 2 > 4
        assert cutting.remaining_mm3 == remaining * 0.125 > 0
        assert cutting.removed_mm3 == 8 - remaining * 0.125
        assert after.contacts
    else:
        assert cutting.removed_mm3 == pytest.approx(8) and cutting.remaining_mm3 == 0
        assert after.contacts == ()
    assert after.line == 6 and after.remaining_mm3 == cutting.remaining_mm3
    assert report.rotating and report.meshes[1]["stock G54 · Current stock"].triangles
    assert report.body_review.uncovered_lines and report.body_review.tool_change_lines
    assert "empty cells do not prove clearance" in evolution.qualification


def test_repeat_datums_evolve_all_instances_without_frame_cross_contamination():
    _, _, report, _ = stock_example(repeat=True)
    evolution = report.stock_evolution
    names = tuple(evolution.inputs.stocks)
    assert len(names) == 2
    first_cut = [s for s in evolution.steps if s.line == 5]
    assert [s.removed_mm3 for s in first_cut] == [8, 0]
    second_cut = [s for s in evolution.steps if s.line == 9]
    assert [s.removed_mm3 for s in second_cut] == [0, 8]
    assert all(s.remaining_mm3 == 0 for s in evolution.steps[-2:])


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("ball", [False, True])
def test_complete_source_geometry_material_history_replay_and_resave(tmp_path, grouped, ball):
    source, offsets, report, _ = stock_example(grouped=grouped, ball=ball)
    path = tmp_path / "ordered.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    raw = path.read_bytes()
    assert json.loads(raw)["method"] == (STOCK_GROUP_METHOD if grouped else STOCK_METHOD)
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(report))
    save_surface_review(path, loaded.source, loaded.work_offsets, loaded.report)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "change", ["offset", "tool", "initial", "final", "volume", "method", "missing", "bool", "extra"]
)
def test_rehashed_material_evidence_is_recomputed_and_bound(tmp_path, change):
    source, offsets, report, _ = stock_example(ball=True)
    path = tmp_path / "tampered.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    payload = json.loads(path.read_bytes())
    name = next(iter(payload["stock"]["stocks"]))
    if change == "offset":
        payload["stock"]["stocks"][name]["offset_mm"][0] += 1
    elif change == "tool":
        payload["stock"]["tools"]["1"]["diameter_mm"] = 3
    elif change == "initial":
        payload["stock"]["stocks"][name]["initial"]["occupancy_sha256"] = "0" * 64
    elif change == "final":
        payload["report"]["ordered_stock"]["final"][name]["occupancy_sha256"] = "0" * 64
    elif change == "volume":
        payload["report"]["ordered_stock"]["steps"][0]["remaining_mm3"] = 0
    elif change == "method":
        payload["method"] = "c1-declared-quadric-rotating-groups-surfaces-solids-v9"
    elif change == "missing":
        payload["stock"]["stocks"].pop(name)
    elif change == "bool":
        payload["stock"]["tools"]["1"]["diameter_mm"] = True
    else:
        payload["stock"]["tools"]["1"]["unrelated"] = 1
    payload.pop("sha256")
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    path.write_bytes(encoded(payload))
    with pytest.raises(ValueError):
        load_surface_review(path)


def test_selected_operation_cannot_invent_prior_material_history():
    source, offsets, _report, captures = stock_example()
    with pytest.raises(ValueError, match="preceding material history"):
        review_program_surfaces(source, captures, offsets, start_line=5, stock_resolution_mm=0.5)


def test_curve_enclosure_retains_material_without_certifying_chord_removal():
    _, _, report, _ = stock_example()
    body = replace(report.body_review, curve_enclosures=((5, "G2", 0.01),))
    result = review_stock_evolution(body, report.stock_evolution.inputs, report.rotating_envelopes)
    assert result.steps[1].state == "curve material retained"
    assert result.steps[1].removed_mm3 == 0 and result.steps[-1].remaining_mm3 == 8
    assert result.steps[1].contacts and result.steps[-1].contacts


def test_budget_and_cancellation_never_publish_partial_or_mutate_initial():
    _, _, report, _ = stock_example()
    inputs = report.stock_evolution.inputs
    before = encoded(input_record(inputs))
    with pytest.raises(ValueError, match="no partial report"):
        review_stock_evolution(report.body_review, inputs, report.rotating_envelopes, max_cell_work=1)
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 12

    with pytest.raises(InterruptedError):
        review_stock_evolution(report.body_review, inputs, report.rotating_envelopes, cancelled=cancelled)
    assert encoded(input_record(inputs)) == before


def test_shared_cell_budget_rejects_oversized_replay_before_grid_allocation(monkeypatch):
    _, _, report, _ = stock_example()
    record = input_record(report.stock_evolution.inputs)
    snapshot = next(iter(record["stocks"].values()))["initial"]
    snapshot["maximum"] = (100, 100, 100)
    snapshot["resolution_mm"] = 0.05
    from carveracontroller.addons.manufacturing_simulation import StockVolume

    monkeypatch.setattr(StockVolume, "from_snapshot", lambda *a, **kw: pytest.fail("Allocated over-budget grid"))
    with pytest.raises(ValueError, match="shared two-million-cell"):
        review_stock_evolution(report.body_review, restore_inputs(record), report.rotating_envelopes)


def test_tilted_stock_datum_preserves_ordered_material_and_archive(tmp_path):
    source, offsets, report, _ = stock_example(tilt=(90, 0))
    assert [s.remaining_mm3 for s in report.stock_evolution.steps] == [8, 0, 0]
    assert next(iter(report.stock_evolution.inputs.stocks.values()))[1]["schema"] == 4
    path = tmp_path / "tilted.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    assert load_surface_review(path).report.stock_evolution.steps == report.stock_evolution.steps


def test_cutting_move_checks_shank_before_cutter_removal():
    _, _, report, _ = stock_example()
    body = report.body_review
    moves = tuple(
        replace(s, start=s.start + type(s.start)(0, 0, -3), end=s.end + type(s.end)(0, 0, -3)) for s in body.segments
    )
    result = review_stock_evolution(
        replace(body, segments=moves), report.stock_evolution.inputs, report.rotating_envelopes
    )
    assert result.steps[1].contacts and all(c.component == "shank" for c in result.steps[1].contacts)
    assert result.steps[1].remaining_mm3 == 8 and result.steps[1].removed_mm3 == 0


def test_exchange_cancellation_checks_complete_history_without_encoding_partial():
    _, _, report, _ = stock_example()
    with pytest.raises(InterruptedError, match="exchange cancelled"):
        evolution_record(report.stock_evolution, cancelled=lambda: True)


def test_imported_closed_cavity_cells_and_exact_faces_survive_detached_replay(tmp_path, monkeypatch):
    from tests.unit.test_stock_solid import box, mesh, reverse

    mesh_source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)) + reverse(box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5))))
    model = StockModel.load(mesh_source.source_path, "mm")
    viewer = scene_viewer()
    viewer.machine_setup = MachineSetup(
        work_offset_mm=(-9, -5, -10), stock_origin_mm=(-1, -1, 0), stock_size_mm=(2, 2, 2), stock_model=model
    )
    viewer.library_tool_table_mm[1] = ToolDefinition(
        1, ToolType.FLAT_END_MILL, diameter=4, shank_diameter=4, flute_length=3, stickout=6
    )
    source = ProgramClearanceSource.capture(
        ProgramOperations.from_text("G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG0 X1\nG1 X0 F100\nG0 X1")
    )
    offsets = {"G54": viewer.machine_setup.work_offset_mm}
    report = review_program_surfaces(source, {1: capture(viewer)}, offsets, grouped=True, stock_resolution_mm=0.5)
    assert [s.before_mm3 for s in report.stock_evolution.steps] == [7, 7, 0]
    assert report.stock_evolution.steps[1].removed_mm3 == 7
    assert len(report.meshes[1]["stock G54 · Current stock"].triangles) == 24
    path = tmp_path / "cavity.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    monkeypatch.setattr(
        StockModel, "from_reference", lambda *a, **kw: pytest.fail("Detached opening reread source CAD")
    )
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(report))


def test_ball_then_flat_tool_profiles_share_ordered_material_history():
    source, offsets, report, captures = stock_example(ball=True)
    first = captures[1]
    second = replace(first.definition, number=2, tool_type=ToolType.FLAT_END_MILL)
    viewer = scene_viewer()
    viewer.machine_setup = first.setup
    viewer.library_tool_table_mm = {1: first.definition, 2: second}
    context = capture_context(viewer, None, verify_assets=False)
    captures[2] = capture_scene_clearance(
        first.profile, first.components, first.setup, first.placement, second, 2, None, context
    )
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nT2 M6\nG1 X0"))
    result = review_program_surfaces(source, captures, offsets, grouped=True, stock_resolution_mm=0.5)
    steps = result.stock_evolution.steps
    assert steps[1].tool == 1 and steps[1].remaining_mm3 == 0.25
    assert steps[-1].tool == 2 and steps[-1].removed_mm3 == 0.25 and steps[-1].remaining_mm3 == 0
    assert set(result.stock_evolution.inputs.tools) == {1, 2} and 7 in result.body_review.tool_change_lines
