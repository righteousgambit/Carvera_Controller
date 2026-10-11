from dataclasses import replace
from types import SimpleNamespace

from carveracontroller.addons.manufacturing_simulation.geometry import AABB, CollisionContact, Vec3
from carveracontroller.machine.clearance_groups import group_clearance_candidates


def fixture():
    contact = CollisionContact("holder", "jaw", (), AABB(Vec3(0, 0, 0), Vec3(1, 1, 1)), "swept bounds")
    operation = SimpleNamespace(id="rough", name="Roughing", start_line=1, end_line=40)
    candidates = tuple((line, "holder", "jaw") for line in range(1, 30))
    segments = tuple(SimpleNamespace(line=line, tool_id="1") for line in range(1, 30))
    return contact, operation, candidates, segments


def test_identical_cause_retains_every_source_motion_and_deduplicates_captures():
    contact, operation, candidates, segments = fixture()
    groups = group_clearance_candidates(
        (*candidates, candidates[0]),
        contacts=tuple((line, contact) for line in range(1, 30)) * 2,
        segments=segments,
        operations=(operation,),
    )
    assert len(groups) == 1
    assert groups[0].candidates == candidates
    assert groups[0].tools == ("1",)
    assert groups[0].operation == "Roughing"


def test_tool_operation_and_raw_geometry_changes_are_separate_causes():
    contact, operation, candidates, segments = fixture()
    changed = replace(contact, obstacle_bounds=AABB(Vec3(0.00001, 0, 0), Vec3(1, 1, 1)))
    operation.end_line = 20
    finishing = SimpleNamespace(id="finish", name="Finishing", start_line=21, end_line=40)
    groups = group_clearance_candidates(
        candidates,
        contacts=tuple((line, changed if line == 3 else contact) for line in range(1, 30)),
        segments=(*segments, SimpleNamespace(line=4, tool_id="2")),
        operations=(operation, finishing),
    )
    assert len(groups) == 4
    assert {candidate for group in groups for candidate in group.candidates} == set(candidates)
    assert next(group for group in groups if group.tools == ("1", "2")).candidates == (candidates[3],)
    assert next(group for group in groups if group.operation == "Finishing").candidates == candidates[20:]


def test_missing_capture_or_identity_never_implies_equivalent_causes():
    contact, operation, candidates, segments = fixture()
    assert len(group_clearance_candidates(candidates, segments=segments, operations=(operation,))) == 29
    captures = tuple((line, contact) for line in range(1, 30))
    assert len(group_clearance_candidates(candidates, contacts=captures, operations=(operation,))) == 29
    assert len(group_clearance_candidates(candidates, contacts=captures, segments=segments)) == 29
    changed = replace(contact, method="different method")
    groups = group_clearance_candidates(
        candidates[:1],
        contacts=((1, contact), (1, changed)),
        segments=segments,
        operations=(operation,),
    )
    assert len(groups) == 2
    assert all(group.candidates == candidates[:1] for group in groups)
