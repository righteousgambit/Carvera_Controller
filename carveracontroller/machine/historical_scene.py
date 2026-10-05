"""Prepare a recorded nominal scene from retained bytes, without UI or CNC access."""

import hashlib
import math
import os
from dataclasses import dataclass, fields
from pathlib import Path

from carveracontroller.addons.machine_simulation.model import MachineSetup, build_scene, vector
from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_meshes
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.job_packages import MAX_TOTAL, load_package, resolve_setup_assets
from carveracontroller.machine.recording_setup import validate_setup_binding


@dataclass
class HistoricalScene:
    setup: MachineSetup
    profile: object
    components: dict
    offset: tuple
    rotation: float
    jaw: float
    definitions: dict
    meshes: dict
    fallback: tuple
    geometry: dict
    context: dict
    scale: float


def definitions_from_snapshot(records):
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError("Recorded tools must be a list of at most 1000 definitions")
    allowed = {field.name for field in fields(ToolDefinition)}
    result = {}
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
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1000
            ):
                raise ValueError("Invalid recorded tool dimensions")
        if definition.geometry_unit_scale != 1:
            raise ValueError("Recorded library tools must use millimetres")
        for key in ("diameter", "shank_diameter", "length", "flute_length", "shoulder_length", "thread_pitch"):
            if getattr(definition, key) is not None and getattr(definition, key) <= 0:
                raise ValueError("Recorded positive tool dimension is zero")
        result[number] = definition
    return result


def prepare_historical_scene(
    replay, archive, destination, cam_tools, cam_scale, scale, selected_program, inspection_hash
):
    context = replay.payload.get("context", {})
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
    geometry = profile.scene(setup, offset, rotation, jaw) if profile else build_scene(setup)
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
