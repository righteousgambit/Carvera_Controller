import json

import pytest

from carveracontroller.machine.capabilities import (
    AckState,
    AxisDefinition,
    CapabilityEvidence,
    CapabilitySet,
    CarveraAdapter,
    CommandLifecycle,
    FirmwareIdentity,
    Support,
    carvera_capabilities,
    linuxcnc_declaration,
)


def adapter(firmware=None):
    return CarveraAdapter(
        carvera_capabilities(
            "shop",
            "C1",
            firmware or FirmwareIdentity("community", "2.1.0c"),
            10,
            tuple(AxisDefinition(axis, minimum=-400, maximum=0) for axis in "XYZ"),
            has_atc=True,
        )
    )


def test_firmware_capability_bounds():
    stable = adapter().capabilities
    assert "pwm" in stable.telemetry_fields
    assert stable.features["inverse_time"].permits(20)
    dev = adapter(FirmwareIdentity("community", "dev", "f1db00fabcd")).capabilities
    assert "pwm" not in dev.telemetry_fields
    assert not dev.features["custom_slots"].permits(20)
    future = adapter(FirmwareIdentity("community", "9.0.0")).capabilities
    assert not future.features["status"].permits(20)
    assert not stable.features["tcp"].permits(20)


def test_persistent_slot_commands_require_opt_in_and_travel():
    a = adapter()
    with pytest.raises(ValueError, match="opt-in"):
        a.write_slot(1, (-100, -200, -50), 20)
    assert a.write_slot(23, (-100, -200, -50), 20, opt_in=True).commands == ("M890 T23 X-100 Y-200 Z-50", "M889")
    assert a.write_slot(23, None, 20, opt_in=True).commands == ("M891 T23", "M889")
    for point in ((0, 0, 1), (float("nan"), 0, 0), (-401, 0, 0)):
        with pytest.raises(ValueError, match="travel"):
            a.write_slot(1, point, 20, opt_in=True)
    for slot in (0, 256, True, 2.5):
        with pytest.raises(ValueError, match="integer"):
            a.write_slot(slot, None, 20, opt_in=True)


def test_overrides_named_outputs_and_unknown_denial():
    a = adapter()
    assert a.snapshot(20).commands == ("?",)
    assert a.feed_override(225, 20, instant=True).commands == ("$F S225",)
    assert a.feed_override(75, 20).commands == ("M220 S75",)
    assert a.named_io("air", False, 20).commands == ("M9",)
    assert a.named_io("vacuum", True, 20, 40).commands == ("M801 S40",)
    with pytest.raises(ValueError, match="unmapped"):
        a.named_io("clamp", True, 20)
    with pytest.raises(ValueError, match="stale"):
        a.snapshot(41)
    with pytest.raises(ValueError):
        a.feed_override(float("inf"), 20)
    a.capabilities.features["feed_override"] = CapabilityEvidence(Support.UNSUPPORTED, Support.SUPPORTED, 10)
    assert a.capabilities.features["feed_override"].conflict
    with pytest.raises(ValueError, match="conflicts"):
        a.feed_override(80, 20)


def test_schema_roundtrip_and_offline_linuxcnc():
    a = adapter().capabilities
    a.tool_slots = (1, 17, 255)
    encoded = json.loads(json.dumps(a.to_dict()))
    assert CapabilitySet.from_dict(encoded) == a
    encoded["schema_version"] = 999
    with pytest.raises(ValueError, match="schema"):
        CapabilitySet.from_dict(encoded)
    cnc = linuxcnc_declaration("five", tuple(AxisDefinition(axis) for axis in "XYZBC"), "head-table")
    assert not cnc.execution_available
    with pytest.raises(ValueError, match="unavailable"):
        cnc.require("tcp", 10)


def test_ack_acceptance_is_not_physical_verification():
    lifecycle = CommandLifecycle("unique-1", adapter().feed_override(80, 20))
    lifecycle.sent(20)
    lifecycle.acknowledge(20.125, "ok")
    assert lifecycle.state == AckState.ACCEPTED
    assert lifecycle.latency_ms == 125
    lifecycle.verify("observed override 80%")
    assert lifecycle.state == AckState.VERIFIED
    with pytest.raises(ValueError):
        lifecycle.sent(21)
    second = CommandLifecycle("unique-2", adapter().snapshot(20))
    second.sent(20)
    assert not second.expire(20.5, 1)
    assert second.expire(21, 1)
    with pytest.raises(ValueError):
        second.acknowledge(22, "late ok")
    assert second.state == AckState.TIMED_OUT


def test_invalid_axes():
    for kwargs in ({"name": "XX"}, {"name": "X", "minimum": 2, "maximum": 1}, {"name": "A", "maximum": float("inf")}):
        with pytest.raises(ValueError):
            AxisDefinition(**kwargs)


def test_slot_readback_matches_firmware_format():
    from carveracontroller.machine.capabilities import parse_slot_readback

    result = parse_slot_readback("Tool Slots Configuration:\nTool 17: X=-100.000 Y=-40.000 Z=-50.000\nok")
    assert result[0].number == 17
    assert result[0].position == (-100, -40, -50)
    for text in ("ok", "Tool Slots Configuration:\n", "Tool Slots Configuration:\nTool 2: broken"):
        with pytest.raises(ValueError):
            parse_slot_readback(text)
