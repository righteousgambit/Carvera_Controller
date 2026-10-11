"""Packet-scoped machining evidence. No sensor reading is inherited from GUI caches."""

from __future__ import annotations

import hashlib
import math
import re
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from os import PathLike
from typing import Any, Protocol, cast

NumericFields = Mapping[str, Sequence[float]]
JsonObject = dict[str, Any]


class IncrementalHash(Protocol):
    def update(self, data: bytes) -> None: ...
    def hexdigest(self) -> str: ...


STATUS_MINIMUM = {
    "MPos": 3,
    "WPos": 3,
    "R": 1,
    "G": 1,
    "C": 4,
    "F": 3,
    "S": 3,
    "PWM": 1,
    "T": 2,
    "W": 1,
    "L": 5,
    "P": 3,
    "A": 1,
    "O": 1,
    "H": 1,
    "SE": 9,
    "SI": 2,
    "SC": 4,
    "SS": 14,
    "SA": 4,
    "SF": 7,
    "SP": 4,
    "ST": 5,
    "SQ": 6,
}
DIAGNOSTIC_MINIMUM = {
    "S": 2,
    "L": 2,
    "F": 2,
    "V": 2,
    "G": 1,
    "T": 1,
    "R": 1,
    "C": 1,
    "E": 6,
    "P": 2,
    "A": 2,
    "I": 1,
    "RSSI": 1,
    "SI": 2,
}
EVENT_FIELDS = (
    "sequence",
    "tick_us",
    "tick_wraps",
    "kind",
    "input_mask",
    "input_valid_mask",
    "halt_reason",
    "atc_stage",
    "executing_line",
    "parsed_line",
    "x",
    "y",
    "z",
    "rpm",
    "pwm",
    "context_valid",
    "active_tool",
    "target_tool",
    "tlo",
    "context_age_us",
    "spindle_age_us",
)
INPUT_NAMES = (
    "x_motor_alarm",
    "y_motor_alarm",
    "z_motor_alarm",
    "spindle_alarm",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "cover",
    "probe",
    "tool_setter",
    "atc_home",
    "tool_present",
    "estop",
)


