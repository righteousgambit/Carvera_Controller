"""Declared multi-channel schedules and transfer state; no transport or execution.

Durations, grip dimensions, phase locking and datums are local declarations.
This model cannot qualify physical synchronization, clearance or workholding.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Callable

MAX_BYTES = 256 * 1024
MAX_STEPS = 256
ACTIONS = ("reserve", "machine", "barrier", "spin", "stop", "sync", "grip", "release", "cutoff", "datum")
RESOURCE_KINDS = ("axis", "turret", "spindle", "live_tool")


class PlanCancelled(ValueError):
    pass


@dataclass(frozen=True)
class Resource:
    id: str
    kind: str


@dataclass(frozen=True)
class Piece:
    id: str
    holder: str
    datum: str
    attached: bool
    minimum_grip_mm: float


@dataclass(frozen=True)
class Step:
    id: str
    channel: str
    name: str
    action: str
    duration_s: float
    resources: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    piece: str = ""
    spindle: str = ""
    peer: str = ""
    mode: str = "turn"
    rpm: float = 0
    overlap_mm: float = 0
    grip_mm: float = 0
    datum: str = ""
    barrier: str = ""


@dataclass(frozen=True)
class Plan:
    name: str
    machine_profile: str
    channels: tuple[str, ...]
    resources: tuple[Resource, ...]
    pieces: tuple[Piece, ...]
    barriers: tuple[tuple[str, tuple[str, ...]], ...]
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class PieceState:
    id: str
    holders: tuple[str, ...]
    datum: str
    attached: bool
    remnant_holder: str = ""


@dataclass(frozen=True)
class State:
    pieces: tuple[PieceState, ...]
    spindle_rpm: tuple[tuple[str, float], ...]
    synchronized: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    steps: tuple[str, ...]
    resources: tuple[str, ...] = ()
    at_s: float = 0


@dataclass(frozen=True)
class ScheduledStep:
    step: Step
    start_s: float
    end_s: float
    resources: tuple[str, ...]
    status: str
    before: State
    after: State


@dataclass(frozen=True)
class Review:
    plan: Plan
    digest: str
    steps: tuple[ScheduledStep, ...]
    issues: tuple[Issue, ...]
    duration_s: float
    final_state: State


def _object(value: object, allowed: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name} must be an object")
    if set(value) - allowed:
        raise ValueError(f"{name}: unknown fields {', '.join(sorted(set(value) - allowed))}")
    return value


def _text(value: object, name: str, *, identifier: bool = True) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > (64 if identifier else 128):
        raise ValueError(f"{name} must be nonempty bounded text")
    if identifier and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(f"{name} must use letters, numbers, underscore, dot or hyphen")
    return value


def _array(value: object, name: str, maximum: int) -> list[object]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{name} must contain 1–{maximum} entries")
    return value


def _ids(value: object, name: str, maximum: int = 64) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded array")
    result = tuple(_text(v, name) for v in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} contains duplicates")
    return result


def _number(value: object, name: str, maximum: float = 86400) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} exceeds numeric bounds") from error
    if not math.isfinite(result) or not 0 <= result <= maximum:
        raise ValueError(f"{name} must be finite between 0 and {maximum:g}")
    return result


def plan_from_record(value: object) -> Plan:
    record = _object(
        value, {"schema", "name", "machine_profile", "channels", "resources", "pieces", "barriers", "steps"}, "Plan"
    )
    if type(record.get("schema")) is not int or record["schema"] != 1:
        raise ValueError("Plan schema must be integer 1")
    name = _text(record.get("name"), "Plan name", identifier=False)
    profile = _text(record.get("machine_profile"), "Declared machine profile", identifier=False)
    channels = _ids(record.get("channels"), "Channels", 8)
    if not channels:
        raise ValueError("At least one channel required")
    resources = []
    for item in _array(record.get("resources"), "Resources", 64):
        row = _object(item, {"id", "kind"}, "Resource")
        resource = Resource(_text(row.get("id"), "Resource ID"), _text(row.get("kind"), "Resource kind"))
        if resource.kind not in RESOURCE_KINDS:
            raise ValueError("Unknown resource kind")
        resources.append(resource)
    kinds = {resource.id: resource.kind for resource in resources}
    if len(kinds) != len(resources):
        raise ValueError("Duplicate resource IDs")
    pieces = []
    for item in _array(record.get("pieces"), "Workpieces", 32):
        row = _object(item, {"id", "holder", "datum", "attached", "minimum_grip_mm"}, "Workpiece")
        attached = row.get("attached", False)
        if type(attached) is not bool:
            raise ValueError("Workpiece attached must be boolean")
        piece = Piece(
            _text(row.get("id"), "Workpiece ID"),
            _text(row.get("holder"), "Initial spindle"),
            _text(row.get("datum"), "Initial datum"),
            attached,
            _number(row.get("minimum_grip_mm", 1), "Minimum grip", 1000),
        )
        if kinds.get(piece.holder) != "spindle" or piece.minimum_grip_mm <= 0:
            raise ValueError("Workpiece requires a declared spindle and positive minimum grip")
        pieces.append(piece)
    piece_ids = {piece.id for piece in pieces}
    if len(piece_ids) != len(pieces):
        raise ValueError("Duplicate workpiece IDs")
    barrier_record = record.get("barriers", {})
    if not isinstance(barrier_record, dict) or len(barrier_record) > MAX_STEPS:
        raise ValueError("Barriers must be a bounded object")
    barriers = tuple((_text(k, "Barrier ID"), _ids(v, "Barrier participants", 8)) for k, v in barrier_record.items())
    for _key, participants in barriers:
        if len(participants) < 2 or set(participants) - set(channels):
            raise ValueError("Barrier requires at least two declared channels")
    steps = []
    for index, item in enumerate(_array(record.get("steps"), "Steps", MAX_STEPS)):
        row = _object(item, set(Step.__dataclass_fields__), f"Step {index + 1}")
        text = {
            key: _text(row.get(key), f"Step {index + 1} {key}", identifier=key != "name")
            for key in ("id", "channel", "name", "action")
        }
        optional = {
            key: _text(row[key], key) if key in row and row[key] != "" else ""
            for key in ("piece", "spindle", "peer", "datum", "barrier")
        }
        step = Step(
            **text,
            duration_s=_number(row.get("duration_s"), "Duration"),
            resources=_ids(row.get("resources", []), "Resources"),
            after=_ids(row.get("after", []), "Dependencies", MAX_STEPS),
            mode=_text(row.get("mode", "turn"), "Machining mode"),
            rpm=_number(row.get("rpm", 0), "RPM", 120000),
            overlap_mm=_number(row.get("overlap_mm", 0), "Overlap", 1000),
            grip_mm=_number(row.get("grip_mm", 0), "Grip", 1000),
            **optional,
        )
        if step.channel not in channels or step.action not in ACTIONS or set(step.resources) - set(kinds):
            raise ValueError(f"{step.id}: undeclared channel/resource or unsupported action")
        if step.action != "barrier" and step.duration_s <= 0:
            raise ValueError(f"{step.id}: non-barrier duration must be positive")
        if step.action == "barrier" and (
            step.duration_s != 0 or step.resources or not step.barrier or step.piece or step.spindle or step.peer
        ):
            raise ValueError(f"{step.id}: barrier must have zero duration, an ID and no resource reservations")
        if step.action != "barrier" and step.barrier:
            raise ValueError("Only barrier steps may name a barrier")
        if step.action in ("machine", "grip", "release", "cutoff", "datum") and step.piece not in piece_ids:
            raise ValueError(f"{step.id}: declared workpiece required")
        if (
            step.action in ("machine", "spin", "stop", "sync", "grip", "release", "cutoff", "datum")
            and kinds.get(step.spindle) != "spindle"
        ):
            raise ValueError(f"{step.id}: declared spindle required")
        if step.piece and step.piece not in piece_ids:
            raise ValueError(f"{step.id}: undeclared workpiece")
        if step.spindle and kinds.get(step.spindle) != "spindle":
            raise ValueError(f"{step.id}: undeclared spindle")
        if step.peer and (kinds.get(step.peer) != "spindle" or step.peer == step.spindle):
            raise ValueError(f"{step.id}: peer must be a different declared spindle")
        if step.action in ("sync", "grip", "release", "cutoff") and not step.peer:
            raise ValueError(f"{step.id}: peer spindle required")
        if step.action == "machine" and step.mode not in ("turn", "mill", "inspect"):
            raise ValueError("Machining mode must be turn, mill or inspect")
        if step.action == "datum" and not step.datum:
            raise ValueError("Datum action requires a new declared datum ID")
        steps.append(step)
    ids = {step.id for step in steps}
    if len(ids) != len(steps):
        raise ValueError("Duplicate step IDs")
    if any(set(step.after) - ids or step.id in step.after for step in steps):
        raise ValueError("Unknown or self-referencing dependency")
    expected = dict(barriers)
    for key, participants in barriers:
        members = [step.channel for step in steps if step.action == "barrier" and step.barrier == key]
        if sorted(members) != sorted(participants):
            raise ValueError(f"Barrier {key}: exactly one step per declared participant required")
    if any(step.barrier not in expected for step in steps if step.action == "barrier"):
        raise ValueError("Undeclared barrier")
    return Plan(name, profile, channels, tuple(resources), tuple(pieces), barriers, tuple(steps))


def plan_record(plan: Plan) -> dict[str, object]:
    record: dict[str, object] = json.loads(json.dumps(asdict(plan)))
    # Default fields do not need to consume the bounded interchange budget.
    defaults = {
        name: field.default
        for name, field in Step.__dataclass_fields__.items()
        if name not in ("id", "channel", "name", "action", "duration_s")
    }
    rows = [json.loads(json.dumps(asdict(step))) for step in plan.steps]
    record["steps"] = rows
    for row in rows:
        for name, default in defaults.items():
            if row.get(name) == default or (isinstance(default, tuple) and row.get(name) == list(default)):
                row.pop(name, None)
        for name in ("duration_s", "rpm", "grip_mm", "overlap_mm"):
            value = row.get(name)
            if isinstance(value, float) and math.isfinite(value) and value.is_integer():
                row[name] = int(value)
    record["schema"] = 1
    record["barriers"] = {key: list(values) for key, values in plan.barriers}
    return record


def dump_plan(plan: Plan) -> str:
    """Readable when bounded; compact interchange remains loadable at the limit."""
    record = plan_record(plan)
    pretty = json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False)
    if len(pretty.encode("utf-8")) <= MAX_BYTES:
        return pretty
    compact = json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(compact.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Serialized plan exceeds 256 KiB")
    return compact


def load_plan(text: str) -> Plan:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Plan JSON exceeds 256 KiB")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def numeric(value: str) -> float:
        if len(value) > 64:
            raise ValueError("Numeric token exceeds 64 characters")
        return float(value)

    def integer(value: str) -> int:
        if len(value) > 12:
            raise ValueError("Integer token exceeds 12 characters")
        return int(value)

    def invalid(value: str) -> object:
        raise ValueError(f"Non-finite JSON value: {value}")

    return plan_from_record(
        json.loads(text, object_pairs_hook=unique, parse_int=integer, parse_float=numeric, parse_constant=invalid)
    )


def _check(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise PlanCancelled("Plan review cancelled")


def review_plan(plan: Plan, cancelled: Callable[[], bool] | None = None) -> Review:
    """Group synchronization barriers, then inspect resource and state transitions."""
    # Revalidate public dataclass input; direct construction is not schema admission.
    _check(cancelled)
    plan = plan_from_record(plan_record(plan))
    digest = hashlib.sha256(json.dumps(plan_record(plan), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    groups: dict[str, list[Step]] = {}
    node_for = {
        step.id: ("barrier:" + step.barrier if step.action == "barrier" else "step:" + step.id) for step in plan.steps
    }
    for step in plan.steps:
        groups.setdefault(node_for[step.id], []).append(step)
    predecessors: dict[str, set[str]] = {key: set() for key in groups}
    previous: dict[str, Step] = {}
    for step in plan.steps:
        _check(cancelled)
        dependencies = list(step.after)
        if step.channel in previous:
            dependencies.append(previous[step.channel].id)
        for dependency in dependencies:
            parent, child = node_for[dependency], node_for[step.id]
            if parent == child:
                raise ValueError(f"Barrier {step.barrier} depends on one of its own arrivals")
            predecessors[child].add(parent)
        previous[step.channel] = step
    times: dict[str, tuple[float, float]] = {}
    ranks: dict[str, int] = {}
    pending = set(groups)
    while pending:
        _check(cancelled)
        ready = [key for key in groups if key in pending and not (predecessors[key] - times.keys())]
        if not ready:
            blocked = ", ".join(step.id for key in groups if key in pending for step in groups[key])
            raise ValueError("Synchronization/dependency cycle: " + blocked)
        for key in ready:
            start = max((times[parent][1] for parent in predecessors[key]), default=0.0)
            times[key] = (start, start + groups[key][0].duration_s)
            ranks[key] = len(ranks)
            pending.remove(key)
    locks = {
        step.id: tuple(
            sorted(
                set(step.resources)
                | ({step.spindle} if step.spindle else set())
                | ({step.peer} if step.peer else set())
                | ({"piece:" + step.piece} if step.piece else set())
            )
        )
        for step in plan.steps
    }
    issues: list[Issue] = []
    blocked_ids: set[str] = set()
    for index, left in enumerate(plan.steps):
        _check(cancelled)
        a, b = times[node_for[left.id]]
        for right in plan.steps[index + 1 :]:
            c, d = times[node_for[right.id]]
            shared = tuple(sorted(set(locks[left.id]) & set(locks[right.id])))
            if shared and max(a, c) < min(b, d):
                issues.append(
                    Issue(
                        "resource_conflict",
                        f"{left.id} and {right.id} simultaneously reserve {', '.join(shared)}",
                        (left.id, right.id),
                        shared,
                        max(a, c),
                    )
                )
                blocked_ids.update((left.id, right.id))
    state = State(
        tuple(PieceState(p.id, (p.holder,), p.datum, p.attached) for p in plan.pieces),
        tuple((r.id, 0.0) for r in plan.resources if r.kind == "spindle"),
        (),
    )
    source = {piece.id: piece for piece in plan.pieces}
    kinds = {resource.id: resource.kind for resource in plan.resources}
    scheduled: dict[str, ScheduledStep] = {}
    active: dict[str, State] = {}
    failed_nodes: set[str] = set()
    events = []
    for index, step in enumerate(plan.steps):
        a, b = times[node_for[step.id]]
        events.append((a, 1, ranks[node_for[step.id]], index, step))
        if b > a:
            events.append((b, 0, ranks[node_for[step.id]], index, step))
    for stamp, phase, _rank, _index, step in sorted(events, key=lambda item: item[:4]):
        _check(cancelled)
        node = node_for[step.id]
        start, end = times[node]
        if phase == 1:
            message = ""
            if step.id in blocked_ids:
                message = "Resource conflict; planned action not applied"
            elif predecessors[node] & failed_nodes:
                message = "A predecessor was blocked; planned action not applied"
            else:
                message = _state_error(step, state, source, kinds)
            if message:
                failed_nodes.add(node)
                if step.id not in blocked_ids:
                    issues.append(
                        Issue(
                            "blocked_dependency" if predecessors[node] & failed_nodes else "transfer_state",
                            message,
                            (step.id,),
                            (),
                            stamp,
                        )
                    )
                scheduled[step.id] = ScheduledStep(step, start, end, locks[step.id], "blocked", state, state)
            elif end == start:
                scheduled[step.id] = ScheduledStep(step, start, end, locks[step.id], "planned", state, state)
            else:
                active[step.id] = state
        elif step.id in active:
            before = active.pop(step.id)
            state = _apply(step, state, source)
            scheduled[step.id] = ScheduledStep(step, start, end, locks[step.id], "planned", before, state)
    return Review(
        plan,
        digest,
        tuple(scheduled[step.id] for step in plan.steps),
        tuple(issues),
        max(end for _start, end in times.values()),
        state,
    )


def _state_error(step: Step, state: State, source: dict[str, Piece], kinds: dict[str, str]) -> str:
    speeds = dict(state.spindle_rpm)
    piece = next((p for p in state.pieces if p.id == step.piece), None)
    pair = _pair(step.spindle, step.peer)
    linked = next((p for p in state.synchronized if step.spindle in p), None)
    if step.action == "spin":
        if step.rpm <= 0 or linked:
            return "Spin requires positive RPM and an unlinked spindle"
    elif step.action == "sync":
        if any(step.spindle in p or step.peer in p for p in state.synchronized):
            return "Spindle already belongs to a synchronization pair"
    elif step.action == "stop":
        if any(p != pair for p in state.synchronized if step.spindle in p or step.peer in p):
            return "Stop a synchronized pair together with an explicit peer"
    elif piece is not None:
        if step.action == "grip":
            if step.spindle in piece.holders or len(piece.holders) != 1:
                return "Grip requires one existing holder and a different receiving spindle"
            existing = piece.holders[0]
            if step.peer != existing:
                return "Grip must explicitly reserve the current source spindle as peer"
            live_pair = tuple(sorted((existing, step.spindle)))
            if (speeds[existing] > 0 or speeds[step.spindle] > 0) and live_pair not in state.synchronized:
                return "Rotating co-grip requires a declared synchronized spindle pair"
            if step.grip_mm < source[piece.id].minimum_grip_mm or step.overlap_mm < step.grip_mm:
                return "Grip must meet the minimum engagement and fit within declared overlap"
        elif step.action == "release":
            if step.spindle not in piece.holders or len(piece.holders) < 2:
                return "Release would leave the workpiece unsupported or names a non-holder"
            if step.peer not in piece.holders or step.peer == step.spindle:
                return "Release must explicitly reserve the remaining holder as peer"
            if piece.attached and step.spindle == source[piece.id].holder:
                return "Source stock is still attached; cutoff is required before source release"
        elif step.action == "cutoff":
            if (
                not piece.attached
                or set(piece.holders) != {step.spindle, step.peer}
                or step.spindle != source[piece.id].holder
            ):
                return "Cutoff requires attached stock, source spindle and a declared receiving grip"
            if pair not in state.synchronized or speeds[step.spindle] <= 0:
                return "Cutoff requires declared phase synchronization at positive RPM"
            if not any(kinds[r] == "turret" for r in step.resources):
                return "Cutoff requires a reserved turret/cutting-tool resource"
        elif step.action in ("machine", "datum"):
            if piece.holders != (step.spindle,):
                return "Machining/datum work requires exactly one declared holder"
            if step.action == "datum":
                if speeds[step.spindle] != 0:
                    return "Establish the new datum with the workpiece spindle stopped"
            elif not piece.datum:
                return "Ownership/cutoff invalidated the datum; establish the new reference first"
            elif step.mode == "turn" and speeds[step.spindle] <= 0:
                return "Turning requires a declared rotating workpiece spindle"
            elif step.mode == "turn" and not any(kinds[r] == "turret" for r in step.resources):
                return "Turning requires a reserved turret/cutting-tool resource"
            elif step.mode in ("mill", "inspect") and speeds[step.spindle] != 0:
                return "Milling/inspection requires a declared stopped workpiece spindle; orientation is not evaluated"
            elif step.mode == "mill" and not any(kinds[r] == "live_tool" for r in step.resources):
                return "Milling requires a reserved live-tool drive"
    return ""


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _apply(step: Step, state: State, source: dict[str, Piece]) -> State:
    speeds = dict(state.spindle_rpm)
    pairs = set(state.synchronized)
    pieces = list(state.pieces)
    if step.action in ("spin", "sync"):
        speeds[step.spindle] = step.rpm
        if step.action == "sync":
            speeds[step.peer] = step.rpm
            pairs.add(_pair(step.spindle, step.peer))
    elif step.action == "stop":
        speeds[step.spindle] = 0
        if step.peer:
            speeds[step.peer] = 0
        pairs = {p for p in pairs if step.spindle not in p and (not step.peer or step.peer not in p)}
    for index, piece in enumerate(pieces):
        if piece.id != step.piece:
            continue
        holders, datum, attached, remnant = piece.holders, piece.datum, piece.attached, piece.remnant_holder
        if step.action == "grip":
            holders = tuple(sorted((*holders, step.spindle)))
        elif step.action == "release":
            holders = tuple(h for h in holders if h != step.spindle)
            datum = ""
        elif step.action == "cutoff":
            holders, datum, attached, remnant = (step.peer,), "", False, step.spindle
        elif step.action == "datum":
            datum = step.datum
        pieces[index] = PieceState(piece.id, holders, datum, attached, remnant)
    return State(tuple(pieces), tuple(sorted(speeds.items())), tuple(sorted(pairs)))


def example_record() -> dict[str, object]:
    """Explicit demonstration declarations, not the connected Carvera's hardware."""
    return {
        "schema": 1,
        "name": "DEMO dual-spindle transfer",
        "machine_profile": "Declared dual-spindle example",
        "channels": ["main-channel", "sub-channel"],
        "resources": [
            {"id": name, "kind": kind}
            for name, kind in (
                ("main", "spindle"),
                ("sub", "spindle"),
                ("Z-shared", "axis"),
                ("turret-main", "turret"),
                ("turret-sub", "turret"),
                ("live-sub", "live_tool"),
            )
        ],
        "pieces": [{"id": "part", "holder": "main", "datum": "main-front", "attached": True, "minimum_grip_mm": 4}],
        "barriers": {"ready": ["main-channel", "sub-channel"]},
        "steps": [
            {
                "id": "spin-main",
                "channel": "main-channel",
                "name": "Start declared main spindle",
                "action": "spin",
                "spindle": "main",
                "rpm": 1200,
                "duration_s": 2,
            },
            {
                "id": "rough",
                "channel": "main-channel",
                "name": "Rough front features",
                "action": "machine",
                "piece": "part",
                "spindle": "main",
                "duration_s": 8,
                "resources": ["Z-shared", "turret-main"],
            },
            {
                "id": "wait-main",
                "channel": "main-channel",
                "name": "Wait for transfer approach",
                "action": "barrier",
                "barrier": "ready",
                "duration_s": 0,
            },
            {
                "id": "prepare-sub",
                "channel": "sub-channel",
                "name": "Reserve sub tooling preparation",
                "action": "reserve",
                "duration_s": 5,
                "resources": ["turret-sub", "live-sub"],
            },
            {
                "id": "approach",
                "channel": "sub-channel",
                "name": "Declared transfer approach",
                "action": "reserve",
                "duration_s": 3,
                "resources": ["sub", "Z-shared"],
                "after": ["rough"],
            },
            {
                "id": "wait-sub",
                "channel": "sub-channel",
                "name": "Transfer approach ready",
                "action": "barrier",
                "barrier": "ready",
                "duration_s": 0,
            },
            {
                "id": "sync",
                "channel": "main-channel",
                "name": "Declare phase-locked pair",
                "action": "sync",
                "spindle": "main",
                "peer": "sub",
                "rpm": 1200,
                "duration_s": 1,
                "after": ["wait-sub"],
            },
            {
                "id": "grip",
                "channel": "sub-channel",
                "name": "Receive with declared overlap",
                "action": "grip",
                "peer": "main",
                "piece": "part",
                "spindle": "sub",
                "duration_s": 1,
                "grip_mm": 6,
                "overlap_mm": 10,
                "after": ["sync"],
            },
            {
                "id": "cutoff",
                "channel": "main-channel",
                "name": "Separate part from source stock",
                "action": "cutoff",
                "piece": "part",
                "spindle": "main",
                "peer": "sub",
                "duration_s": 2,
                "resources": ["turret-main"],
                "after": ["grip"],
            },
            {
                "id": "stop-pair",
                "channel": "sub-channel",
                "name": "Stop the synchronized pair",
                "action": "stop",
                "spindle": "sub",
                "peer": "main",
                "duration_s": 1,
                "after": ["cutoff"],
            },
            {
                "id": "datum",
                "channel": "sub-channel",
                "name": "Declare the back-face reference",
                "action": "datum",
                "piece": "part",
                "spindle": "sub",
                "datum": "sub-back",
                "duration_s": 0.5,
            },
            {
                "id": "back-mill",
                "channel": "sub-channel",
                "name": "Mill back-face features",
                "action": "machine",
                "mode": "mill",
                "piece": "part",
                "spindle": "sub",
                "resources": ["Z-shared", "turret-sub", "live-sub"],
                "duration_s": 6,
            },
        ],
    }
