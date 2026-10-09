"""Bounded multi-stock occupancy exchange. Digests prove bytes, not physical setup."""

from __future__ import annotations

import json
import math
import os
import tempfile
import zlib
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.stock_model import validate_residual_stock
from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.addons.manufacturing_simulation.planning import SimulationReport
from carveracontroller.machine.geometry_changes import asset_problems, asset_state, digest_context
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan
from carveracontroller.machine.repeat_simulation import RepeatSimulation
from carveracontroller.machine.simulation_preview import simulation_segments, stock_geometry

LIMIT = 16 * 1024 * 1024


def verify_assets(context: Mapping[str, Any], *, cancelled: Callable[[], bool] | None = None) -> None:
    # Refresh every declared asset off the UI thread; never accept an old loaded digest alone.
    current = json.loads(json.dumps(context))
    entries = []
    for definition in current["tools"].values():
        if definition:
            entries.extend((definition, key, 24 * 1024 * 1024) for key in ("cutter_asset", "holder_asset"))
    entries.extend((component, "asset", 8 * 1024 * 1024) for component in current["components"].values())
    for owner, key, limit in entries:
        asset = owner[key]
        if asset:
            owner[key] = asset_state(asset["path"], asset["loaded_sha256"], limit)
    plan = RepeatPartPlan.from_dict(current["repeat_plan"])
    for source in {p.stock_source for p in plan.parts if p.stock_source is not None}:
        reference = source.reference
        if asset_digest(reference["source_path"], 24 * 1024 * 1024, cancelled=cancelled) != reference["source_sha256"]:
            raise ValueError("Imported array stock source bytes changed; reload before exchanging results")
    problems = asset_problems(current)
    if problems:
        raise ValueError("\n".join(problems))
    if digest_context(current) != digest_context(context):
        raise ValueError("CAD bytes changed; reload the selected asset before exchanging results")


