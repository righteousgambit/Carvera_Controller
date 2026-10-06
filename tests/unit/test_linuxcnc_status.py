import json
import sys
from types import SimpleNamespace

import pytest

from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader


class Status:
    def __init__(self):
        self.joints = 2
        self.joint = [
            {
                "jointType": kind,
                "units": units,
                "output": command,
                "input": actual,
                "ferror_current": error,
                "velocity": velocity,
                "homed": 0,
                "homing": 0,
                "enabled": 1,
                "fault": 0,
                "min_hard_limit": 0,
                "max_hard_limit": 0,
                "min_soft_limit": 0,
                "max_soft_limit": 0,
            }
            for kind, units, command, actual, error, velocity in (
                (1, 0.0393700787, 4.0, 3.99, 0.01, 0.2),
                (2, 1.0, 90.0, 89.9, 0.1, 2.0),
            )
        ]
        self.actual_position = (3.99, 0.0, 0.0, 89.9, 0.0, 0.0, 0.0, 0.0, 0.0)
        self.axis_mask = 9
        self.linear_units = 0.0393700787
        self.angular_units = 1.0
        self.ini_filename = "/configs/machine.ini"
        self.din, self.dout = (0, 1), (1, 0)
        self.ain, self.aout = (1.2,), (3.4,)
        self.task_state, self.task_mode, self.interp_state, self.motion_mode = 4, 1, 1, 1
        self.exec_state, self.tool_in_spindle = 2, 7
        self.failure = None
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.failure:
            raise self.failure


def test_real_api_entry_opens_only_status_channel(monkeypatch):
    status = Status()

    def command():
        pytest.fail("read-only adapter must never construct command channel")

    monkeypatch.setitem(sys.modules, "linuxcnc", SimpleNamespace(stat=lambda: status, command=command))
    reader = LinuxCNCStatusReader.connect_local("gantry")
    observed = reader.poll(100.0)
    assert status.polls == 1
    assert observed.machine_id == "gantry"
    assert observed.axis_mask == 9
    assert observed.actual_position[3] == 89.9
    assert observed.joints[0].actual == 3.99
    assert observed.joints[0].kind == "linear"
    assert observed.joints[1].kind == "angular"
    assert observed.linear_units_per_mm == 0.0393700787
    assert observed.joints[1].units_per_mm_or_degree == 1
    assert observed.joints[0].following_error == 0.01
    assert observed.digital_inputs == (False, True)
    assert observed.analog_outputs == (3.4,)
    assert json.loads(json.dumps(observed.to_dict()))["evidence"] == "NML status poll"
    assert reader.fresh(100.5) and not reader.fresh(102.0)
    assert not reader.fresh(99.0)


def test_homing_and_io_changes_record_observation_interval():
    status = Status()
    reader = LinuxCNCStatusReader("gantry", status)
    reader.poll(10.0)
    assert reader.transitions == ()
    status.joint[1]["homing"] = 1
    status.din = (1, 1)
    reader.poll(10.1)
    assert {c.signal for c in reader.transitions} == {"din.0", "joint.1.homing"}
    assert all(c.previous_observed_at == 10.0 and c.observed_at == 10.1 for c in reader.transitions)
    status.joint[1]["homing"], status.joint[1]["homed"] = 0, 1
    reader.poll(10.2)
    assert {c.signal for c in reader.transitions} == {"joint.1.homing", "joint.1.homed"}
    assert reader.last.sequence == 3
    # Snapshot owns immutable copies, not a live reference to status dictionaries.
    status.joint[1]["homed"] = 0
    assert reader.last.joints[1].homed


def test_failed_poll_invalidates_pose_and_breaks_transition_continuity():
    status = Status()
    reader = LinuxCNCStatusReader("gantry", status)
    reader.poll(10.0)
    status.failure = OSError("NML unavailable")
    with pytest.raises(OSError):
        reader.poll(10.1)
    assert reader.last is None and reader.transitions == ()
    assert not reader.fresh(10.2)
    status.failure = None
    status.din = (1, 1)
    restored = reader.poll(10.3)
    assert restored.generation == 1 and restored.sequence == 2
    assert reader.transitions == ()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: setattr(s, "actual_position", (0.0,) * 8),
        lambda s: setattr(s, "linear_units", 0),
        lambda s: setattr(s, "axis_mask", 512),
        lambda s: setattr(s, "joints", 3),
        lambda s: setattr(s, "din", (2,)),
        lambda s: s.joint[0].update(input=float("nan")),
        lambda s: s.joint[0].update(jointType=3),
        lambda s: s.joint[0].update(units=-1),
        lambda s: setattr(s, "tool_in_spindle", True),
        lambda s: setattr(s, "ini_filename", ""),
    ],
)
def test_malformed_status_cannot_retain_a_fresh_observation(mutation):
    status = Status()
    reader = LinuxCNCStatusReader("gantry", status)
    reader.poll(10.0)
    mutation(status)
    with pytest.raises(ValueError):
        reader.poll(11.0)
    assert reader.last is None and not reader.fresh(11.0)


def test_configuration_switch_and_clock_regression():
    status = Status()
    reader = LinuxCNCStatusReader("gantry", status)
    reader.poll(10.0)
    status.ini_filename = "/configs/other.ini"
    status.din = (1, 1)
    reader.poll(11.0)
    assert reader.transitions == ()
    with pytest.raises(ValueError, match="regressed"):
        reader.poll(9.0)
    assert reader.last is None


def test_capture_binds_ini_and_retains_failures_without_overwriting(tmp_path):
    from scripts.capture_linuxcnc_status import capture

    status = Status()
    config = tmp_path / "machine.ini"
    config.write_text("[KINS]\nJOINTS=2\n")
    status.ini_filename = str(config)
    output = tmp_path / "capture.jsonl"
    reader = LinuxCNCStatusReader("gantry", status)

    def change_configuration(interval):
        config.write_text("[KINS]\nJOINTS=3\n")

    with pytest.raises(ValueError, match="INI changed"):
        capture(reader, output, 2, 0.1, clock=lambda: 100.0, sleep=change_configuration)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [r["record"] for r in records] == ["observation", "failure"]
    assert len(records[0]["ini_sha256"]) == 64
    assert records[0]["status"]["machine_id"] == "gantry"
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        capture(reader, output, 1, 0.1)
    assert output.read_bytes() == saved


def test_capture_completes_only_after_all_samples(tmp_path):
    from scripts.capture_linuxcnc_status import capture

    status = Status()
    config = tmp_path / "machine.ini"
    config.write_text("[KINS]\nJOINTS=2\n")
    status.ini_filename = str(config)
    output = tmp_path / "capture.jsonl"
    reader = LinuxCNCStatusReader("gantry", status)
    capture(reader, output, 3, 0.1, clock=lambda: 100.0, sleep=lambda _: None)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [r["status"]["sequence"] for r in records[:-1]] == [1, 2, 3]
    assert records[-1] == {"record": "complete", "samples": 3, "execution_available": False}
