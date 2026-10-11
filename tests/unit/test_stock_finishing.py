"""Independent planned/candidate material controls, binding and bounded work."""

from dataclasses import replace

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_stock_evolution import evolution_record, review_stock_evolution
from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move, section_from_state
from carveracontroller.machine.program_surface_clearance import review_program_surfaces
from carveracontroller.machine.scene_joint_clearance import capture_scene_clearance
from carveracontroller.machine.stock_finishing import compare_stock_continuation
from tests.unit.test_program_stock_evolution import stock_example
from tests.unit.test_scene_joint_clearance import scene_viewer


def finishing_example(*, repeat=False, reverse=False, small=False, short=False):
    source, offsets, original, captures = stock_example(ball=not reverse, repeat=repeat)
    first = captures[1]
    second = replace(
        first.definition,
        number=2,
        tool_type=ToolType.BALL_END_MILL if reverse else ToolType.FLAT_END_MILL,
        diameter=1 if small else 4,
        shank_diameter=1 if small else 4,
        flute_length=1 if short else 3,
    )
    viewer = scene_viewer()
    viewer.machine_setup = first.setup
    viewer.library_tool_table_mm = {1: first.definition, 2: second}
    viewer.repeat_stock_plan = first.repeat_plan
    captures[2] = capture_scene_clearance(
        first.profile,
        first.components,
        first.setup,
        first.placement,
        second,
        2,
        first.repeat_plan,
        capture_context(viewer, None, verify_assets=False),
    )
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nT2 M6\nG0 X0\nG1 X1 F100"))
    return review_program_surfaces(source, captures, offsets, grouped=True, stock_resolution_mm=0.5)


def compare(report, *, index=0, tool=2, end=6, name=None, state=None, **kwargs):
    name = name or next(iter(report.stock_evolution.inputs.stocks))
    state = state or reconstruct_stock_move(
        report.body_review, report.stock_evolution, report.rotating_envelopes, name, index
    )
    return compare_stock_continuation(
        report.body_review,
        report.stock_evolution,
        report.rotating_envelopes,
        state,
        name,
        tool,
        end,
        **kwargs,
    )


def test_layer_and_plane_reuse_never_replays_prefix_again(monkeypatch):
    import carveracontroller.machine.program_stock_inspection as inspection

    _, _, report, _ = stock_example(ball=True)
    name = next(iter(report.stock_evolution.inputs.stocks))
    calls = 0
    original = inspection.review_stock_evolution

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(inspection, "review_stock_evolution", counted)
    state = reconstruct_stock_move(report.body_review, report.stock_evolution, report.rotating_envelopes, name, 1)
    assert calls == 2
    for plane in ("XY", "XZ", "YZ"):
        for layer in range(4):
            assert section_from_state(state, name, plane, layer).after_mm3 == 0.25
    assert calls == 2
    with pytest.raises(TypeError):
        state.after[name]["minimum"] = (0, 0, 0)


def test_ball_plan_vs_flat_tool_matches_independent_remaining_corner_cells():
    result = compare(finishing_example())
    assert result.initial_mm3 == 8
    assert result.planned.remaining_mm3 == 0.25 and result.planned.removed_mm3 == 7.75
    assert result.candidate.remaining_mm3 == 0 and result.candidate.removed_mm3 == 8
    assert result.extra_removed_mm3 == 0.25 and result.extra_remaining_mm3 == 0
    assert result.planned.contacts and all(c.line == 6 and c.tool == 1 for c in result.planned.contacts)
    assert result.candidate.contacts == ()
    assert all(c.contact.source_ratio is not None for c in result.planned.contacts)
    assert "not a nominal finished-part target" in result.qualification


def test_small_flat_leaves_independently_counted_side_material():
    result = compare(finishing_example(small=True))
    # Grid centers x=-.75,-.25,.25,.75; y=-.75,-.25,.25,.75.
    # Radius .5 removes three X columns and two Y rows through four Z layers.
    assert result.candidate.removed_mm3 == 3 and result.candidate.remaining_mm3 == 5
    assert result.extra_remaining_mm3 == 4.75 and result.extra_removed_mm3 == 0


def test_short_flutes_check_shank_against_remaining_stock_before_cutting():
    result = compare(finishing_example(short=True))
    assert any(c.line == 5 and c.contact.component == "shank" for c in result.candidate.contacts)
    assert result.candidate.remaining_mm3 == 4


def test_same_reviewed_tool_reproduces_plan_and_comparison_does_not_mutate_history():
    _, _, report, _ = stock_example(ball=True)
    before = encoded(evolution_record(report.stock_evolution))
    result = compare(report, tool=1)
    assert result.planned == result.candidate
    assert result.extra_removed_mm3 == result.extra_remaining_mm3 == 0
    assert encoded(evolution_record(report.stock_evolution)) == before


def test_repeat_second_stock_receives_correct_other_datum_tip_path():
    report = finishing_example(repeat=True, reverse=True)
    names = tuple(report.stock_evolution.inputs.stocks)
    result = compare(report, name=names[1], index=1, end=10)
    assert result.initial_mm3 == 8 and result.planned.remaining_mm3 == 0
    assert result.candidate.remaining_mm3 == 0.25 and result.extra_remaining_mm3 == 0.25
    first = compare(report, name=names[0], index=1, end=10)
    assert first.initial_mm3 == first.planned.remaining_mm3 == first.candidate.remaining_mm3 == 0


def test_uncertified_curves_retain_material_in_both_candidate_routes():
    report = finishing_example()
    body = replace(report.body_review, curved_lines=(5,))
    evolution = review_stock_evolution(body, report.stock_evolution.inputs, report.rotating_envelopes)
    result = compare(replace(report, body_review=body, stock_evolution=evolution))
    assert result.planned.retained_curve_lines == result.candidate.retained_curve_lines == (5,)
    assert result.planned.removed_mm3 == result.candidate.removed_mm3 == 0


@pytest.mark.parametrize("change", ["body", "history", "envelopes"])
def test_cached_state_cannot_be_rebound_to_another_review(change):
    report = finishing_example()
    name = next(iter(report.stock_evolution.inputs.stocks))
    state = reconstruct_stock_move(report.body_review, report.stock_evolution, report.rotating_envelopes, name, 0)
    if change == "body":
        report = replace(report, body_review=replace(report.body_review))
    elif change == "history":
        report = replace(report, stock_evolution=replace(report.stock_evolution))
    else:
        report = replace(report, rotating_envelopes=dict(report.rotating_envelopes))
    with pytest.raises(ValueError, match="different retained review"):
        compare(report, state=state)


@pytest.mark.parametrize(
    "options", [{"tool": True}, {"tool": 99}, {"end": True}, {"end": 3}, {"end": 999}, {"index": 4, "end": None}]
)
def test_invalid_tools_or_range_and_empty_continuation_are_refused(options):
    with pytest.raises(ValueError):
        compare(finishing_example(), **options)


def test_shared_candidate_plan_work_refusal_and_cancellation_preserve_inputs():
    report = finishing_example()
    before = encoded(evolution_record(report.stock_evolution))
    result = compare(report)
    assert compare(report, max_cell_work=result.cell_work) == result
    with pytest.raises(ValueError, match="work budget"):
        compare(report, max_cell_work=result.cell_work - 1)
    with pytest.raises(InterruptedError):
        compare(report, cancelled=lambda: True)
    assert encoded(evolution_record(report.stock_evolution)) == before