def save_repeat_result(
    path: str | Path,
    result: RepeatSimulation,
    context: Mapping[str, Any],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> None:
    if cancelled():
        raise InterruptedError("Saving cancelled; previous file retained")
    verify_assets(context, cancelled=cancelled)
    if result.plan.to_dict() != context["repeat_plan"] or result.program_hash != context["program"]:
        # JSON normalization makes tuples and lists equivalent, while retaining all numeric values.
        if (
            digest_context(result.plan.to_dict()) != digest_context(context["repeat_plan"])
            or result.program_hash != context["program"]
        ):
            raise ValueError("Result does not match its program and array context")
    if len(result.snapshots) != len(result.plan.parts) or len(result.reports) != len(result.plan.parts):
        raise ValueError("Result has no complete per-part occupancy; recompute before saving")
    reports = []
    for report in result.reports:
        record = {
            key: getattr(report, key) for key in SimulationReport.__dataclass_fields__ if key != "clearance_details"
        }
        reports.append(record)
    payload: dict[str, Any] = {"schema": 1, "context": context, "stocks": list(result.snapshots), "reports": reports}
    payload["sha256"] = digest_context(payload)
    data = json.dumps(payload, allow_nan=False).encode()
    if len(data) > LIMIT:
        raise ValueError("Multi-stock result exceeds 16 MiB")
    target = Path(path)
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=".repeat-result-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled():
            raise InterruptedError("Saving cancelled; previous file retained")
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_repeat_result(
    path: str | Path,
    program: ProgramOperations,
    context: Mapping[str, Any],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> RepeatSimulation:
    def unique(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate multi-stock result field")
            output[key] = value
        return output

    with Path(path).open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Multi-stock result exceeds 16 MiB")
    try:
        payload = json.loads(raw, object_pairs_hook=unique)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid multi-stock result encoding or nesting") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "context", "stocks", "reports", "sha256"}:
        raise ValueError("Unknown or missing multi-stock result fields")
    if type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("Unsupported multi-stock result schema")
    recorded_hash = payload.pop("sha256")
    if digest_context(payload) != recorded_hash:
        raise ValueError("Multi-stock result integrity mismatch")
    if digest_context(payload["context"]) != digest_context(context) or program.file_hash != context["program"]:
        raise ValueError("Result does not match current program, array, machine, tools or workholding")
    verify_assets(context, cancelled=cancelled)
    plan = RepeatPartPlan.from_dict(context["repeat_plan"]).prepared(cancelled=cancelled)
    snapshots, records = payload["stocks"], payload["reports"]
    if (
        not isinstance(snapshots, list)
        or not isinstance(records, list)
        or len(snapshots) != len(plan.parts)
        or len(records) != len(plan.parts)
    ):
        raise ValueError("Result needs one stock and report for every declared part")
    voxel_count = 0
    reports, geometries = [], {}
    mapped = ProgramOperations.from_text(
        "\n".join(program.lines), work_offsets={p.wcs: p.work_offset_mm for p in plan.parts}
    )
    if any(checkpoint.state.recovery_errors for checkpoint in mapped.checkpoints):
        raise ValueError("Result program contains unsupported modal or rotary commands")
    segments = simulation_segments(mapped, work_offsets={p.wcs: p.work_offset_mm for p in plan.parts})
    faces = 100_000
    for part, snapshot, record in zip(plan.parts, snapshots, records):
        if cancelled():
            raise InterruptedError("Result loading cancelled; previous scene retained")
        if not isinstance(snapshot, dict) or not isinstance(record, dict):
            raise ValueError("Invalid per-part stock or report")
        resolution = snapshot.get("resolution_mm")
        if (
            isinstance(resolution, bool)
            or not isinstance(resolution, (int, float))
            or not math.isfinite(resolution)
            or not 0.05 <= resolution <= 10
        ):
            raise ValueError("Invalid multi-stock resolution")
        if resolution != context["resolution_mm"]:
            raise ValueError("Snapshot resolution differs from captured inputs")
        low, high = part.bounds
        if part.stock_source is not None:
            ref = part.stock_source.reference
            # Match source-to-machine floating-point placement before decoding
            # any occupancy, including nonzero source minima. A forged large
            # grid must not consume the generic decoder's eight-million budget.
            shift = tuple(c - a for c, a in zip(low, ref["minimum_mm"]))
            a, b = ref["minimum_mm"], ref["maximum_mm"]
            low = (a[0] + shift[0], a[1] + shift[1], a[2] + shift[2])
            high = (b[0] + shift[0], b[1] + shift[1], b[2] + shift[2])
        if (
            snapshot.get("minimum") != list(low)
            or snapshot.get("maximum") != list(high)
            or snapshot.get("schema") not in ((1, 3) if part.stock_source is not None else (1,))
        ):
            raise ValueError("Snapshot stock placement differs from declared array")
        voxel_count += math.prod(math.ceil((b - a) / resolution) for a, b in zip(low, high))
        if voxel_count > 2_000_000:
            raise ValueError("Result exceeds shared two-million voxel budget")
        try:
            stock = StockVolume.from_snapshot(snapshot, cancelled=cancelled)
        except zlib.error as exc:
            raise ValueError("Invalid compressed stock occupancy") from exc
        validate_residual_stock(plan.setup(part, machine_space=True), stock, cancelled=cancelled)
        expected_fields = set(SimulationReport.__dataclass_fields__) - {"clearance_details"}
        if set(record) != expected_fields or record["cancelled"] is not False:
            raise ValueError("Incomplete or invalid per-part report")
        if type(record["segments_processed"]) is not int or record["segments_processed"] != len(segments):
            raise ValueError("Report segment count differs from program")
        for key in ("removed_volume_mm3", "remaining_volume_mm3", "resolution_mm"):
            if type(record[key]) not in (int, float) or not math.isfinite(record[key]) or record[key] < 0:
                raise ValueError("Report contains invalid quantities")
        if record["resolution_mm"] != resolution or record["remaining_volume_mm3"] != stock.remaining_volume_mm3:
            raise ValueError("Report differs from saved occupancy")
        if not math.isclose(record["removed_volume_mm3"], stock.removed_volume_mm3, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("Removed volume differs from saved occupancy")
        if record["status"] not in ("unknown", "potential_collision", "clear_conservative_bounds") or not isinstance(
            record["qualification"], str
        ):
            raise ValueError("Invalid report qualification")
        candidates = record["candidates"]
        if (
            not isinstance(candidates, list)
            or len(candidates) > 100_000
            or any(
                not isinstance(c, list)
                or len(c) != 3
                or type(c[0]) is not int
                or not 1 <= c[0] <= len(program.lines)
                or any(not isinstance(v, str) or len(v) > 200 for v in c[1:])
                for c in candidates
            )
        ):
            raise ValueError("Invalid collision candidates")
        record["candidates"] = tuple(tuple(c) for c in candidates)
        reports.append(SimulationReport(**record))
        mesh = stock_geometry(stock, max_faces=faces, cancelled=cancelled)
        faces -= len(mesh.indices) // 6
        geometries[part.wcs] = GeometrySnapshot(tuple(mesh.vertices), tuple(mesh.indices))
    return RepeatSimulation(
        plan, program.file_hash, segments, tuple(reports), geometries, mapped.unresolved_motion_lines, tuple(snapshots)
    )
