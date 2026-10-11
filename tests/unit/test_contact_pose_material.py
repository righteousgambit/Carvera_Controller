"""Exact partial stock replay, original target faces and work-chain placement."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.machine.contact_pose_material import prepare_contact_material
from carveracontroller.machine.contact_pose_view import prepare_contact_pose_view, project_contact_pose_view
from carveracontroller.machine.program_cad_first_contact import CadFirstContact, contact_pose
from carveracontroller.machine.stock_generated_clearance import review_generated_finish
from carveracontroller.machine.tool_preview import PreviewPose
from tests.unit.test_stock_generated_clearance import prepared


def sample(result, index, time=F(1)):
    pose = contact_pose(result.scene, result.plan.tool, index, time)
    names = tuple(b.name for b in pose.bodies)
    row = CadFirstContact(result.plan.tool, names[0], names[1], "contained", index, time, time, pose)
    return prepare_contact_pose_view(result.scene, row)


@pytest.fixture
def review(tmp_path):
    parent, plan = prepared(tmp_path)
    return review_generated_finish(plan, parent)


def volume(triangles):
    return abs(
        sum(
            a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2]) + a[2] * (b[0] * c[1] - b[1] * c[0])
            for a, b, c in triangles
        )
        / 6
    )


def test_all_independent_final_states_and_complete_boundary_volume(review):
    scene = sample(review, len(review.plan.moves) - 1)
    before = review.plan.analysis.target.initial
    for label, state in review.plan.states.items():
        material = prepare_contact_material(review, scene, label)
        remaining, target = material.view.bodies[-2:]
        assert material.before_mm3 == state.before.material_mm3
        assert material.remaining_mm3 == state.after.material_mm3
        assert material.removed_mm3 == pytest.approx(state.removed_mm3)
        assert remaining.kind == "remaining" and target.kind == "target"
        assert volume(remaining.triangles) == pytest.approx(material.remaining_mm3, abs=1e-8)
        assert len(target.triangles) == len(review.plan.analysis.target.solid.mesh.triangles_mm)
        assert material.view.bodies[:-2] == scene.bodies
        assert material.view.pose == scene.pose
        batches = project_contact_pose_view(
            material.view, PreviewPose(0.6, -0.25, 1, 640, 360, 320, 180), tuple(b.name for b in material.view.bodies)
        )
        assert sum(len(i) // 3 for v, i in batches) == sum(len(b.triangles) for b in material.view.bodies)
    assert review.plan.analysis.target.initial == before


def test_earlier_and_partial_move_do_not_substitute_final_stock(review):
    label = "Initial stock"
    initial = prepare_contact_material(review, sample(review, 0, F(0)), label)
    final = prepare_contact_material(review, sample(review, len(review.plan.moves) - 1), label)
    assert initial.remaining_mm3 == initial.before_mm3 > final.remaining_mm3
    candidates = []
    for i, m in enumerate(review.plan.moves):
        if m.cutting:
            a = prepare_contact_material(review, sample(review, i, F(0)), label)
            b = prepare_contact_material(review, sample(review, i, F(1, 2)), label)
            c = prepare_contact_material(review, sample(review, i, F(1)), label)
            assert a.remaining_mm3 >= b.remaining_mm3 >= c.remaining_mm3
            candidates.append((a.remaining_mm3, b.remaining_mm3, c.remaining_mm3))
    assert any(a > b or b > c for a, b, c in candidates)


def test_target_keeps_original_face_order_and_negative_table_y_datum(review):
    scene = sample(review, len(review.plan.moves) // 2, F(1, 3))
    material = prepare_contact_material(review, scene, "Initial stock")
    target = review.plan.analysis.target
    from carveracontroller.addons.manufacturing_simulation import StockVolume, Vec3

    grid = StockVolume.from_snapshot(target.target)
    hy = review.parent.body_review.records[review.plan.tool]["work_base"]["translation"][1]
    for actual, original in zip(material.view.bodies[-1].triangles, target.solid.mesh.triangles_mm):
        for a, p in zip(actual, original):
            q = grid.program_point(Vec3(*(v + s for v, s in zip(p, target.translation_mm)))).tuple
            expected = (
                q[0] + review.plan.stock_offset_mm[0],
                q[1] + review.plan.stock_offset_mm[1] + hy - float(scene.pose.joints_mm[1]),
                q[2] + review.plan.stock_offset_mm[2],
            )
            assert a == pytest.approx(expected, abs=1e-9)


def test_empty_remaining_body_clears_geometry_instead_of_retaining_old_stock(review):
    material = prepare_contact_material(review, sample(review, 0), "Initial stock")
    body = replace(material.view.bodies[-2], triangles=())
    scene = replace(material.view, bodies=(body,))
    assert project_contact_pose_view(scene, PreviewPose(0, 0, 1, 400, 200, 200, 100), (body.name,)) == ()


def test_tilted_inch_target_and_rotated_material_are_not_recentred(tmp_path):
    from carveracontroller.addons.manufacturing_simulation import StockVolume, Vec3
    from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
    from carveracontroller.machine.stock_generated_finish import generate_stock_finish
    from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target
    from tests.unit.test_program_stock_evolution import stock_example
    from tests.unit.test_stock_solid import box, mesh

    _, _, parent, _ = stock_example(rotation=31, tilt=(20, -10))
    name = next(iter(parent.stock_evolution.inputs.stocks))
    state = reconstruct_stock_move(parent.body_review, parent.stock_evolution, parent.rotating_envelopes, name, 0)
    source = mesh(tmp_path, box((0, 0, 0), (1 / 25.4, 1 / 25.4, 1 / 25.4)), units="inch")
    target = prepare_stock_target(state, name, source.source_path, units="inch", translation_mm=(-0.5, -0.5, 0.5))
    result = review_generated_finish(generate_stock_finish(analyze_stock_target(target, state), 1), parent)
    scene = sample(result, 0, F(0))
    material = prepare_contact_material(result, scene, "Initial stock")
    grid = StockVolume.from_snapshot(target.target)
    target_body = material.view.bodies[-1]
    assert volume(target_body.triangles) == pytest.approx(1)
    assert volume(material.view.bodies[-2].triangles) == pytest.approx(material.remaining_mm3)
    hy = parent.body_review.records[1]["work_base"]["translation"][1]
    for actual, triangle in zip(target_body.triangles, target.solid.mesh.triangles_mm):
        for p, q in zip(actual, triangle):
            local = grid.program_point(Vec3(*q) + Vec3(*target.translation_mm)).tuple
            expected = (
                local[0] + result.plan.stock_offset_mm[0],
                local[1] + result.plan.stock_offset_mm[1] + hy - float(scene.pose.joints_mm[1]),
                local[2] + result.plan.stock_offset_mm[2],
            )
            assert p == pytest.approx(expected, abs=1e-8)


def test_closed_cavity_keeps_all_original_target_faces_and_inner_winding(tmp_path):
    from carveracontroller.machine.stock_generated_finish import generate_stock_finish
    from tests.unit.test_stock_allowance import example

    parent, analysis = example(tmp_path, cavity=True)
    result = review_generated_finish(generate_stock_finish(analysis, 2), parent)
    material = prepare_contact_material(result, sample(result, 0, F(0)), "Initial stock")
    assert len(material.view.bodies[-1].triangles) == 24
    assert volume(material.view.bodies[-1].triangles) == pytest.approx(7)


@pytest.mark.parametrize(
    "case", ["state", "source", "pose", "plan", "work", "faces", "cancel", "double", "assembly", "scene"]
)
def test_refusals_and_cancellation_never_publish_partial_material(review, case):
    scene = sample(review, len(review.plan.moves) - 1)
    kwargs = {}
    state = "Initial stock"
    if case == "state":
        state = "unknown"
    elif case == "source":
        scene = replace(scene, source_sha256="changed")
    elif case == "pose":
        scene = replace(scene, pose=replace(scene.pose, joints_mm=(F(1), F(2), F(3))))
    elif case == "plan":
        review = replace(review, plan=replace(review.plan, stock_offset_mm=(1, 2, 3)))
    elif case == "work":
        kwargs["max_cell_work"] = 1
    elif case == "faces":
        kwargs["max_boundary_faces"] = 1
    elif case == "cancel":
        kwargs["cancelled"] = lambda: True
    elif case == "assembly":
        scene = replace(scene, bodies=scene.bodies[:-1])
    elif case == "scene":
        record = dict(review.scene.body_review.records[review.plan.tool])
        record["work_base"] = {"translation": [1, 2, 3]}
        review = replace(
            review,
            scene=replace(
                review.scene, body_review=replace(review.scene.body_review, records={review.plan.tool: record})
            ),
        )
        scene = sample(review, len(review.plan.moves) - 1)
    else:
        scene = prepare_contact_material(review, scene, state).view
    with pytest.raises((ValueError, InterruptedError)):
        prepare_contact_material(review, scene, state, **kwargs)


def test_context_change_during_geometry_preparation_withholds_whole_view(review, monkeypatch):
    import carveracontroller.machine.contact_pose_material as module

    original = module.stock_geometry

    def changed(*args, **kwargs):
        geometry = original(*args, **kwargs)
        review.parent.body_review.records[review.plan.tool]["scene_source"]["scene_digest"] = "changed"
        return geometry

    scene = sample(review, 0)
    monkeypatch.setattr(module, "stock_geometry", changed)
    with pytest.raises(ValueError, match="changed during"):
        prepare_contact_material(review, scene, "Initial stock")
