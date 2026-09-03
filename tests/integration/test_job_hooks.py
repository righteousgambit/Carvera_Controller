"""Pre- and post-job hooks.

A hook is written once and then runs before every job, so a mistake in one
repeats every time. These assert a bad hook is caught here rather than on the
machine, and that a hook failing never stops the job.
"""

import pytest

from carveracontroller.CNC import CNC


@pytest.fixture
def sent(kivy_app, monkeypatch):
    """Capture what would be sent to the machine."""
    captured = []
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", lambda cmd: captured.append(cmd.strip()))
    return captured


def _set_hook(monkeypatch, which, text):
    from carveracontroller import main as main_module

    monkeypatch.setattr(
        main_module.Config,
        "get",
        lambda _section, key: text if key == f"job_{which}_gcode" else "",
        raising=False,
    )


def test_no_hook_configured_sends_nothing(kivy_app, sent, monkeypatch):
    _set_hook(monkeypatch, "pre", "")
    assert kivy_app.root.run_job_hook("pre") == []
    assert sent == []


def test_a_valid_hook_is_sent_line_by_line(kivy_app, sent, monkeypatch):
    _set_hook(monkeypatch, "pre", "G90 G21\nM7\nG53 G0 Z-5")

    lines = kivy_app.root.run_job_hook("pre")

    assert lines == ["G90 G21", "M7", "G53 G0 Z-5"]
    assert sent == ["G90 G21", "M7", "G53 G0 Z-5"]


def test_blank_lines_are_skipped(kivy_app, sent, monkeypatch):
    _set_hook(monkeypatch, "post", "G90 G21\n\n   \nM9")

    assert kivy_app.root.run_job_hook("post") == ["G90 G21", "M9"]


def test_a_hook_with_an_error_is_not_sent(kivy_app, sent, monkeypatch):
    """A feed the machine cannot reach would silently be clamped."""
    _set_hook(monkeypatch, "pre", "G90 G21\nS12000 M3\nG1 X10 F9000")

    assert kivy_app.root.run_job_hook("pre") == []
    assert sent == [], "sent a hook the checker rejected"


def test_inch_mode_in_a_hook_is_rejected(kivy_app, sent, monkeypatch):
    _set_hook(monkeypatch, "pre", "G20\nG0 X1")

    assert kivy_app.root.run_job_hook("pre") == []
    assert sent == []


def test_hooks_are_independent(kivy_app, sent, monkeypatch):
    _set_hook(monkeypatch, "post", "M9")

    assert kivy_app.root.run_job_hook("pre") == []
    assert kivy_app.root.run_job_hook("post") == ["M9"]


def test_a_missing_config_entry_does_not_raise(kivy_app, monkeypatch):
    from carveracontroller import main as main_module

    monkeypatch.setattr(main_module.Config, "get", lambda *_a: None, raising=False)

    assert kivy_app.root.run_job_hook("pre") == []


def test_starting_a_job_counts_it(kivy_app, monkeypatch):
    from carveracontroller.machine.usage_counters import UsageCounters

    kivy_app.root.usage_counters = UsageCounters()
    monkeypatch.setattr(kivy_app.root, "run_job_hook", lambda _which: [])
    monkeypatch.setattr(kivy_app.root, "apply", lambda _buffer: None)
    monkeypatch.setattr(kivy_app.root.controller, "playCommand", lambda *_a, **_k: None)
    CNC.vars["playedseconds"] = 0

    kivy_app.root._play_now("job.nc", 0)

    assert kivy_app.root.usage_counters.jobs_started == 1
