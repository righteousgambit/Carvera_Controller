"""Tests for halt recovery guidance."""

import pytest

from carveracontroller.machine.halt_recovery import (
    RecoveryAction,
    format_guidance,
    guidance_for,
    recovery_action_for,
)


def _halt_codes():
    """Halt reason codes the application knows how to name."""
    from carveracontroller.main import load_halt_translations
    from carveracontroller.translation import tr

    return list(load_halt_translations(tr))


def test_every_halt_reason_the_app_knows_has_guidance():
    """The two lists must not drift apart.

    HALT_REASON names every halt the firmware reports. A reason with a name
    but no guidance is exactly the case this module exists to remove.
    """
    for code in _halt_codes():
        assert guidance_for(code) is not None, f"halt reason {code} has a name but no guidance"


def test_unknown_reason_yields_nothing_rather_than_a_guess():
    assert guidance_for(9999) is None
    assert format_guidance(9999) == ""


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (1, RecoveryAction.UNLOCK),
        (16, RecoveryAction.UNLOCK),
        (20, RecoveryAction.UNLOCK),
        (21, RecoveryAction.RESET),
        (26, RecoveryAction.RESET),
        (41, RecoveryAction.POWER_CYCLE),
    ],
)
def test_recovery_action_follows_the_firmware_ranges(code, expected):
    assert recovery_action_for(code) is expected


def test_declared_action_matches_the_code_range():
    """Guidance must not promise an unlock for something needing a reset."""
    for code in _halt_codes():
        guidance = guidance_for(code)
        assert guidance.action is recovery_action_for(code), f"halt {code} declares the wrong action"


def test_probe_failures_warn_about_the_work_origin():
    """A stopped probe can leave the work coordinate at the stop position."""
    for code in (3, 16):
        assert "work origin" in guidance_for(code).caution.lower()


def test_spindle_stall_advice_targets_engagement_not_feed():
    """Radial engagement is what consumes headroom on a 200 W spindle."""
    steps = " ".join(guidance_for(25).steps).lower()

    assert "engagement" in steps
    assert "200" in steps


def test_emergency_stop_says_to_twist_the_button():
    steps = " ".join(guidance_for(13).steps).lower()
    assert "twist" in steps


def test_formatted_guidance_numbers_its_steps():
    text = format_guidance(2)

    assert text.startswith("Homing did not complete.")
    assert "1. " in text
    assert "2. " in text


def test_formatted_guidance_includes_the_caution_when_present():
    assert "work origin" in format_guidance(3).lower()


def test_guidance_without_a_caution_does_not_trail_blank_lines():
    text = format_guidance(1)

    assert guidance_for(1).caution == ""
    assert text == text.rstrip()


def test_every_guidance_has_at_least_one_step():
    for code in _halt_codes():
        assert guidance_for(code).steps, f"halt {code} has no steps"


# ---------------------------------------------------- popup body composition


def _halt_content(*args):
    import inspect

    import carveracontroller.main as main_module

    cls = next(obj for obj in vars(main_module).values() if inspect.isclass(obj) and hasattr(obj, "_halt_content"))
    return cls._halt_content(*args)


def test_popup_puts_guidance_before_the_firmware_message():
    """Guidance is what the operator needs; the raw message is detail."""
    body = _halt_content(25, "ERROR: spindle stall detected", "Confirm to reset machine?")

    assert body.index("Reduce radial engagement") < body.index("ERROR: spindle stall detected")
    assert body.endswith("Confirm to reset machine?")


def test_popup_still_works_without_a_firmware_message():
    body = _halt_content(2, "", "Choose unlock option:")

    assert "Homing did not complete." in body
    assert "Choose unlock option:" in body
    assert "\n\n\n" not in body, "no empty section where the message would be"


def test_popup_falls_back_to_the_prompt_for_an_unknown_halt():
    body = _halt_content(9999, "", "Confirm to unlock machine?")
    assert body == "Confirm to unlock machine?"


def test_popup_keeps_the_firmware_message_for_an_unknown_halt():
    body = _halt_content(9999, "ERROR: something new", "Confirm to unlock machine?")

    assert "ERROR: something new" in body
    assert body.endswith("Confirm to unlock machine?")
