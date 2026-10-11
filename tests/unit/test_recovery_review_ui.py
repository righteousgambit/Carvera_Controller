"""Recovery modal callbacks using the production policy and durable controller journal."""

import json
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.recovery_popup import RecoveryReviewPopup


@pytest.fixture
def recovery_popup(tmp_path, monkeypatch):
    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    program = tmp_path / "job.nc"
    program.write_text("G21\nG90\nG54\nG0 X0 Y0 Z5\n")
    controller.set_program_source(program)
    context = {
        "firmware_boot_id": 1,
        "wcs": 0,
        "tool": 1,
        "tlo": 22.5,
        "rotation": 0,
        "machine_position": [0, 0, -10],
        "work_position": [0, 0, 5],
        "work_offset": [0, 0, -15],
        "modes": [0, 0, 0, 1],
        "machine_filename": "/sd/job.nc",
        "halt_reason": 0,
        "state": "Idle",
        "telemetry_stale": False,
        "raw_inputs": {},
        "connection_generation": 1,
        "connection_address": "test-only",
    }
    monkeypatch.setattr(controller, "_recovery_context", lambda: dict(context))
    provider = Mock(return_value={"commands": ["G90", "G53 G0 Z-5", "G0 X0 Y0"], "summary": "Review test approach"})
    execute = Mock(return_value=True)
    popup = RecoveryReviewPopup(controller, 4, provider, execute)
    yield popup, context, provider, execute
    popup.stop_refresh()
    popup.dismiss()
    controller.stream.send.assert_not_called()
    controller.stream = None


def prepare(popup):
    popup.form.fields["clearance_machine_z_mm"].text = "-5"
    popup.form.fields["operator_note"].text = "Checked fixtures, homing and tool offsets"
    popup.preview_button.dispatch("on_release")
    for check in popup.checks.values():
        check.dispatch("on_release")


def test_open_refresh_and_preview_never_execute_and_require_blank_checks(recovery_popup):
    popup, _context, provider, execute = recovery_popup
    popup.refresh(0)
    provider.assert_not_called()
    execute.assert_not_called()
    assert all(not check.checked for check in popup.checks.values())
    assert not popup.form.fields["clearance_machine_z_mm"].text
    assert popup.run_button.disabled and popup.verify_button.disabled
    assert popup.checks["program_verified"].disabled
    prepare(popup)
    assert provider.call_count == 1
    assert provider.call_args.args[1]["clearance_machine_z_mm"] == -5
    execute.assert_not_called()
    assert not popup.verify_button.disabled and popup.run_button.disabled
    assert "G53 G0 Z-5" in popup.preview_text.text


def test_durable_verification_then_explicit_run_calls_once(recovery_popup):
    popup, _context, provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()
    records = [json.loads(line) for line in popup.controller.adaptive_log_path.read_text().splitlines()]
    receipt = next(event for event in records if event.get("kind") == "recovery_verification")
    assert receipt["data"]["clearance_machine_z_mm"] == -5
    assert receipt["data"]["program_verified"] is True
    assert not popup.run_button.disabled
    execute.assert_not_called()
    assert popup.run()
    assert not popup.run()
    execute.assert_called_once_with(4, provider.return_value)
    assert popup.event is None


def test_scope_change_clears_all_checks_and_preview(recovery_popup):
    popup, context, _provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()
    context["tlo"] = 23
    popup.refresh(0)
    assert all(not check.checked for check in popup.checks.values())
    assert popup.plan is None and popup.verified_signature is None
    assert popup.run_button.disabled
    assert not popup.run()
    execute.assert_not_called()
    popup.set_start_line(3)
    assert popup.start_line == 3
    assert popup.plan is None


def test_clearance_edit_invalidates_plan_and_note_edit_invalidates_verification(recovery_popup):
    popup, _context, _provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()
    popup.form.fields["operator_note"].text += " revised"
    assert popup.plan is not None and popup.run_button.disabled
    assert popup.verify()
    popup.form.fields["clearance_machine_z_mm"].text = "-4"
    assert popup.plan is None
    assert not popup.checks["clearance_verified"].checked
    assert not popup.checks["program_verified"].checked
    assert not popup.run()
    execute.assert_not_called()


def test_persistence_failure_cannot_authorize_run(recovery_popup, monkeypatch):
    popup, _context, _provider, execute = recovery_popup
    prepare(popup)
    monkeypatch.setattr(popup.controller, "_write_evidence", Mock(return_value=False))
    assert not popup.verify()
    assert popup.verified_signature is None and popup.run_button.disabled
    assert "Not verified" in popup.message.text
    assert not popup.run()
    execute.assert_not_called()


def test_invalid_clearance_and_failed_preview_cannot_verify(recovery_popup):
    popup, _context, provider, execute = recovery_popup
    popup.form.fields["clearance_machine_z_mm"].text = "nan"
    popup.form.fields["operator_note"].text = "inspected"
    popup.preview()
    provider.assert_not_called()
    assert popup.preview_button.disabled
    assert not popup.verify()
    popup.form.fields["clearance_machine_z_mm"].text = "-5"
    provider.return_value = {"commands": []}
    popup.preview()
    assert popup.plan is None
    assert "complete command list" in popup.message.text
    assert not popup.verify()
    execute.assert_not_called()


def test_changed_scope_during_preview_and_fresh_alarm_block_run(recovery_popup):
    popup, context, provider, execute = recovery_popup
    popup.form.fields["clearance_machine_z_mm"].text = "-5"
    popup.form.fields["operator_note"].text = "inspected"

    def changed(_line, _assessment):
        context["tool"] = 2
        return {"commands": ["G90"]}

    provider.side_effect = changed
    popup.preview()
    assert popup.plan is None
    assert "scope changed" in popup.message.text
    provider.side_effect = None
    prepare(popup)
    assert popup.verify()
    context["raw_inputs"] = {"z_motor_alarm": True}
    assert not popup.run()
    assert "blockers" in popup.message.text
    execute.assert_not_called()


def test_executor_refusal_consumes_verification_and_requires_explicit_recheck(recovery_popup):
    popup, _context, _provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()
    execute.return_value = False
    assert not popup.run()
    assert popup.verified_signature is None
    assert "refused" in popup.message.text
    assert not popup.run()
    execute.assert_called_once()


def test_read_error_discards_cached_approval_and_cancels_timer(recovery_popup, monkeypatch):
    popup, _context, _provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()
    monkeypatch.setattr(popup.controller, "recovery_assessment", Mock(side_effect=OSError("source unavailable")))
    popup.refresh(0)
    assert popup.plan is None
    assert popup.verify_button.disabled and popup.run_button.disabled
    assert all(not check.checked for check in popup.checks.values())
    assert "source unavailable" in popup.status.text
    assert not popup.run()
    execute.assert_not_called()
    popup.stop_refresh()
    assert popup.event is None


def test_executor_exception_and_reentrant_request_cannot_repeat_motion(recovery_popup):
    popup, _context, _provider, execute = recovery_popup
    prepare(popup)
    assert popup.verify()

    def interrupted(_line, _plan):
        assert not popup.run()
        raise RuntimeError("transport outcome unknown")

    execute.side_effect = interrupted
    assert not popup.run()
    assert "transport outcome unknown" in popup.message.text
    assert not popup.run()
    assert popup.verified_signature is None and not popup.executing
    execute.assert_called_once()
