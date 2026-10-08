"""Prepare a recorded nominal scene from retained bytes, without UI or CNC access."""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, fields
from pathlib import Path

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup, build_scene, vector
from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.addons.tool_visualization.mesh_builder import ToolMesh, build_tool_meshes
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.job_packages import MAX_TOTAL, load_package, resolve_setup_assets
from carveracontroller.machine.recording_setup import validate_setup_binding
from carveracontroller.machine.run_recording import RecordingReplay


@dataclass
class HistoricalScene:
    setup: MachineSetup
    profile: MachineProfile | None
    components: dict[str, MachineProfile]
    offset: tuple[float, float, float]
    rotation: float
    jaw: float
    definitions: dict[int, ToolDefinition]
    meshes: dict[int, ToolMesh]
    fallback: ToolMesh
    geometry: dict[str, Geometry | GeometrySnapshot]
    context: dict[str, object]
    scale: float


def definitions_from_snapshot(records: object) -> dict[int, ToolDefinition]:
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError("Recorded tools must be a list of at most 1000 definitions")
    allowed = {field.name for field in fields(ToolDefinition)}
    result: dict[int, ToolDefinition] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) - allowed:
            raise ValueError("Unsupported recorded tool fields")
        number = record.get("number")
        if type(number) is not int or not 1 <= number <= 9999 or number in result:
            raise ValueError("Recorded tool numbers must be unique integers from 1 to 9999")
        definition = ToolDefinition(**{**record, "tool_type": ToolType(record.get("tool_type", "unknown"))})
        for field in fields(ToolDefinition):
            value = getattr(definition, field.name)
            if field.name in ("number", "tool_type"):
                continue
            if field.name in (
                "description",
                "vendor",
                "product_id",
                "type_name",
                "geometry_path",
                "holder_geometry_path",
                "drawing_path",
                "source_url",
                "geometry_sha256",
                "holder_geometry_sha256",
            ):
                if not isinstance(value, str) or len(value) > 16384:
                    raise ValueError("Invalid recorded tool text")
            elif value is not None and (
                type(value) not in (int, float) or not 0 <= value <= 1000 or not math.isfinite(value)
            ):
                raise ValueError("Invalid recorded tool dimensions")
        if definition.geometry_unit_scale != 1:
            raise ValueError("Recorded library tools must use millimetres")
        for key in ("diameter", "shank_diameter", "length", "flute_length", "shoulder_length", "thread_pitch"):
            if getattr(definition, key) is not None and getattr(definition, key) <= 0:
                raise ValueError("Recorded positive tool dimension is zero")
        if definition.thread_teeth is not None or definition.thread_tip_offset is not None:
            if (
                definition.tool_type != ToolType.THREAD_MILL
                or type(definition.thread_teeth) is not int
                or not 2 <= definition.thread_teeth <= 200
                or definition.thread_pitch is None
                or definition.thread_tip_offset is None
                or definition.flute_length is None
            ):
                raise ValueError(
                    "Recorded multi-form tool requires thread shape, pitch, complete teeth and tooth datum"
                )
            if (
                definition.thread_tip_offset + definition.thread_teeth * definition.thread_pitch
                > definition.flute_length + 1e-9
            ):
                raise ValueError("Recorded complete tooth stack exceeds flute length")
        result[number] = definition
    return result


