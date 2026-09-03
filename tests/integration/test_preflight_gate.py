"""The pre-job checks must inform without getting in the way.

A dialog that appears before every job, mostly to say everything is fine, is
one people learn to dismiss without reading. These assert it stays quiet when
there is nothing to say and speaks up when there is.
"""

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.machine.preflight import CheckStatus


def _good_setup(app):
    # The checks read the app's connection state, not just CNC.vars.
    app.state = "Idle"
    CNC.vars["state"] = "Idle"
    CNC.vars["wcox"] = -150.0
    CNC.vars["wcoy"] = -90.0
    CNC.vars["wcoz"] = -20.0
    app.root.lines = ["G90 G94\n", "G17\n", "G21\n", "M6 T1\n", "S12000 M3\n", "G1 X10 F800\n"]
    app.root.tool_table = {1: "6mm endmill"}


def test_a_clean_setup_reports_nothing(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)

    assert kivy_app.root.preflight_findings() == []


def test_a_program_error_is_reported(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    kivy_app.root.lines.append("G1 X20 F9000\n")
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)

    findings = kivy_app.root.preflight_findings()

    assert any(c.name == "Program" and c.status is CheckStatus.FAIL for c in findings)


def test_an_uncalibrated_probe_is_reported(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "2.0", raising=False)

    findings = kivy_app.root.preflight_findings()

    assert any(c.name == "Probe tip diameter" for c in findings)


def test_a_missing_tool_is_reported(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    kivy_app.root.tool_table = {4: "something else"}
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)

    findings = kivy_app.root.preflight_findings()

    assert any(c.name == "Tools" and c.status is CheckStatus.FAIL for c in findings)


def test_checks_never_prevent_a_job_from_starting(kivy_app, monkeypatch):
    """A failure inside the checks must not become a failure to run."""

    def _explode(_state):
        raise RuntimeError("checks are broken")

    monkeypatch.setattr("carveracontroller.main.run_preflight", _explode)

    assert kivy_app.root.preflight_findings() == []


def test_a_clean_job_starts_without_a_dialog(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)

    played = []
    monkeypatch.setattr(kivy_app.root, "_play_now", lambda f, s: played.append((f, s)))
    shown = []
    monkeypatch.setattr(kivy_app.root, "_show_preflight_popup", lambda *a: shown.append(a))

    kivy_app.root.play("job.nc", 0)

    assert played == [("job.nc", 0)]
    assert shown == []


def test_a_job_with_findings_asks_first(kivy_app, monkeypatch):
    _good_setup(kivy_app)
    kivy_app.root.tool_table = {9: "wrong tool"}
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)

    played = []
    monkeypatch.setattr(kivy_app.root, "_play_now", lambda f, s: played.append((f, s)))
    shown = []
    monkeypatch.setattr(kivy_app.root, "_show_preflight_popup", lambda *a: shown.append(a))

    kivy_app.root.play("job.nc", 0)

    assert played == [], "started despite findings"
    assert len(shown) == 1


def test_acknowledgement_does_not_carry_to_the_next_job(kivy_app, monkeypatch):
    """Accepting findings once must not silence the checks thereafter."""
    _good_setup(kivy_app)
    kivy_app.root.tool_table = {9: "wrong tool"}
    monkeypatch.setattr("carveracontroller.main.get_machine_config_hint", lambda _key: "1.642", raising=False)
    played = []
    monkeypatch.setattr(kivy_app.root, "_play_now", lambda f, s: played.append((f, s)))
    shown = []
    monkeypatch.setattr(kivy_app.root, "_show_preflight_popup", lambda *a: shown.append(a))

    kivy_app.root._preflight_acknowledged = True
    kivy_app.root.play("job.nc", 0)
    assert played == [("job.nc", 0)]

    kivy_app.root.play("job.nc", 0)

    assert len(shown) == 1, "second job was not checked"
