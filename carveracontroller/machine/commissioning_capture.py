"""Bounded historical LinuxCNC capture import; never grants live capability."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from carveracontroller.machine.linuxcnc_hal import HalObservation, decode_hal, hal_changes
from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader, SignalTransition, StatusObservation, integer


@dataclass(frozen=True)
class CommissioningCapture:
    source: str
    sha256: str
    ini_sha256: str
    observations: tuple[StatusObservation, ...]
    transitions: tuple[tuple[SignalTransition, ...], ...]
    utc_times: tuple[str, ...]
    complete: bool
    failure: str
    hal_observations: tuple[HalObservation | None, ...] = ()


def decode_status(data: dict[str, Any], reader: LinuxCNCStatusReader) -> StatusObservation:
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        raise ValueError("Unsupported status schema")
    if data.get("backend") != "linuxcnc" or data.get("machine_id") != reader.machine_id:
        raise ValueError("Capture backend or machine identity changed")
    raw_joints = data["joints"]
    if not isinstance(raw_joints, list) or len(raw_joints) > 64:
        raise ValueError("Invalid joint list")
    joints = []
    for index, joint in enumerate(raw_joints):
        if integer(joint["index"]) != index or joint["kind"] not in ("linear", "angular"):
            raise ValueError("Invalid joint identity")
        joints.append(
            {
                "jointType": 1 if joint["kind"] == "linear" else 2,
                "units": joint["units_per_mm_or_degree"],
                "output": joint["commanded"],
                "input": joint["actual"],
                "ferror_current": joint["following_error"],
                "velocity": joint["velocity"],
                **{
                    name: joint[name]
                    for name in (
                        "homed",
                        "homing",
                        "enabled",
                        "fault",
                        "min_hard_limit",
                        "max_hard_limit",
                        "min_soft_limit",
                        "max_soft_limit",
                    )
                },
            }
        )
    for name in ("actual_position", "digital_inputs", "digital_outputs", "analog_inputs", "analog_outputs"):
        if not isinstance(data[name], list) or len(data[name]) > 1024:
            raise ValueError("Invalid status channel array")
    reader.status = SimpleNamespace(
        poll=lambda: None,
        joints=len(joints),
        joint=joints,
        actual_position=data["actual_position"],
        axis_mask=data["axis_mask"],
        linear_units=data["linear_units_per_mm"],
        angular_units=data["angular_units_per_degree"],
        ini_filename=data["ini_filename"],
        din=data["digital_inputs"],
        dout=data["digital_outputs"],
        ain=data["analog_inputs"],
        aout=data["analog_outputs"],
        **{
            name: data[key]
            for name, key in (
                ("task_state", "task_state"),
                ("task_mode", "task_mode"),
                ("interp_state", "interp_state"),
                ("motion_mode", "motion_mode"),
                ("exec_state", "execution_state"),
                ("tool_in_spindle", "tool_in_spindle"),
            )
        },
    )
    if integer(data["sequence"]) != reader.sequence + 1 or integer(data["generation"]) != 0:
        raise ValueError("Capture sequence or generation is discontinuous")
    return reader.poll(data["observed_at"])


def load_capture(path: str | Path) -> CommissioningCapture:
    source = Path(path)
    with source.open("rb") as stream:
        raw = stream.read(20 * 1024 * 1024 + 1)
    return decode_capture(raw, str(source))


def decode_capture(raw: bytes, source: str = "embedded capture") -> CommissioningCapture:
    if not isinstance(raw, bytes):
        raise ValueError("Capture bytes required")
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Capture exceeds 20 MiB")
    observations, transitions, times = [], [], []
    reader = None
    identity = None
    complete, failure, terminal = False, "", False
    hal_observations = []
    hal_present = None
    previous_hal = None
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            if terminal:
                raise ValueError("Records appear after capture terminal record")
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("Capture record must be an object")
            if record.get("record") == "complete":
                if integer(record["samples"]) != len(observations) or record.get("execution_available") is not False:
                    raise ValueError("Completion does not match observed samples")
                complete, terminal = True, True
            elif record.get("record") == "failure":
                if (
                    integer(record["sample"]) != len(observations)
                    or not isinstance(record["error"], str)
                    or len(record["error"]) > 2048
                ):
                    raise ValueError("Invalid capture failure")
                failure, terminal = record["error"], True
            elif record.get("record") == "observation":
                if len(observations) >= 10000:
                    raise ValueError("Capture exceeds 10,000 samples")
                data = record["status"]
                if not isinstance(data, dict):
                    raise ValueError("Status must be an object")
                for key, limit in (("machine_id", 256), ("ini_filename", 4096)):
                    if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit:
                        raise ValueError("Invalid capture identity")
                digest = record["ini_sha256"]
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("Invalid INI digest")
                utc = record["captured_at_utc"]
                if not isinstance(utc, str) or len(utc) > 128:
                    raise ValueError("Invalid capture timestamp")
                stamp = datetime.fromisoformat(utc.replace("Z", "+00:00"))
                offset = stamp.utcoffset()
                if offset is None or offset.total_seconds() != 0:
                    raise ValueError("UTC capture timestamp required")
                current = (data["machine_id"], data["ini_filename"], digest)
                if identity is not None and identity != current:
                    raise ValueError("Capture configuration identity changed")
                identity = current
                if reader is None:
                    reader = LinuxCNCStatusReader(data["machine_id"], None)
                observation = decode_status(data, reader)
                present = "hal" in record
                if hal_present is not None and present != hal_present:
                    raise ValueError("HAL capture coverage changed")
                hal_present = present
                hal = None
                changes = reader.transitions
                if present:
                    if not isinstance(record["hal"], dict):
                        raise ValueError("HAL observation must be an object")
                    hal = decode_hal(record["hal"])
                    if (
                        hal.machine_id != observation.machine_id
                        or hal.sequence != observation.sequence
                        or hal.generation != 0
                        or hal.observed_at < observation.observed_at
                        or (previous_hal is not None and previous_hal.observed_at > observation.observed_at)
                    ):
                        raise ValueError("HAL/NML capture identity or timing differs")
                    changes += hal_changes(previous_hal, hal)
                previous_hal = hal
                hal_observations.append(hal)
                observations.append(observation)
                # Recompute transitions; never trust imported event assertions.
                transitions.append(changes)
                times.append(utc)
            else:
                raise ValueError("Unknown capture record")
    except (KeyError, TypeError, AttributeError, OverflowError, UnicodeError) as exc:
        raise ValueError("Malformed commissioning capture") from exc
    if not observations:
        raise ValueError("Capture contains no observations")
    assert identity is not None
    return CommissioningCapture(
        str(source),
        hashlib.sha256(raw).hexdigest(),
        identity[2],
        tuple(observations),
        tuple(transitions),
        tuple(times),
        complete,
        failure,
        tuple(hal_observations),
    )
