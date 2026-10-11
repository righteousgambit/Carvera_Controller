"""Full nominal inputs without clearance claims or relaxed collision budgets."""

from dataclasses import replace

import pytest

from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_playback_preparation import prepare_program_playback
from carveracontroller.machine.program_playback_timing import prepare_program_timing
from carveracontroller.machine.program_surface_clearance import scene_surfaces
from carveracontroller.machine.scene_joint_clearance import build_scene_clearance, capture_scene_clearance
from tests.unit.test_program_stock_evolution import stock_example
from tests.unit.test_scene_joint_clearance import scene_viewer


def test_nominal_preparation_preserves_all_geometry_motion_stock_and_explicit_unknown_clearance():
    source, offsets, expected, captures = stock_example(ball=True, repeat=True, rotation=31, tilt=(20, -10))
    prepared = prepare_program_playback(source, captures, offsets, stock_resolution_mm=0.5)
    report = prepared.scene
    assert report.body_review.segments == expected.body_review.segments
    assert report.meshes.keys() == expected.meshes.keys()
    for tool, meshes in report.meshes.items():
        assert meshes.keys() == expected.meshes[tool].keys()
        for name, mesh in meshes.items():
            original = expected.meshes[tool][name]
            assert mesh.triangles == original.triangles
            assert mesh.root.bounds == original.root.bounds
            assert mesh.index_method == "median-v1" and original.index_method == "surface-directions-v3"
            pending, faces = [mesh.root], []
            while pending:
                node = pending.pop()
                pending.extend(node.children)
                faces.extend(node.ids)
            assert sorted(faces) == list(range(len(original.triangles)))
    assert report.stock_evolution.steps == expected.stock_evolution.steps
    assert report.stock_evolution.final_snapshots == expected.stock_evolution.final_snapshots
    assert report.body_review.contacts == () and report.contacts == () and report.body_review.tested_pairs == 0
    assert "clearance_not_reviewed" in report.body_review.status
    assert "has not been reviewed" in report.qualification
    assert prepare_program_timing(source, report.body_review, offsets).gap_count >= 2


def test_curve_parameters_bind_nominal_segments_and_do_not_remove_uncertified_curve_material():
    source, offsets, _, captures = stock_example(ball=True)
    program = ProgramOperations.from_text(source.text + "\nG2 X0 Y1 I-0.5 J0.5 F100")
    source = ProgramClearanceSource.capture(program)
    prepared = prepare_program_playback(source, captures, offsets, stock_resolution_mm=0.5)
    curve = source.curve_enclosures[-1]
    segments = [s for s in prepared.scene.body_review.segments if s.line == curve.line_number]
    assert [s.source_start_ratio for s in segments] == list(curve.parameters[:-1])
    assert [s.source_end_ratio for s in segments] == list(curve.parameters[1:])
    assert all(
        s.state == "curve material retained" and s.removed_mm3 == 0
        for s in prepared.scene.stock_evolution.steps
        if s.line == curve.line_number
    )
    prepare_program_timing(source, prepared.scene.body_review, offsets)


def test_nominal_preparation_refuses_unknown_tools_limits_datums_and_cancel():
    source, offsets, _, captures = stock_example()
    with pytest.raises(ValueError, match="profiles"):
        prepare_program_playback(source, {}, offsets)
    with pytest.raises(ValueError, match="datums"):
        prepare_program_playback(replace(source, declared_offsets=(("G54", (0, 0, 0)),)), captures, offsets)
    far = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nG1 X1000"))
    with pytest.raises(ValueError, match="travel"):
        prepare_program_playback(far, captures, offsets)
    with pytest.raises(InterruptedError):
        prepare_program_playback(source, captures, offsets, cancelled=lambda: True)


def test_all_tools_share_complete_fixed_geometry_with_independent_spindle_and_one_face_budget():
    source, offsets, _, captures = stock_example()
    first = captures[1]
    second = replace(first.definition, number=2, stickout=first.definition.stickout + 3)
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
    report = prepare_program_playback(source, captures, offsets).scene
    one, two = report.meshes[1], report.meshes[2]
    assert one.keys() == two.keys()
    for name in one:
        assert (one[name] is two[name]) == (not name.startswith("spindle "))
    for tool, captured in captures.items():
        original = scene_surfaces(captured, build_scene_clearance(captured))
        assert all(mesh.index_method == "surface-directions-v3" for mesh in original.values())
        assert {n: m.triangles for n, m in report.meshes[tool].items()} == {n: m.triangles for n, m in original.items()}
    unique = {id(m): m for meshes in report.meshes.values() for m in meshes.values()}
    required = sum(len(m.triangles) for m in unique.values())
    admitted = prepare_program_playback(source, captures, offsets, max_triangles=required).scene
    assert {t: {n: m.triangles for n, m in meshes.items()} for t, meshes in admitted.meshes.items()} == {
        t: {n: m.triangles for n, m in meshes.items()} for t, meshes in report.meshes.items()
    }
    with pytest.raises(ValueError, match="budget"):
        prepare_program_playback(source, captures, offsets, max_triangles=required - 1)
    for limit in (0, 250001, True):
        with pytest.raises(ValueError, match="budget"):
            prepare_program_playback(source, captures, offsets, max_triangles=limit)
