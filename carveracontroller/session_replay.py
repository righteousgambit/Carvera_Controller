"""Bounded offline replay through production parsers; globals restored on every exit."""

from __future__ import annotations

import math
import os
import re
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .machine.evidence_io import JsonObject, iter_jsonl
from .machine.sensor_run_recording import parse_numeric_fields

MAX_REPLAY_BYTES = 64 * 1024 * 1024
MAX_REPLAY_RECORDS = 10000
MAX_REPLAY_LINE_BYTES = 2 * 1024 * 1024


def replay_jsonl(path: str | os.PathLike[str], *, max_records: int = MAX_REPLAY_RECORDS) -> JsonObject:
    from carveracontroller.Controller import Controller

    with Controller._evidence_global_lock:
        if any(
            instance._connecting
            or instance._closing
            or instance.stream is not None
            or (instance.thread and instance.thread.is_alive())
            or any(thread.is_alive() for thread in list(getattr(instance, "_receive_threads", ())))
            for instance in list(Controller._instances)
        ):
            raise ValueError("offline replay requires all machine connections disconnected")
        return _replay_jsonl(path, max_records=max_records)


def _program(value: Any, existing: JsonObject | None = None) -> JsonObject | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid replay program metadata")
    if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value["sha256"]):
        raise ValueError("invalid replay program identity")
    if value.get("operations_omitted") is True and "operations" not in value:
        count = value.get("operation_count")
        if type(count) is not int or not 0 <= count <= 2**32 - 1:
            raise ValueError("invalid compact program operation count")
        merged = deepcopy(value)
        if existing and existing.get("sha256") == value["sha256"]:
            merged["operations"] = deepcopy(existing.get("operations", []))
            merged["operations_unavailable"] = existing.get("operations_unavailable", False)
        else:
            merged["operations"] = []
            merged["operations_unavailable"] = True
        return merged
    operations = value.get("operations")
    if not isinstance(operations, list) or len(operations) > 4096:
        raise ValueError("invalid replay operations")
    previous_line = 0
    for operation in operations:
        if not isinstance(operation, dict) or type(operation.get("line")) is not int or operation["line"] < 1:
            raise ValueError("invalid replay operation line")
        if operation["line"] <= previous_line:
            raise ValueError("replay operation lines must be strictly ordered")
        previous_line = operation["line"]
        if any(
            key in operation and (not isinstance(operation[key], str) or len(operation[key]) > 160)
            for key in ("name", "label")
        ):
            raise ValueError("invalid replay operation label")
    return deepcopy(value)


def _validate_frame(raw: Any, kind: Any) -> str:
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("missing or oversized replay frame")
    if raw.startswith("<"):
        parse_numeric_fields(raw, status=True)
    elif raw.startswith("{"):
        _, fields = parse_numeric_fields(raw)
        if raw.startswith("{PRH:"):
            from .machine.probe_evidence import parse_latched_contact

            if len(fields) != 1 or parse_latched_contact(raw) is None:
                raise ValueError("invalid replay probe hit")
        elif raw.startswith(("{EV:", "{EH:", "{EE:")) and len(fields) != 1:
            raise ValueError("invalid replay event envelope")
    elif kind != "alarm" or not re.search(r"\b(?:error|alarm)\b", raw, re.I):
        raise ValueError("unsupported replay frame")
    return raw


def _provider(declarations: JsonObject) -> Callable[[], JsonObject]:
    saved = deepcopy(declarations)

    def provider() -> JsonObject:
        return deepcopy(saved)

    return provider


