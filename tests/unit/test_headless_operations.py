import pytest

from carveracontroller.headless.operations import catalog, compile_operation
from carveracontroller.headless.probing import compile_probe, probe_catalog


@pytest.mark.parametrize("variant", probe_catalog(), ids=lambda value: value["id"])
def test_every_probe_variant_has_a_bounded_plan_with_manual_text_separated(variant):
    values = {parameter["code"]: 5 for parameter in variant["parameters"]}
    values.update({"D": 3, "I": 0, "S": 0, "L": 1, "F": 100, "Q": 0})
    values = {key: value for key, value in values.items() if key in {p["code"] for p in variant["parameters"]}}
    plan = compile_probe(variant["id"], values)
    assert plan["commands"][0:2] == ["M120", "G21"]
    assert plan["commands"][-2:] == ["M400", "M121"]
    assert all("\n" not in line and "Make sure" not in line for line in plan["commands"])
    assert plan["probe_accuracy_verified"] is False


def test_probe_direction_is_chosen_by_variant_and_not_inverted_twice():
    assert "X-5.0" in compile_probe("single_axis.Right", {"X": 5, "D": 3, "I": 0, "S": 0})["commands"][2]
    with pytest.raises(ValueError):
        compile_probe("single_axis.Right", {"X": -5, "D": 3, "I": 0, "S": 0})


@pytest.mark.parametrize(
    "values",
    [
        {"X": 5},
        {"X": 5, "D": 3, "I": 0},
        {"X": float("nan"), "D": 3, "I": 0, "S": 0},
        {"X": "5\nM3", "D": 3, "I": 0, "S": 0},
    ],
)
def test_probe_never_inherits_polarity_zero_write_or_non_numeric_parameters(values):
    with pytest.raises(ValueError):
        compile_probe("single_axis.Right", values)


@pytest.mark.parametrize(
    "command",
    [
        "M3 S12000",
        "M499",
        "M509",
        "M826",
        "M490.2",
        "M469.1",
        "M999",
        "T6",
        "G1 X5 M3 S12000",
        "G999",
        "config-set sd pin 1",
        "G1 X5\nM3",
        "G1 X5; M3",
    ],
)
def test_expert_mdi_cannot_bypass_named_tooling_or_maintenance(command):
    with pytest.raises(ValueError):
        compile_operation("expert.mdi", {"command": command})


def test_motion_and_setting_plans_preserve_units_and_explicit_reference():
    plan = compile_operation("machine.move", {"frame": "machine", "coordinates": {"Z": -3, "X": -200}, "feed": 100})
    assert plan["commands"] == ["M120", "G21", "G90", "G53 G1 X-200 Z-3 F100", "M400", "M121"]
    assert plan["motion_completed"] is False
    assert compile_operation("wcs.set", {"wcs": 1, "method": "current_position", "coordinates": {"Z": 0}})[
        "commands"
    ] == ["M120", "G21", "G10 L20 P1 Z0", "M121"]
    assert compile_operation("machine.hold", {})["realtime"] == "feed_hold"
    assert compile_operation("accessory.light", {"enabled": True})["commands"] == ["M821"]


def test_catalog_distinguishes_unsupported_capabilities_from_ready_operations():
    value = catalog()
    assert value["profile_id"] == "carvera-community-c1-2.1.0c-v2"
    assert "maintenance.laser" in {item["id"] for item in value["unsupported"]}
    assert "maintenance.laser" not in {item["id"] for item in value["operations"]}


@pytest.mark.parametrize(
    "operation,parameters",
    [
        ("spindle.set", {"enabled": True, "rpm": 0}),
        ("machine.jog", {"axis": "Z", "distance": 0, "feed": 100}),
        ("accessory.light", {"enabled": 1}),
        ("tool.measure", {"repeats": 1, "tool_kind": "guess"}),
        ("job.start", {"path": "/sd/gcodes/a.ngc\nM3"}),
        ("wcs.set", {"wcs": 1, "method": "guess", "coordinates": {"X": 0}}),
    ],
)
def test_operation_parameters_are_closed(operation, parameters):
    with pytest.raises(ValueError):
        compile_operation(operation, parameters)
