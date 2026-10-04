from dataclasses import replace

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    ToolGeometry,
    Vec3,
)
from carveracontroller.machine.setup_remedies import Remedy, compare_remedy


def inputs():
    path = (SimulationSegment(Vec3(0, 0, 0), Vec3(4, 0, 0), "1", line=7),)
    tools = {"1": ToolGeometry(2, 1, 3, 10)}
    scene = CollisionScene((CollisionObstacle("vise", AABB(Vec3(1, -1, 2), Vec3(2, 1, 3))),))
    stock = StockVolume(AABB(Vec3(0, -1, 0), Vec3(4, 1, 1)), 0.5)
    return path, tools, scene, stock


def test_obstacle_comparison_preserves_path_stock_and_tools():
    path, tools, scene, stock = inputs()
    original = stock.snapshot()
    result = compare_remedy(path, tools, scene, stock, Remedy("Move vise", obstacle="vise", shift=Vec3(0, 10, 0)))
    assert result.complete
    assert (7, "shank", "vise") in result.removed_contacts
    assert not result.new_contacts
    assert result.removal_delta_mm3 == 0
    assert stock.snapshot() == original
    assert scene.obstacles[0].bounds.minimum == Vec3(1, -1, 2)
    assert tools["1"].flute_length_mm == 1
    assert "physical clearance remain unqualified" in result.warnings[0]
    assert result.candidate.status == "potential_collision"
    assert result.candidate.candidates  # Resolving this fixture contact does not clear other contacts.


def test_longer_cutting_reach_resolves_body_contact_but_warns_diameter_changes():
    path, tools, scene, stock = inputs()
    longer = replace(tools["1"], flute_length_mm=5)
    result = compare_remedy(path, tools, scene, stock, Remedy("Longer flute", tool_id="1", replacement=longer))
    assert (7, "shank", "vise") in result.removed_contacts
    bigger = replace(longer, diameter_mm=4)
    result = compare_remedy(path, tools, scene, stock, Remedy("Larger cutter", tool_id="1", replacement=bigger))
    assert any("feature dimensions" in warning for warning in result.warnings)


def test_shift_can_introduce_contact_instead_of_resolving_it():
    path, tools, scene, stock = inputs()
    scene = replace(scene, obstacles=(replace(scene.obstacles[0], bounds=AABB(Vec3(1, 9, 2), Vec3(2, 11, 3))),))
    result = compare_remedy(
        path, tools, scene, stock, Remedy("Move toward path", obstacle="vise", shift=Vec3(0, -10, 0))
    )
    assert (7, "shank", "vise") in result.new_contacts
    assert not result.removed_contacts


def test_cancelled_comparison_does_not_claim_differences_or_mutate_stock():
    path, tools, scene, stock = inputs()
    original = stock.snapshot()
    result = compare_remedy(
        path, tools, scene, stock, Remedy("Move", obstacle="vise", shift=Vec3(0, 10, 0)), cancelled=lambda: True
    )
    assert not result.complete
    assert result.removal_delta_mm3 is None
    assert not result.removed_contacts and not result.new_contacts
    assert stock.snapshot() == original


@pytest.mark.parametrize("budget", [True, 0, -1, 2.5, 20_001])
def test_budgets_are_bounded_integers(budget):
    with pytest.raises(ValueError, match="integer segment budget"):
        compare_remedy(*inputs(), Remedy("Move", obstacle="vise", shift=Vec3(0, 10, 0)), max_segments=budget)


def test_missing_or_ambiguous_remedies_are_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        Remedy("Empty")
    with pytest.raises(ValueError, match="exactly one"):
        Remedy("Both", tool_id="1", replacement=ToolGeometry(2, 1, 3, 10), obstacle="vise", shift=Vec3(0, 1, 0))
    with pytest.raises(ValueError, match="absent"):
        compare_remedy(*inputs(), Remedy("Missing", obstacle="other", shift=Vec3(0, 1, 0)))
    with pytest.raises(ValueError, match="not used"):
        compare_remedy(*inputs(), Remedy("Missing", tool_id="9", replacement=ToolGeometry(2, 1, 3, 10)))


def test_contact_free_comparison_remains_unknown_without_registration():
    path, tools, scene, stock = inputs()
    stock = StockVolume(AABB(Vec3(20, 20, 0), Vec3(21, 21, 1)), 1)
    result = compare_remedy(path, tools, scene, stock, Remedy("Move", obstacle="vise", shift=Vec3(0, 10, 0)))
    assert not result.candidate.candidates
    assert result.candidate.status == "unknown"
    assert "physical registration and clearance unqualified" in result.candidate.qualification