def _replay_jsonl(path: str | os.PathLike[str], *, max_records: int = MAX_REPLAY_RECORDS) -> JsonObject:
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    if type(max_records) is not int or not 0 < max_records <= MAX_REPLAY_RECORDS:
        raise ValueError("invalid replay record bound")
    cnc_class: Any = CNC
    saved_vars, saved_scale, saved_rotate = deepcopy(CNC.vars), cnc_class.UnitScale, CNC.can_rotate_wcs
    outputs: deque[JsonObject] = deque(maxlen=300)
    accepted = 0
    previous_arrival: float | None = None
    recorded_plan: JsonObject | None = None
    recorded_restart: JsonObject | None = None
    rejected = 0
    try:
        # Integration with the existing untyped controller; all external inputs
        # are narrowed here before invoking its production parser methods.
        factory: Any = Controller
        cnc_factory: Any = CNC
        controller: Any = factory(cnc_factory(), None)
        controller._evidence_writes_enabled = False
        for record in iter_jsonl(
            path, max_bytes=MAX_REPLAY_BYTES, max_line_bytes=MAX_REPLAY_LINE_BYTES, max_records=max_records
        ):
            raw = record.get("raw_frame")
            arrival = record.get("arrival_monotonic_s")
            if (
                not isinstance(arrival, (int, float))
                or isinstance(arrival, bool)
                or not math.isfinite(arrival)
                or arrival < 0
            ):
                rejected += 1
                continue
            if previous_arrival is not None and arrival < previous_arrival:
                rejected += 1
                continue
            saved_program = controller.run_evidence.program
            saved_provider = controller.measurement_context_provider
            saved_arrival = controller._evidence_arrival_override
            try:
                kind = record.get("kind")
                context = record.get("context")
                if context is not None and not isinstance(context, dict):
                    raise ValueError("invalid replay context")
                program = _program(context.get("program"), saved_program) if context else None
                declarations = context.get("measurement_declarations") if context else None
                if declarations is not None and not isinstance(declarations, dict):
                    raise ValueError("invalid replay measurement declarations")
                if kind not in (
                    "advisory_control",
                    "recovery_verification",
                    "recovery_status",
                    "recovery_plan",
                    "program_manifest",
                    "recording_restart",
                    "recipe",
                    "outcome",
                ):
                    raw_frame = _validate_frame(raw, kind)
                if kind in ("recovery_verification", "recovery_status"):
                    if type(record.get("start_line")) is not int or record["start_line"] < 1:
                        raise ValueError("invalid replay recovery line")
                if kind == "advisory_control" and record.get("action") not in ("baseline", "reset", "shadow", "off"):
                    raise ValueError("invalid advisory control replay")
                controller._evidence_arrival_override = arrival
                if context is not None:
                    controller.run_evidence.program = program
                    controller.measurement_context_provider = (
                        _provider(declarations) if declarations is not None else None
                    )
                if kind == "recording_restart":
                    # This receipt may identify forensic sidecars. Never follow
                    # those paths or infer their contents from the journal.
                    recorded_restart = deepcopy(record)
                elif kind == "program_manifest":
                    manifest = _program(record.get("data"))
                    if manifest is None or "operations" not in manifest or manifest.get("operations_unavailable"):
                        raise ValueError("invalid program manifest")
                    controller.run_evidence.program = manifest
                elif kind == "recovery_plan":
                    plan = record.get("plan")
                    if (
                        not isinstance(plan, dict)
                        or not isinstance(plan.get("commands"), list)
                        or not 1 <= len(plan["commands"]) <= 128
                    ):
                        raise ValueError("invalid recorded recovery plan")
                    if any(
                        not isinstance(command, str)
                        or not command
                        or len(command) > 4096
                        or any(char in command for char in "\r\n\0")
                        for command in plan["commands"]
                    ):
                        raise ValueError("invalid recorded recovery command")
                    if not isinstance(plan.get("scope"), str) or not re.fullmatch(r"[0-9a-f]{64}", plan["scope"]):
                        raise ValueError("invalid recorded recovery plan scope")
                    recorded_plan = deepcopy(plan)
                elif kind == "advisory_control":
                    action = record["action"]
                    if action == "baseline":
                        controller.adaptive_monitor.capture_baseline()
                    elif action == "reset":
                        controller.adaptive_monitor.reset()
                    else:
                        controller.adaptive_monitor.enabled = action == "shadow"
                elif kind == "recovery_verification":
                    from .machine.recovery_policy import RecoveryVerification

                    data = record.get("data")
                    if not isinstance(data, dict):
                        raise ValueError("invalid replay recovery verification")
                    verification = RecoveryVerification(**data)
                    controller._recovery_verification = verification
                    controller._recovery_line = record["start_line"]
                elif kind == "recovery_status":
                    controller._recovery_line = record["start_line"]
                elif kind in ("recipe", "outcome"):
                    data = record.get("data")
                    if not isinstance(data, dict):
                        raise ValueError("invalid advisory replay input")
                    if kind == "recipe":
                        controller.adaptive_monitor.configure_recipe(data)
                    else:
                        controller.adaptive_monitor.record_outcome(data)
                elif raw_frame.startswith("<"):
                    controller.parseBracketAngle(raw_frame)
                elif raw_frame.startswith(("{EV:", "{EH:", "{EE:")):
                    controller.run_evidence.observe_event(raw_frame, arrival)
                elif raw_frame.startswith("{PRH:") or kind == "alarm":
                    controller.parseLine(raw_frame)
                else:
                    controller.parseBigParentheses(raw_frame)
            except (ValueError, TypeError, KeyError):
                # Rejected metadata cannot become context for a later good frame;
                # its timestamp cannot advance the replay clock either.
                controller.run_evidence.program = saved_program
                controller.measurement_context_provider = saved_provider
                controller._evidence_arrival_override = saved_arrival
                rejected += 1
                continue
            previous_arrival = float(arrival)
            accepted += 1
            outputs.append(
                {
                    "arrival_monotonic_s": arrival,
                    "context": controller.sensor_context_snapshot(),
                    "advisory": controller.adaptive_monitor.snapshot(arrival),
                    "recorded_recording_restart": deepcopy(recorded_restart),
                    "recorded_restart_semantics": "opaque journal receipt; referenced files not read",
                    "recorded_recovery_plan": deepcopy(recorded_plan),
                    "recorded_plan_semantics": "recorded commands for review; never executed",
                    "recovery": controller.recovery_assessment(controller._recovery_line)
                    if controller._recovery_line
                    else None,
                }
            )
        return {
            "schema": "carvera.replay.v1",
            "offline": True,
            "machine_commands_sent": 0,
            "accepted": accepted,
            "rejected": rejected,
            "outputs": list(outputs),
            "retained_output_limit": 300,
            "discarded_outputs": max(0, accepted - len(outputs)),
            "source_quality": controller.adaptive_monitor.quality.snapshot(previous_arrival),
        }
    finally:
        CNC.vars.clear()
        CNC.vars.update(saved_vars)
        cnc_class.UnitScale = saved_scale
        CNC.can_rotate_wcs = saved_rotate
