"""Source-bound complete approach exchange; opening recomputes all retained claims."""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from carveracontroller.addons.cad_identity import read_asset_bytes
from carveracontroller.addons.manufacturing_simulation.stock_mesh import MAX_BYTES as MAX_TARGET_BYTES
from carveracontroller.machine.kinematic_profile_io import retain_geometry_bytes
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_clearance_archive import (
    encoded,
    program_review_payload,
    recompute_program_review,
)
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_stock_evolution import (
    evolution_record,
    input_record,
    restore_inputs,
    review_stock_evolution,
)
from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
from carveracontroller.machine.program_surface_archive import BODY_FIELDS, mesh_record, restore_meshes, restore_rotating
from carveracontroller.machine.program_surface_clearance import ProgramSurfaceClearance
from carveracontroller.machine.repeat_parts import vector
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_approach_clearance import ApproachClearance, review_stock_approach
from carveracontroller.machine.stock_approach_path import ApproachStart
from carveracontroller.machine.stock_approach_record import approach_record
from carveracontroller.machine.stock_finishing import FinishingComparison, compare_stock_continuation
from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target

MAX_BYTES = 64 * 1024 * 1024
METHOD = "c1-complete-retained-stock-approach-rigid-groups-v1"
FIELDS = {"schema", "kind", "method", "body", "geometry", "stock", "history", "target", "selection", "report"}


@dataclass(frozen=True)
class ApproachArchive:
    source: ProgramClearanceSource
    work_offsets: Mapping[str, tuple[float, float, float]]
    report: ApproachClearance
    comparison: FinishingComparison | None
    clearance_mm: float
    target_raw: bytes
    sha256: str