def prepare_historical_scene(
    replay: RecordingReplay,
    archive: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    cam_tools: dict[int, ToolDefinition],
    cam_scale: float,
    scale: float,
    selected_program: str | os.PathLike[str],
    inspection_hash: str,
) -> HistoricalScene:
    context = replay.payload.get("context")
    if context is None:
        raise ValueError("This recording has no retained setup archive")
    binding = context.get("configuration")
    if binding is None:
        raise ValueError("This recording has no retained setup archive")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (scale, cam_scale)):
        raise ValueError("Invalid preview scale")
    with Path(archive).open("rb") as source:
        encoded = source.read(MAX_TOTAL + 1)
    if len(encoded) != binding["size_bytes"] or hashlib.sha256(encoded).hexdigest() != binding["sha256"]:
        raise ValueError("Recorded setup archive bytes differ")
    # Freeze the exact validated bytes before parsing, so path replacement cannot
    # switch configuration between its digest check and archive interpretation.
    destination = Path(destination)
    destination.mkdir(parents=True)
    frozen = destination / "setup.cvjob"
    with frozen.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    if frozen.read_bytes() != encoded:
        raise OSError("Recorded setup copy readback differs")
    loaded = load_package(frozen, destination=destination / "assets")
    validate_setup_binding(loaded.package, context)
    with Path(selected_program).open("rb") as source:
        selected_bytes = source.read(16 * 1024 * 1024 + 1)
    if selected_bytes != loaded.package.program:
        raise ValueError("Open the exact recorded program before restoring its scene")
    # The operation inspector uses universal-newline text, while recording keeps
    # original bytes. Check these two identities separately, including CRLF files.
    normalized = loaded.package.program.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != inspection_hash:
        raise ValueError("The loaded program inspection does not match the recorded program")
    resolved = resolve_setup_assets(loaded)
    stock = resolved["stock"]
    setup = MachineSetup(
        stock["work_offset_mm"], stock["size_mm"], stock["origin_mm"], False, stock.get("rotation_deg", 0)
    )
    profile_path = resolved["machine"].get("cad_path")
    profile = MachineProfile.load(profile_path) if profile_path else None
    components = {}
    for item in resolved["fixtures"]:
        group = item["group"]
        if group not in ("fixture", "workholding") or group in components:
            raise ValueError("Unsupported or duplicate recorded scene component")
        cad = MachineProfile.load(item["cad_path"])
        if not cad.groups[group].indices:
            raise ValueError("Recorded component has no geometry for its group")
        components[group] = cad
    vise = resolved["vise"]
    offset = vector(vise.get("offset_mm", (0, 0, 0)), "Recorded vise offset")
    rotation, jaw = vise.get("rotation_deg", 0), vise.get("jaw_offset_mm", 0)
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000 for v in (*offset, rotation, jaw)):
        raise ValueError("Invalid recorded workholding placement")
    definitions = definitions_from_snapshot(resolved["inspection_plan"].get("tool_definitions_mm", []))
    for definition in definitions.values():
        for path_key, digest_key in (
            ("geometry_path", "geometry_sha256"),
            ("holder_geometry_path", "holder_geometry_sha256"),
        ):
            path, expected = getattr(definition, path_key), getattr(definition, digest_key)
            if path and expected and hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError("Recorded tool geometry digest differs")
    meshes, fallback = build_tool_meshes(cam_tools, scale=scale * cam_scale)
    library_meshes, _ = build_tool_meshes(definitions, scale=scale)
    meshes.update(library_meshes)
    geometry: dict[str, Geometry | GeometrySnapshot] = {}
    geometry.update(profile.scene(setup, offset, rotation, jaw) if profile else build_scene(setup))
    for group, cad in components.items():
        geometry[group] = cad.scene(setup, offset, rotation, jaw)[group]
    # Retained files are independently checked after all decoders have read them.
    for reference, path in loaded.asset_paths.items():
        if path.read_bytes() != loaded.asset_bytes[reference]:
            raise ValueError("Recorded asset changed during scene preparation")
    return HistoricalScene(
        setup,
        profile,
        components,
        offset,
        rotation,
        jaw,
        definitions,
        meshes,
        fallback,
        geometry,
        {
            "configuration": binding,
            "inspection_plan": resolved["inspection_plan"],
            "session_id": replay.payload["session_id"],
        },
        scale,
    )


def scene_inventory(prepared: HistoricalScene) -> str:
    """Describe the active nominal scene without promoting declarations to measurements."""

    def component(group: str) -> str:
        if group in prepared.components:
            return str(prepared.components[group].model).replace("\n", " ")[:90]
        geometry = prepared.geometry.get(group)
        return "included in machine CAD" if prepared.profile and geometry and geometry.indices else "schematic"

    machine = str(prepared.profile.model).replace("\n", " ")[:90] if prepared.profile else "schematic"
    dimensions = prepared.setup.stock_size_mm
    stock = " × ".join(f"{value:g}" for value in dimensions) + " mm" if dimensions else "not declared"
    offset = ", ".join(f"{value:g}" for value in prepared.setup.work_offset_mm)
    cutters = sum(bool(tool.geometry_path) for tool in prepared.definitions.values())
    holders = sum(bool(tool.holder_geometry_path) for tool in prepared.definitions.values())
    return (
        f"Recorded machine: {machine}\n"
        f"Fixture plate: {component('fixture')} · Vise/workholding: {component('workholding')}\n"
        f"Stock: {stock} · Work offset: {offset} mm\n"
        f"Archived tools: {len(prepared.definitions)} · Cutter CAD references: {cutters} · Holder CAD references: {holders}\n"
        "Nominal local preview · setup alignment remains unmeasured"
    )
