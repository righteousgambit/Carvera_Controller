"""Bounded offline replay through the production parser and advisory monitor."""

from __future__ import annotations

import json
import math
from collections import deque
from copy import deepcopy
from pathlib import Path

from .machine.run_recording import parse_numeric_fields

MAX_REPLAY_BYTES = 64 * 1024 * 1024
MAX_REPLAY_RECORDS = 10000
MAX_REPLAY_LINE_BYTES = 65536


def replay_jsonl(path, *, max_records=MAX_REPLAY_RECORDS):
    from carveracontroller.Controller import Controller

    with Controller._evidence_global_lock:
        if any(
            instance.stream is not None or (instance.thread and instance.thread.is_alive())
            for instance in list(Controller._instances)
        ):
            raise ValueError("offline replay requires all machine connections disconnected")
        return _replay_jsonl(path, max_records=max_records)


def _replay_jsonl(path, *, max_records=MAX_REPLAY_RECORDS):
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    if not isinstance(max_records, int) or not 0 < max_records <= MAX_REPLAY_RECORDS:
        raise ValueError("invalid replay record bound")
    path = Path(path).expanduser()
    if path.stat().st_size > MAX_REPLAY_BYTES:
        raise ValueError("replay exceeds 64 MiB")
    saved_vars, saved_scale, saved_rotate = deepcopy(CNC.vars), CNC.UnitScale, CNC.can_rotate_wcs
    controller = Controller(CNC(), None)
    controller._evidence_writes_enabled = False
    outputs = deque(maxlen=300)
    accepted = 0
    previous_arrival = None
    rejected = 0
    try:
        with path.open("rb") as stream:
            for _ in range(max_records):
                line = stream.readline(MAX_REPLAY_LINE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_REPLAY_LINE_BYTES:
                    raise ValueError("oversized replay record")
                try:
                    record = json.loads(line)
                except ValueError:
                    rejected += 1
                    continue
                if not isinstance(record, dict):
                    rejected += 1
                    continue
                raw = record.get("raw_frame")
                arrival = record.get("arrival_monotonic_s")
                if not isinstance(arrival, (int, float)) or isinstance(arrival, bool) or not math.isfinite(arrival):
                    rejected += 1
                    continue
                if previous_arrival is not None and arrival < previous_arrival:
                    rejected += 1
                    continue
                previous_arrival = arrival
                controller._evidence_arrival_override = arrival
                try:
                    kind = record.get("kind")
                    context = record.get("context")
                    if isinstance(context, dict):
                        controller.run_evidence.program = deepcopy(context.get("program"))
                        declarations = deepcopy(context.get("measurement_declarations"))
                        controller.measurement_context_provider = (
                            (lambda saved=declarations: saved) if isinstance(declarations, dict) else None
                        )
                    if kind == "advisory_control":
                        action = record.get("action")
                        if action == "baseline":
                            controller.adaptive_monitor.capture_baseline()
                        elif action == "reset":
                            controller.adaptive_monitor.reset()
                        elif action in ("shadow", "off"):
                            controller.adaptive_monitor.enabled = action == "shadow"
                        else:
                            raise ValueError("invalid advisory control replay")
                    elif kind == "recovery_verification":
                        from .machine.recovery_policy import RecoveryVerification

                        controller._recovery_verification = RecoveryVerification(**record["data"])
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
                    elif not isinstance(raw, str):
                        raise ValueError("missing replay frame")
                    elif raw.startswith("<"):
                        parse_numeric_fields(raw, status=True)
                        controller.parseBracketAngle(raw)
                    elif raw.startswith(("{EV:", "{EH:", "{EE:")):
                        controller.run_evidence.observe_event(raw, arrival)
                    elif raw.startswith("{PRH:") or kind == "alarm":
                        controller.parseLine(raw)
                    elif raw.startswith("{"):
                        controller.parseBigParentheses(raw)
                    else:
                        raise ValueError("unsupported replay frame")
                except (ValueError, TypeError, KeyError):
                    rejected += 1
                    continue
                accepted += 1
                outputs.append(
                    {
                        "arrival_monotonic_s": arrival,
                        "context": controller.sensor_context_snapshot(),
                        "advisory": controller.adaptive_monitor.snapshot(arrival),
                        "recovery": controller.recovery_assessment(controller._recovery_line)
                        if controller._recovery_line
                        else None,
                    }
                )
            if stream.read(1):
                raise ValueError("replay record count exceeded")
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
        CNC.UnitScale = saved_scale
        CNC.can_rotate_wcs = saved_rotate
