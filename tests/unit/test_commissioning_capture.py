import json
from types import SimpleNamespace

import pytest

from carveracontroller.machine.commissioning_capture import load_capture
from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader
from scripts.capture_linuxcnc_status import capture
from tests.unit.test_linuxcnc_status import Status


@pytest.fixture
def recording(tmp_path):
    status = Status()
    ini = tmp_path / "mill.ini"
    ini.write_text("[KINS]\nJOINTS=2\n")
    status.ini_filename = str(ini)
    path = tmp_path / "capture.jsonl"
    times = iter((10.0, 10.1, 10.2))

    def advance(_interval):
        status.joint[1]["homed"] = 1
        status.din = (1, 1)

    capture(LinuxCNCStatusReader("mill", status), path, 3, 0.1, clock=lambda: next(times), sleep=advance)
    return path


def test_capture_review_retains_units_and_recomputes_transitions(recording):
    lines = [json.loads(line) for line in recording.read_text().splitlines()]
    lines[0]["transitions"] = [{"signal": "forged safety permissive", "current": True}]
    recording.write_text("\n".join(json.dumps(line) for line in lines))
    review = load_capture(recording)
    assert review.complete and review.failure == ""
    assert len(review.sha256) == 64
    assert review.observations[0].joints[0].units_per_mm_or_degree == 0.0393700787
    assert review.observations[0].joints[1].kind == "angular"
    assert review.transitions[0] == ()
    assert {t.signal for t in review.transitions[1]} == {"din.0", "joint.1.homed"}
    assert review.transitions[2] == ()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda lines: lines[1]["status"].update(machine_id="other"),
        lambda lines: lines[1]["status"].update(sequence=4),
        lambda lines: lines[1]["status"]["joints"][0].update(actual=float("nan")),
        lambda lines: lines[1].update(ini_sha256="0" * 64),
        lambda lines: lines[-1].update(samples=4),
        lambda lines: lines[-1].update(execution_available=True),
        lambda lines: lines[0].update(captured_at_utc="2026-10-06T10:00:00"),
        lambda lines: lines[0]["status"].update(schema_version=True),
        lambda lines: lines[0]["status"]["joints"][0].update(index=2),
        lambda lines: lines[0]["status"].update(machine_id="x" * 257),
    ],
)
def test_corrupted_evidence_cannot_load(recording, mutation):
    lines = [json.loads(line) for line in recording.read_text().splitlines()]
    mutation(lines)
    recording.write_text("\n".join(json.dumps(line) for line in lines))
    with pytest.raises(ValueError):
        load_capture(recording)


def test_partial_and_failed_capture_remain_incomplete(recording):
    lines = recording.read_text().splitlines()
    recording.write_text("\n".join(lines[:2]))
    assert not load_capture(recording).complete
    recording.write_text(
        "\n".join(lines[:2] + [json.dumps({"record": "failure", "sample": 2, "error": "NML disconnected"})])
    )
    review = load_capture(recording)
    assert not review.complete and review.failure == "NML disconnected"
    recording.write_text(
        "\n".join(lines[:2] + [json.dumps({"record": "failure", "sample": 2, "error": "lost"})] + lines[2:])
    )
    with pytest.raises(ValueError, match="after"):
        load_capture(recording)


def test_panel_sample_navigation_and_stale_import_do_not_change_live_machine(recording):
    pytest.importorskip("kivy")
    from carveracontroller.desktop_commissioning import CommissioningPanel

    commands = []
    workspace = SimpleNamespace(machine=SimpleNamespace(executeCommand=commands.append))
    panel = CommissioningPanel(workspace)
    review = load_capture(recording)
    panel.generation = 2
    panel.deliver(1, review, None)
    assert panel.capture is None
    panel.deliver(2, review, None)
    assert panel.first.disabled and panel.previous.disabled
    panel.joint_choice.text = "Joint 1"
    assert "angular" in panel.joint_note.text
    panel.move(1)
    assert "joint.1.homed" in panel.transition_note.text
    panel.move(99)
    assert panel.cursor == 2 and panel.next.disabled and panel.last.disabled
    panel.deliver(2, None, "broken")
    assert panel.capture is review
    assert "previous review retained" in panel.note.text
    panel.clear()
    assert panel.capture is None and panel.details.parent is None
    panel.deliver(2, review, None)
    assert panel.capture is None
    assert commands == []


@pytest.mark.parametrize("width", [360, 650])
def test_review_layout_wraps_and_retains_joint_controls(recording, width, tmp_path):
    pytest.importorskip("kivy")
    from kivy.core.window import Window

    from carveracontroller.desktop_commissioning import CommissioningPanel
    from tests.integration.conftest import pump_frames

    panel = CommissioningPanel(SimpleNamespace(), size_hint_x=None, width=width)
    Window.add_widget(panel)
    try:
        panel.deliver(0, load_capture(recording), None)
        panel.joint_choice.text = "Joint 1"
        panel.move(1)
        pump_frames(8)
        for item in (panel.note, panel.sample_note, panel.joint_note, panel.io_note, panel.scope_note):
            assert item.text_size[1] is None
            assert item.height >= item.texture_size[1]
            assert item.width <= panel.width
        assert panel.height >= panel.minimum_height
        assert panel.details.orientation == "vertical"
        panel.export_to_png(str(tmp_path / f"commissioning-{width}.png"))
    finally:
        Window.remove_widget(panel)