def replay_approach(
    payload: dict[str, Any], *, cancelled: Callable[[], bool], phase: Callable[[str], None] = lambda name: None
) -> ApproachArchive:
    if (
        set(payload) != FIELDS
        or type(payload["schema"]) is not int
        or payload["schema"] != 1
        or payload["kind"] != "stock_approach_review"
        or payload["method"] != METHOD
    ):
        raise ValueError("Unsupported complete route archive schema or method")
    if not isinstance(payload["body"], dict) or set(payload["body"]) != BODY_FIELDS:
        raise ValueError("Route archive needs complete source/body declarations")
    from carveracontroller.machine.program_clearance_archive import LEGACY_METHOD
    from carveracontroller.machine.program_clearance_archive import METHOD as BODY_METHOD

    if (
        payload["body"]["method"] not in (LEGACY_METHOD, BODY_METHOD)
        or type(payload["body"]["schema"]) is not int
        or payload["body"]["schema"] != 1
        or payload["body"]["kind"] != "program_machine_clearance"
    ):
        raise ValueError("Unsupported route source/body method")
    phase("Reparse source and machine bodies")
    body = recompute_program_review(payload["body"], cancelled=cancelled)
    phase("Restore complete prepared geometry")
    meshes = restore_meshes(payload["geometry"], body.report, cancelled=cancelled, index_method="surface-directions-v3")
    envelopes = restore_rotating(payload["geometry"]["rotating"], body.report, cancelled, shaped=True)
    phase("Replay complete ordered stock")
    history = review_stock_evolution(body.report, restore_inputs(payload["stock"]), envelopes, cancelled=cancelled)
    if encoded(evolution_record(history, cancelled=cancelled)) != encoded(payload["history"]):
        raise ValueError("Saved route stock history differs from source replay")
    selection = payload["selection"]
    if not isinstance(selection, dict) or set(selection) != {
        "stock",
        "segment_index",
        "label",
        "cell",
        "tool",
        "clearance_mm",
        "continuation",
        "start",
    }:
        raise ValueError("Route archive requires explicit complete selection and start")
    if (
        type(selection["tool"]) is not int
        or not isinstance(selection["cell"], list)
        or len(selection["cell"]) != 3
        or any(type(v) is not int for v in selection["cell"])
        or not isinstance(selection["label"], str)
    ):
        raise ValueError("Route archive needs canonical cell/tool/state selection")
    phase("Reconstruct selected stock move")
    state = reconstruct_stock_move(
        body.report, history, envelopes, selection["stock"], selection["segment_index"], cancelled=cancelled
    )
    phase("Replay retained continuation")
    comparison = None
    continuation = selection["continuation"]
    if continuation is not None:
        if not isinstance(continuation, dict) or set(continuation) != {"tool", "end_line"}:
            raise ValueError("Route continuation requires retained tool and source range")
        comparison = compare_stock_continuation(
            body.report,
            history,
            envelopes,
            state,
            selection["stock"],
            continuation["tool"],
            continuation["end_line"],
            cancelled=cancelled,
        )
    phase("Validate embedded target bytes")
    target = payload["target"]
    if (
        not isinstance(target, dict)
        or set(target) != {"path_label", "raw_base64", "source_sha256", "units", "translation_mm"}
        or not isinstance(target["path_label"], str)
        or len(target["path_label"]) > 4096
        or not isinstance(target["raw_base64"], str)
        or len(target["raw_base64"]) > 4 * ((MAX_TARGET_BYTES + 2) // 3)
        or target["units"] not in ("mm", "inch")
    ):
        raise ValueError("Route archive needs bounded embedded target bytes and explicit units")
    raw = base64.b64decode(target["raw_base64"], validate=True)
    if len(raw) > MAX_TARGET_BYTES or hashlib.sha256(raw).hexdigest() != target["source_sha256"]:
        raise ValueError("Embedded route target integrity mismatch")
    if cancelled():
        raise InterruptedError("Route target replay cancelled")
    # Fixed private filename, never the incoming provenance label. Existing STL
    # parser validates exact bytes; the temporary file is removed after parsing.
    with tempfile.TemporaryDirectory(prefix="carvera-route-target-") as folder:
        path = Path(folder) / "target.stl"
        path.write_bytes(raw)
        prepared = prepare_stock_target(
            state,
            selection["stock"],
            str(path),
            units=target["units"],
            translation_mm=vector(target["translation_mm"]),
            cancelled=cancelled,
        )
    prepared = replace(prepared, source_path=target["path_label"])
    phase("Compare complete target grids")
    analysis = analyze_stock_target(prepared, state, comparison, cancelled=cancelled)
    phase("Recompute selected cell inspection")
    inspection = inspect_target_cell(
        analysis,
        selection["label"],
        tuple(selection["cell"]),
        tool=selection["tool"],
        approach_clearance_mm=selection["clearance_mm"],
        cancelled=cancelled,
    )
    origin = selection["start"]
    if not isinstance(origin, dict) or set(origin) != {"machine_mm", "origin", "observed"}:
        raise ValueError("Route start must retain declared or historical status provenance")
    pose = None
    if origin["observed"] is not None:
        row = origin["observed"]
        if not isinstance(row, dict) or set(row) != set(ObservedPose.__dataclass_fields__):
            raise ValueError("Historical route start needs complete packet metadata")
        row = dict(row, machine_mm=vector(row["machine_mm"]), work_mm=vector(row["work_mm"]))
        if (
            row["state"] != "Idle"
            or type(row["tool"]) is not int
            or row["tool"] != selection["tool"]
            or type(row["wcs_index"]) is not int
            or not 0 <= row["wcs_index"] <= 6
            or type(row["tool_length_mm"]) not in (int, float)
            or row["rotation_deg"] != 0
            or row["rotary_deg"] != 0
        ):
            raise ValueError("Historical route packet differs from supported captured Idle context")
        pose = ObservedPose(**row)
    start = ApproachStart(vector(origin["machine_mm"]), origin["origin"], pose)
    parent = ProgramSurfaceClearance(
        body.report,
        meshes,
        (),
        (),
        0,
        0,
        0,
        sum(len(m.triangles) for rows in meshes.values() for m in rows.values()),
        rotating_envelopes=envelopes,
        stock_evolution=history,
    )
    phase("Review complete machine approach")
    result = review_stock_approach(inspection, parent, route_start=start, cancelled=cancelled)
    phase("Compare exact retained route evidence")
    if encoded(approach_record(result, cancelled=cancelled)) != encoded(payload["report"]):
        raise ValueError("Saved route evidence differs from complete source/stock/target/route recomputation")
    return ApproachArchive(body.source, body.work_offsets, result, comparison, selection["clearance_mm"], raw, "")


def save_approach_review(
    path: str | Path,
    source: ProgramClearanceSource,
    work_offsets: Mapping[str, tuple[float, float, float]],
    result: ApproachClearance,
    *,
    comparison: FinishingComparison | None = None,
    clearance_mm: float = 1,
    target_raw: bytes | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    phase: Callable[[str], None] = lambda name: None,
) -> str:
    phase("Capture complete retained route context")
    parent, inspection = result.parent, result.inspection
    if parent.stock_evolution is None or result.start_evidence is None or result.material is None:
        raise ValueError("Save requires a complete approach route with retained stock and start context")
    if {m.index_method for rows in parent.meshes.values() for m in rows.values()} != {"surface-directions-v3"}:
        raise ValueError("Route method requires complete directional prepared geometry")
    target = inspection.analysis.target
    raw = (
        target_raw
        if target_raw is not None
        else read_asset_bytes(Path(target.source_path), MAX_TARGET_BYTES, cancelled=cancelled)
    )
    if len(raw) > MAX_TARGET_BYTES or hashlib.sha256(raw).hexdigest() != target.source_sha256:
        raise ValueError("Target bytes changed; reload the target before saving its route")
    body_payload = program_review_payload(source, work_offsets, parent.body_review, cancelled=cancelled)
    body_payload["work_offsets"] = {name: vector(value) for name, value in work_offsets.items()}
    payload = {
        "schema": 1,
        "kind": "stock_approach_review",
        "method": METHOD,
        "body": body_payload,
        "geometry": mesh_record(parent, cancelled=cancelled),
        "stock": input_record(parent.stock_evolution.inputs),
        "history": evolution_record(parent.stock_evolution, cancelled=cancelled),
        "target": {
            "path_label": target.source_path,
            "raw_base64": base64.b64encode(raw).decode("ascii"),
            "source_sha256": target.source_sha256,
            "units": target.source_units,
            "translation_mm": target.translation_mm,
        },
        "selection": {
            "stock": target.stock,
            "segment_index": inspection.analysis.segment_index,
            "label": inspection.label,
            "cell": inspection.cell,
            "tool": inspection.approach.tool if inspection.approach else None,
            "clearance_mm": clearance_mm,
            "continuation": None
            if comparison is None
            else {"tool": comparison.candidate_tool, "end_line": comparison.end_line},
            "start": asdict(result.start_evidence),
        },
        "report": approach_record(result, cancelled=cancelled),
    }
    if len(encoded(payload)) > MAX_BYTES - 100:
        raise ValueError("Complete route archive exceeds64 MiB; no partial exchange")
    # Reparse encoded JSON so save exercises the same canonical wire types as load.
    replay_approach(json.loads(encoded(payload)), cancelled=cancelled, phase=phase)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    data = encoded(payload) + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("Complete route archive exceeds64 MiB")
    phase("Publish verified route bytes")
    return retain_geometry_bytes(path, data, cancelled=cancelled)


def load_approach_review(
    path: str | Path,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    phase: Callable[[str], None] = lambda name: None,
) -> ApproachArchive:
    if cancelled():
        raise InterruptedError("Route archive loading cancelled")
    phase("Decode bounded complete route archive")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Complete route archive exceeds64 MiB")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if cancelled():
                raise InterruptedError("Route archive decoding cancelled")
            if key in result:
                raise ValueError("Duplicate route archive JSON field")
            result[key] = value
        return result

    def integer(text: str) -> int:
        if len(text) > 20:
            raise ValueError("Route archive integer exceeds20 characters")
        return int(text)

    def constant(text: str) -> None:
        raise ValueError("Nonfinite route archive number: " + text)

    try:
        payload = json.loads(raw, object_pairs_hook=unique, parse_int=integer, parse_constant=constant)
        if not isinstance(payload, dict) or set(payload) != FIELDS | {"sha256"}:
            raise ValueError("Unsupported route archive fields")
        digest = payload.pop("sha256")
        if digest != hashlib.sha256(encoded(payload)).hexdigest():
            raise ValueError("Route archive integrity mismatch")
        result = replay_approach(payload, cancelled=cancelled, phase=phase)
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        OverflowError,
        TypeError,
        KeyError,
        AttributeError,
    ) as exc:
        raise ValueError("Expected bounded complete UTF-8 route archive") from exc
    if cancelled():
        raise InterruptedError("Route archive loading cancelled before delivery")
    return replace(result, sha256=hashlib.sha256(raw).hexdigest())