def parse_numeric_fields(text: str, *, status: bool = False) -> tuple[str | None, dict[str, list[float]]]:
    """Validate the entire packet before any cached machine state can change."""
    if not isinstance(text, str) or len(text) > 16384:
        raise ValueError("invalid or oversized telemetry frame")
    left, right = ("<", ">") if status else ("{", "}")
    start, end = text.find(left), text.rfind(right)
    if start != 0 or end <= start or text[end + 1 :].strip("\r\n\0") or left in text[1:end] or right in text[1:end]:
        raise ValueError("malformed telemetry delimiters")
    parts = text[start + 1 : end].split("|")
    state = parts.pop(0) if status else None
    if status and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cast(str, state)):
        raise ValueError("invalid machine state")
    fields: dict[str, list[float]] = {}
    minimum = STATUS_MINIMUM if status else DIAGNOSTIC_MINIMUM
    for part in parts:
        name, separator, values = part.partition(":")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or name in fields:
            raise ValueError("missing or duplicate telemetry field")
        # Stock Carvera firmware pads numeric list items (notably L:) with
        # ASCII spaces. Normalize only that padding; embedded whitespace,
        # control characters and empty values must still reject the packet.
        tokens = [token.strip(" ") for token in values.split(",")]
        if any(
            not re.fullmatch(r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?", token) for token in tokens
        ):
            raise ValueError("invalid numeric telemetry token")
        numbers = [float(value) for value in tokens]
        if not numbers or not all(math.isfinite(number) for number in numbers):
            raise ValueError("nonfinite telemetry field")
        if len(numbers) < minimum.get(name, 1):
            raise ValueError("short telemetry field: " + name)
        if name in {"SE", "SI", "SC", "SF", "SP", "ST", "SQ", "EH", "EE"} and any(
            number < 0 or number > 2**32 - 1 or number != int(number) for number in numbers
        ):
            raise ValueError("invalid unsigned evidence field: " + name)
        exact = {"SE": 9, "SI": 2, "SC": 4, "SA": 4, "SF": 7, "SP": 4, "ST": 5, "SS": 14, "SQ": 6, "EH": 5, "EE": 1}
        if name in exact and len(numbers) != exact[name]:
            raise ValueError("invalid evidence field length: " + name)
        if name == "ST" and (numbers[0] != 1 or numbers[1] > 7 or any(v > 2**32 - 1 for v in numbers[2:])):
            raise ValueError("invalid measurement age field")
        if name == "SC" and int(numbers[3]) & ~19:
            raise ValueError("invalid executing context validity")
        if name == "SA" and (
            any(v < 0 or v != int(v) for v in numbers[:3]) or numbers[3] < -1 or numbers[3] != int(numbers[3])
        ):
            raise ValueError("invalid ATC evidence field")
        if name == "SI" and any(v > 65535 for v in numbers):
            raise ValueError("invalid raw input bitmask")
        if name == "SE" and (numbers[2] not in (0, 1) or any(v > 2**32 - 1 for v in numbers[1:])):
            raise ValueError("invalid source identity")
        if name == "SQ" and (numbers[0] != 1 or numbers[3] > 2 or numbers[5] > 2):
            raise ValueError("invalid contact queue evidence")
        if name == "EH" and (numbers[0] != 1 or numbers[2] not in (0, 1) or numbers[3] > 16):
            raise ValueError("invalid event history header")
        if name == "EE" and numbers[0] not in (0, 1):
            raise ValueError("invalid event completion status")
        if name == "SF" and numbers[6] > 2 or name == "SP" and numbers[3] not in (0, 1):
            raise ValueError("invalid fault persistence state")
        if (
            status
            and name == "C"
            and (any(v < 0 or v != int(v) for v in numbers) or numbers[2] not in (0, 1) or numbers[3] not in (0, 1))
        ):
            raise ValueError("invalid coordinate modes")
        if status and name == "G" and (numbers[0] != int(numbers[0]) or not 0 <= numbers[0] <= 8):
            raise ValueError("invalid coordinate system")
        if name == "SS":
            unsigned_indices = (0, 5, 6, 7, 8, 13)
            if (
                any(
                    numbers[index] < 0 or numbers[index] > 2**32 - 1 or numbers[index] != int(numbers[index])
                    for index in unsigned_indices
                )
                or numbers[0] > 100
                or not 0 <= numbers[1] <= numbers[9] <= numbers[2]
                or not 0 <= numbers[3] <= numbers[11] <= numbers[4] <= 1
                or numbers[10] < 0
                or numbers[12] < 0
            ):
                raise ValueError("invalid spindle transient statistics")
        if name == "PWM" and not 0 <= numbers[0] <= 1:
            raise ValueError("invalid spindle command duty")
        fields[name] = numbers
    if status and not {"MPos", "WPos"}.issubset(fields):
        raise ValueError("status has no complete position")
    if "SE" in fields and fields["SE"][0] != 1:
        raise ValueError("unsupported sensor evidence version")
    return state, fields


def raw_inputs(fields: NumericFields) -> dict[str, bool | None]:
    pair = fields.get("SI")
    if not pair:
        return dict.fromkeys(INPUT_NAMES)
    mask, valid = map(int, pair[:2])
    return {name: bool(mask & (1 << index)) if valid & (1 << index) else None for index, name in enumerate(INPUT_NAMES)}


def source_field_validity(fields: NumericFields) -> dict[str, bool | None]:
    """Interpret an already validated source extension; absence remains unknown."""
    source = fields.get("SE")
    return {
        name: bool(int(source[6]) & bit) if source else None
        for name, bit in (
            ("spindle_status", 1),
            ("spindle_temperature", 2),
            ("power_temperature", 4),
            ("tool_status", 8),
            ("probe_voltage", 16),
            ("parsed_progress", 32),
            ("executing_block", 64),
        )
    }


def packet_context(state: str | None, fields: NumericFields, arrival: float) -> JsonObject:
    def value(key: str, index: int = 0) -> float | None:
        values = fields.get(key, ())
        return values[index] if len(values) > index else None

    s = fields.get("S", ())
    spindle_temperature = s[4] if len(s) >= 9 or len(s) == 5 else value("F", 3)
    # Legacy firmware serializes absent thermistors as zero; availability is unknown.
    power_temperature = s[5] if len(s) >= 9 else (s[4] if len(s) == 8 else None)
    source = fields.get("SE")
    metadata: dict[str, int] | None = None
    if source:
        metadata = dict(
            zip(
                (
                    "version",
                    "boot_id",
                    "boot_id_valid",
                    "sequence",
                    "tick_us",
                    "tick_wraps",
                    "valid_mask",
                    "position_source",
                    "feed_source",
                ),
                map(int, source[:9]),
            )
        )
    if source:
        valid = int(source[6])
        if not valid & (1 << 1):
            spindle_temperature = None
        if not valid & (1 << 2):
            power_temperature = None
    timing = fields.get("ST")
    measurement_ages: dict[str, JsonObject] = {}
    if timing:
        for index, (key, basis) in enumerate(
            (
                ("spindle_temperature", "filtered thermistor sample"),
                ("power_temperature", "filtered thermistor sample"),
                ("probe_voltage", "accepted UART voltage receipt; radio acquisition unknown"),
            )
        ):
            valid_age = bool(int(timing[1]) & (1 << index)) and timing[index + 2] != 2**32 - 1
            measurement_ages[key] = {"age_us": int(timing[index + 2]) if valid_age else None, "basis": basis}
        if not int(timing[1]) & 1:
            spindle_temperature = None
        if not int(timing[1]) & 2:
            power_temperature = None
    unit_mode = value("C", 2)
    scale = 25.4 if unit_mode == 1 else 1.0 if unit_mode == 0 else None

    def position_mm(key: str) -> list[float] | None:
        position = fields.get(key)
        return (
            [v * scale if index < 3 else v for index, v in enumerate(position)]
            if scale is not None and position
            else None
        )

    return {
        "state": state,
        "arrival_monotonic_s": arrival,
        "field_presence": {key: key in fields for key in STATUS_MINIMUM},
        "field_freshness": {
            "current_packet": sorted(fields),
            "sensor_acquisition_age_s": None,
            "basis": "present in report; acquisition age unknown unless separately reported",
        },
        "raw_fields": deepcopy(fields),
        "source": metadata,
        "field_validity": source_field_validity(fields),
        "measurement_ages": measurement_ages,
        "spindle_temperature": spindle_temperature,
        "power_temperature": power_temperature if source else (None if power_temperature == 0 else power_temperature),
        "power_temperature_availability": "unknown" if not source else "source validity mask",
        "probe_voltage": value("W")
        if (not source or int(source[6]) & 16) and (not timing or int(timing[1]) & 4)
        else None,
        "tool": value("T") if not source or int(source[6]) & 8 else None,
        "tlo": value("T", 1) if not source or int(source[6]) & 8 else None,
        "target_tool": value("T", 2),
        "target_collet": value("T", 3),
        "atc_state": value("A"),
        "atc_timing": fields.get("SA"),
        "halt_reason": value("H") if "H" in fields else (0 if state in ("Idle", "Run", "Pause", "Home") else None),
        "halt_state_source": "explicit H field"
        if "H" in fields
        else (
            "status state (H omitted when not halted)" if state in ("Idle", "Run", "Pause", "Home") else "unavailable"
        ),
        "wcs": value("G"),
        "rotation": value("R"),
        "modes": fields.get("C"),
        "machine_position": position_mm("MPos"),
        "work_position": position_mm("WPos"),
        "position_units": "mm XYZ; degrees rotary" if scale is not None else "unknown",
        "status_linear_unit": "inch" if unit_mode == 1 else "mm" if unit_mode == 0 else None,
        "commanded_feed_mm_min": cast(float, value("F", 1)) * scale
        if scale is not None and value("F", 1) is not None
        else None,
        "planner_feed_mm_min": cast(float, value("F")) * scale
        if scale is not None and value("F") is not None
        else None,
        "position_semantics": (
            "planner milestone"
            if metadata and metadata["position_source"] == 2
            else "issued-step accounting"
            if metadata and metadata["position_source"] == 1
            else "firmware reported position; derivation unavailable"
        )
        + "; not independent physical feedback",
        "feed_semantics": (
            "planner nominal feed"
            if metadata and metadata["feed_source"] == 1
            else "firmware reported feed; derivation unavailable"
        )
        + "; not measured physical velocity",
        "pwm_semantics": "spindle drive command; not measured current or torque",
        "accessory_commands": {
            "vacuum_mode": value("S", 3),
            "external_output": s[-1] if len(s) >= 8 else None,
            "laser": fields.get("L"),
        },
        "progress": {
            "reported_file_line": value("P"),
            "percent": value("P", 1),
            "seconds": value("P", 2),
            "playing": value("P", 3),
            "source": "firmware player progress; not executing block",
        },
        "motion": dict(zip(("executing_line", "parsed_line", "queue_depth", "executing_valid"), fields["SC"]))
        if "SC" in fields
        else None,
        "raw_inputs": raw_inputs(fields),
        "spindle_transients": dict(
            zip(
                (
                    "sample_count",
                    "rpm_min",
                    "rpm_max",
                    "pwm_min",
                    "pwm_max",
                    "saturation_us",
                    "window_us",
                    "window_end_tick_us",
                    "window_end_wraps",
                    "rpm_mean",
                    "rpm_population_variance",
                    "pwm_mean",
                    "pwm_population_variance",
                    "recovery_us",
                ),
                fields["SS"],
            )
        )
        if "SS" in fields and fields["SS"][0] > 0
        else None,
        "fault": fields.get("SF"),
        "previous_fault": fields.get("SP"),
        "contact_queue": fields.get("SQ"),
    }


def compact_program(program: JsonObject | None) -> JsonObject | None:
    if program is None:
        return None
    summary = deepcopy({key: value for key, value in program.items() if key != "operations"})
    summary["operation_count"] = program.get("operation_count", len(program.get("operations", ())))
    summary["operations_omitted"] = True
    return summary


class RunEvidence:
    def __init__(self, capacity: int = 300) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 10000:
            raise ValueError("invalid evidence capacity")
        self.dump_invalid = False
        self.dump_sequences: list[int] = []
        self.dump_last_clock: int | None = None
        self.history: deque[JsonObject] = deque(maxlen=capacity)
        self.events: deque[JsonObject] = deque(maxlen=capacity)
        self.latest: JsonObject | None = None
        self.diagnostic: JsonObject | None = None
        self.program: JsonObject | None = None
        self.rejected = 0
        self.dump_header: dict[str, float] | None = None
        self.dump_received = 0
        self.dump_receipts: deque[JsonObject] = deque(maxlen=32)

    def observe(self, raw_frame: str | None, state: str | None, fields: NumericFields, arrival: float) -> JsonObject:
        if type(arrival) not in (int, float) or not math.isfinite(arrival) or arrival < 0:
            raise ValueError("invalid packet arrival time")
        context = packet_context(state, fields, arrival)
        context["program"] = compact_program(self.program)
        if self.program:
            motion = context["motion"]
            line = int(motion["executing_line"]) if motion and int(motion["executing_valid"]) & 1 else None
            context["operation"] = next(
                (op for op in reversed(self.program["operations"]) if line is not None and op["line"] <= line), None
            )
        else:
            context["operation"] = None
        self.latest = context
        record = {
            "schema": "carvera.run.v1",
            "kind": "status",
            "raw_frame": raw_frame,
            "arrival_monotonic_s": arrival,
            "context": context,
        }
        self.history.append(record)
        return record

    def observe_diagnostic(self, raw_frame: str, fields: NumericFields, arrival: float) -> JsonObject:
        if type(arrival) not in (int, float) or not math.isfinite(arrival) or arrival < 0:
            raise ValueError("invalid diagnostic arrival time")
        self.diagnostic = {
            "arrival_monotonic_s": arrival,
            "fields": deepcopy(fields),
            "raw_frame": raw_frame,
            "semantics": "accessory fields are commands; switches are input states",
        }
        record = {"schema": "carvera.run.v1", "kind": "diagnostic", **self.diagnostic}
        self.history.append(record)
        return record

    def observe_event(self, raw_frame: str, arrival: float) -> JsonObject:
        if type(arrival) not in (int, float) or not math.isfinite(arrival) or arrival < 0:
            raise ValueError("invalid event arrival time")
        _, fields = parse_numeric_fields(raw_frame)
        if len(fields) != 1:
            raise ValueError("event history frames must contain one field")
        if "EH" in fields:
            header = fields["EH"]
            if header[0] != 1 or header[2] not in (0, 1):
                raise ValueError("unsupported event history header")
            self.dump_header = dict(zip(("version", "boot_id", "boot_valid", "event_count", "last_sequence"), header))
            self.dump_received = 0
            self.dump_invalid = False
            self.dump_sequences = []
            self.dump_last_clock = None
            record = {
                "schema": "carvera.run.v1",
                "kind": "event_header",
                "raw_frame": raw_frame,
                "arrival_monotonic_s": arrival,
                "header": deepcopy(self.dump_header),
            }
        elif "EE" in fields:
            status = int(fields["EE"][0])
            complete = bool(
                status == 0
                and self.dump_header
                and not self.dump_invalid
                and self.dump_received == self.dump_header["event_count"]
                and (not self.dump_sequences or self.dump_sequences[-1] == self.dump_header["last_sequence"])
            )
            record = {
                "schema": "carvera.run.v1",
                "kind": "event_receipt",
                "raw_frame": raw_frame,
                "arrival_monotonic_s": arrival,
                "complete": complete,
                "status": status,
                "header": deepcopy(self.dump_header),
                "received_events": self.dump_received,
                "sequence_integrity": not self.dump_invalid,
            }
            self.dump_receipts.append(record)
            self.dump_header = None
        else:
            values = fields.get("EV")
            if values is None or len(values) not in (15, 19, len(EVENT_FIELDS)):
                raise ValueError("malformed firmware event")
            if any(value < 0 or value > 2**32 - 1 or value != int(value) for value in values[:10]):
                raise ValueError("invalid firmware event identity")
            if values[4] > 65535 or values[5] > 65535 or values[13] < 0 or not 0 <= values[14] <= 1:
                raise ValueError("invalid event input/spindle values")
            if len(values) >= 19 and (
                values[15] != int(values[15])
                or not 0 <= values[15] <= 31
                or any(v != int(v) or v < -1 for v in values[16:18])
            ):
                raise ValueError("invalid event context")
            if len(values) == 21 and any(v < 0 or v > 2**32 - 1 or v != int(v) for v in values[19:]):
                raise ValueError("invalid event context age")
            event: JsonObject = dict(zip(EVENT_FIELDS, values))
            context_valid = int(event.get("context_valid", 0))
            if not context_valid & 1:
                event["executing_line"] = None
            if not context_valid & 2:
                event["parsed_line"] = None
            if not context_valid & 4:
                event["rpm"] = event["pwm"] = None
            if not context_valid & 8:
                event["active_tool"] = event["target_tool"] = event["tlo"] = None
            record = {
                "schema": "carvera.run.v1",
                "kind": "event",
                "raw_frame": raw_frame,
                "arrival_monotonic_s": arrival,
                "event": event,
                "source_header": deepcopy(self.dump_header),
                "raw_values": values,
            }
            if self.dump_header:
                sequence = int(values[0])
                clock = int(values[2]) * 2**32 + int(values[1])
                if (
                    self.dump_received >= self.dump_header["event_count"]
                    or self.dump_sequences
                    and (sequence - self.dump_sequences[-1]) % 2**32 != 1
                    or self.dump_last_clock is not None
                    and clock < self.dump_last_clock
                ):
                    self.dump_invalid = True
                if len(self.dump_sequences) < 16:
                    self.dump_sequences.append(sequence)
                else:
                    self.dump_invalid = True
                self.dump_last_clock = clock
            self.dump_received += 1
        self.events.append(record)
        self.history.append(record)
        return record

    def snapshot(self, now: float | None = None) -> JsonObject:
        if now is not None and (type(now) not in (int, float) or not math.isfinite(now)):
            now = None
        result: JsonObject = (
            deepcopy(self.latest) if self.latest else {"source": None, "program": compact_program(self.program)}
        )
        result["program"] = compact_program(self.program)
        arrival = result.get("arrival_monotonic_s")
        result["arrival_age_s"] = now - arrival if now is not None and arrival is not None and now >= arrival else None
        result["diagnostics"] = deepcopy(self.diagnostic)
        if "accessory_commands" in result:
            commands = result["accessory_commands"]
            age = now - self.diagnostic["arrival_monotonic_s"] if self.diagnostic and now is not None else None
            fields = cast(JsonObject, self.diagnostic)["fields"] if age is not None and 0 <= age <= 2.5 else {}
            commands["diagnostic_commands"] = {
                "spindle": fields.get("S"),
                "fan": fields.get("F"),
                "vacuum": fields.get("V"),
                "light": fields.get("G"),
                "tool_sensor_power": fields.get("T"),
                "air": fields.get("R"),
                "probe_charge_power": fields.get("C"),
            }
            result["diagnostic_commands_provenance"] = {
                "arrival_age_s": age,
                "fresh": bool(fields),
                "semantics": "reported commands; not actual airflow/rotation",
            }
        result["event_dump_receipts"] = deepcopy(list(self.dump_receipts))
        if self.diagnostic and now is not None:
            diagnostic_age = now - self.diagnostic["arrival_monotonic_s"]
            result["diagnostics"]["arrival_age_s"] = (
                diagnostic_age if math.isfinite(now) and diagnostic_age >= 0 else None
            )
        result["rejected_packets"] = self.rejected
        return result

    def set_program(self, path: str | PathLike[str], lines: Iterable[str] | None = None) -> JsonObject:
        parsed_digest = hashlib.sha256() if lines is not None else None
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        operations: deque[JsonObject] = deque(maxlen=4096)
        operation_count = 0
        for number, line in enumerate(lines or (), 1):
            cast(IncrementalHash, parsed_digest).update(line.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
            match = re.search(
                r"(?:operation(?:\s+name)?\s*[:=]|\(\s*(?:(?:2D|3D)\s+)?(?:adaptive|pocket|contour|drill|face|bore|trace|engrave)[^\r\n)]*)([^\r\n]*)",
                line,
                re.I,
            )
            if match:
                operation_count += 1
                operations.append(
                    {
                        "line": number,
                        "name": match.group(0).strip("(); ").split(":", 1)[-1].strip()[:160],
                        "label": match.group(0).strip("(); ")[:160],
                    }
                )
        self.program = {
            "local_path": str(path),
            "sha256": digest.hexdigest(),
            "parsed_lines_sha256": parsed_digest.hexdigest() if parsed_digest is not None else None,
            "identity_source": "local file bytes",
            "machine_file_identity": "unverified",
            "operations": list(operations),
            "operation_count": operation_count,
            "operations_dropped": max(0, operation_count - len(operations)),
            "operations_retained": "latest",
            "requested_machine_path": None,
            "request": None,
        }
        return deepcopy(self.program)
