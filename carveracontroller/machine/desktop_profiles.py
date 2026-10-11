"""Local, validated profile library. Profiles never issue controller commands."""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import threading
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import urlparse

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

MAX_BYTES = 2 * 1024 * 1024
ProfileKind = Literal["machines", "tools", "toolsets"]
# Records are heterogeneous JSON objects; validation is the sole entry boundary.
ProfileRecord = dict[str, Any]
KINDS: tuple[ProfileKind, ...] = ("machines", "tools", "toolsets")


class ProfileLibrary(TypedDict):
    schema: int
    machines: list[ProfileRecord]
    tools: list[ProfileRecord]
    toolsets: list[ProfileRecord]


class ProfileError(ValueError):
    """Invalid or unreadable local profile data."""


def _text(value: object, field: str, required: bool = False, limit: int = 512) -> str:
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ProfileError(f"{field} must be text of at most {limit} characters")
    value = value.strip()
    if required and not value:
        raise ProfileError(f"{field} is required")
    return value


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ProfileError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _dimension(value: object, field: str, maximum: float = 1000, allow_zero: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{field} must be a dimension in mm")
    if not math.isfinite(value) or value > maximum or (value < 0 if allow_zero else value <= 0):
        raise ProfileError(f"{field} must be {'non-negative' if allow_zero else 'positive'} and at most {maximum} mm")
    return float(value)


def validate_record(kind: str, record: object) -> ProfileRecord:
    if kind not in KINDS or not isinstance(record, dict):
        raise ProfileError("Unknown profile type or invalid record")
    result: ProfileRecord = {
        "id": _text(record.get("id", ""), "ID", True, 128),
        "name": _text(record.get("name", ""), "Name", True, 128),
    }
    if kind == "machines":
        model = record.get("model", "C1")
        if model not in ("C1", "CA1"):
            raise ProfileError("Machine model must be C1 or CA1")
        host = _text(record.get("host", ""), "Host", False, 253)
        if host and (any(c.isspace() for c in host) or any(c in host for c in "/?#@")):
            raise ProfileError("Host must be an address or hostname, without a URL path")
        camera = _text(record.get("camera_url", ""), "Camera URL", False, 2048)
        if camera:
            parsed = urlparse(camera)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ProfileError("Camera URL must be HTTP or HTTPS without embedded credentials")
        result.update(
            model=model,
            host=host,
            port=_integer(record.get("port", 2222), "Port", 1, 65535),
            camera_url=camera,
            cad_path=_text(record.get("cad_path", ""), "CAD path", False, 2048),
        )
        for key in ("vise_x", "vise_y", "vise_z", "vise_rotation", "vise_jaw_offset"):
            value = record.get(key, 0)
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1000:
                raise ProfileError("Workholding placement must be finite and within 1000 mm/degrees")
            result[key] = float(value)
    elif kind == "tools":
        shape = record.get("shape", "flat_end_mill")
        if shape not in {item.value for item in ToolType}:
            raise ProfileError("Unknown tool shape")
        result.update(number=_integer(record.get("number", 1), "Tool number", 1, 9999), shape=shape)
        for key in (
            "diameter",
            "shank_diameter",
            "length",
            "flute_length",
            "corner_radius",
            "thread_pitch",
            "stickout",
        ):
            result[key] = _dimension(record.get(key), key.replace("_", " ").title(), allow_zero=key == "corner_radius")
        # Optional conical geometry preserves legacy fingerprints when absent.
        if record.get("tip_diameter") is not None:
            result["tip_diameter"] = _dimension(record["tip_diameter"], "Tip diameter", allow_zero=True)
        if record.get("taper_angle_deg") is not None:
            angle = record["taper_angle_deg"]
            if (
                isinstance(angle, bool)
                or not isinstance(angle, (int, float))
                or not math.isfinite(angle)
                or not 0 < angle < 90
            ):
                raise ProfileError("Taper half angle must be greater than 0 and less than 90 degrees")
            result["taper_angle_deg"] = float(angle)
        # Omit absent metadata so legacy design fingerprints stay unchanged.
        if record.get("thread_teeth") is not None:
            result["thread_teeth"] = _integer(record["thread_teeth"], "Complete thread teeth", 2, 200)
        if record.get("thread_tip_offset") is not None:
            result["thread_tip_offset"] = _dimension(record["thread_tip_offset"], "Lowest tooth datum", allow_zero=True)
        if "thread_teeth" in result or "thread_tip_offset" in result:
            if (
                shape != "thread_mill"
                or result["thread_pitch"] is None
                or not {"thread_teeth", "thread_tip_offset"} <= result.keys()
            ):
                raise ProfileError(
                    "Multi-form geometry needs thread-mill shape, pitch, complete tooth count and tip-to-lowest-tooth datum"
                )
            span = result["thread_tip_offset"] + result["thread_teeth"] * result["thread_pitch"]
            if result["flute_length"] is None or span > result["flute_length"] + 1e-9:
                raise ProfileError("Complete tooth stack exceeds flute length")
        if result["diameter"] is None or result["shank_diameter"] is None:
            raise ProfileError("Cutting and shank diameters are required")
        if result.get("tip_diameter") is not None and result["tip_diameter"] > result["diameter"]:
            raise ProfileError("Tip diameter cannot exceed cutting diameter")
        if result["length"] and result["flute_length"] and result["flute_length"] > result["length"]:
            raise ProfileError("Flute length cannot exceed overall tool length")
        if result["corner_radius"] and result["corner_radius"] > result["diameter"] / 2:
            raise ProfileError("Corner radius cannot exceed half the cutting diameter")
        if result["stickout"] is not None and result["length"] is not None and result["stickout"] > result["length"]:
            raise ProfileError("Stickout cannot exceed overall cutter length")
        if (
            result["stickout"] is not None
            and result["flute_length"] is not None
            and result["stickout"] < result["flute_length"]
        ):
            raise ProfileError("Stickout cannot be shorter than flute length")
        source = _text(record.get("source_url", ""), "Tool source URL", False, 2048)
        if source:
            parsed = urlparse(source)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ProfileError("Tool source URL must be HTTP or HTTPS without embedded credentials")
        result.update(
            geometry_path=_text(record.get("geometry_path", ""), "Cutter geometry", False, 2048),
            holder_geometry_path=_text(record.get("holder_geometry_path", ""), "Holder geometry", False, 2048),
            drawing_path=_text(record.get("drawing_path", ""), "Tool drawing", False, 2048),
            source_url=source,
            vendor=_text(record.get("vendor", ""), "Vendor"),
            product_id=_text(record.get("product_id", ""), "Product ID"),
            notes=_text(record.get("notes", ""), "Notes", False, 2048),
        )
    else:
        slots = record.get("slots", {})
        if not isinstance(slots, dict) or len(slots) > 6:
            raise ProfileError("A toolset has six ATC slots")
        validated_slots = {}
        for slot, tool_id in slots.items():
            if str(slot) not in tuple(str(i) for i in range(1, 7)):
                raise ProfileError("ATC slots must be 1 through 6")
            validated_slots[str(slot)] = _text(tool_id, "Tool ID", True, 128)
        if len(set(validated_slots.values())) != len(validated_slots):
            raise ProfileError("A tool profile can occupy only one slot in a toolset")
        result["slots"] = validated_slots
    return result


def validate_library(data: object) -> ProfileLibrary:
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data.get("schema") != 1:
        raise ProfileError("Expected a profile library with schema 1")
    result: ProfileLibrary = {"schema": 1, "machines": [], "tools": [], "toolsets": []}
    for kind in KINDS:
        records = data.get(kind, [])
        if not isinstance(records, list) or len(records) > 1000:
            raise ProfileError(f"{kind} must be a list of at most 1000 profiles")
        result[kind] = [validate_record(kind, item) for item in records]
        ids = [item["id"] for item in result[kind]]
        if len(set(ids)) != len(ids):
            raise ProfileError(f"Duplicate IDs in {kind}")
    tool_ids = {item["id"] for item in result["tools"]}
    for toolset in result["toolsets"]:
        if not set(toolset["slots"].values()) <= tool_ids:
            raise ProfileError(f"Toolset {toolset['name']} references a missing tool")
    return result


def _read(path: str | os.PathLike[str]) -> ProfileLibrary:
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ProfileError("Profile library exceeds 2 MiB")
        return validate_library(json.loads(raw))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Cannot read profile library: {exc}") from exc


def _write(path: str | os.PathLike[str], data: object) -> None:
    path = Path(path).expanduser()
    payload = (json.dumps(validate_library(data), indent=2, allow_nan=False) + "\n").encode()
    if len(payload) > MAX_BYTES:
        raise ProfileError("Profile library exceeds 2 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initial_library() -> ProfileLibrary:
    """Only the three photographed tools; overall length is not measured stickout."""
    tools = []
    for identifier, name, shape, product in (
        ("inventory-square-quarter", "¼ inch square end mill", "flat_end_mill", "H45AL-M-30250"),
        ("inventory-titan-67423", "¼ inch corner-radius end mill", "bull_nose_end_mill", "TC67423"),
        ("inventory-titan-67481", "¼ inch ball-nose end mill", "ball_end_mill", "TC67481"),
    ):
        tools.append(
            {
                "id": identifier,
                "name": name,
                "shape": shape,
                "product_id": product,
                "number": len(tools) + 1,
                "diameter": 6.35,
                "shank_diameter": 6.35,
                "length": 76.2,
                "flute_length": 25.4 if not tools else 31.75,
                "corner_radius": 0.381 if product == "TC67423" else None,
                "vendor": "Titan" if product.startswith("TC") else "",
                "notes": "Photographed inventory. Dimensions from label; stickout and physical ATC slot are unverified.",
            }
        )
    return validate_library({"schema": 1, "machines": [], "tools": tools, "toolsets": []})


class ProfileStore:
    """Atomic local persistence, detached readbacks, and validated merge imports."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/profiles.json").expanduser()
        self._lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._data = _read(self.path) if self.path.exists() else initial_library()
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._state_lock:
            return self._generation

    @property
    def data(self) -> ProfileLibrary:
        with self._state_lock:
            return copy.deepcopy(self._data)

    def snapshot(self) -> tuple[int, ProfileLibrary]:
        with self._state_lock:
            return self._generation, copy.deepcopy(self._data)

    def reload(self) -> tuple[int, ProfileLibrary]:
        """Explicit read-only refresh; invalid external files preserve current data."""
        with self._lock:
            loaded = _read(self.path)
            if loaded != self._data:
                with self._state_lock:
                    self._data = loaded
                    self._generation += 1
            return self.snapshot()

    def _save_record(self, kind: ProfileKind, record: Mapping[str, object]) -> ProfileRecord:
        record = dict(record)
        record.setdefault("id", str(uuid.uuid4()))
        item = validate_record(kind, record)
        with self._lock:
            next_data = self.data
            next_data[kind] = [r for r in next_data[kind] if r["id"] != item["id"]] + [item]
            self._commit(next_data)
        return copy.deepcopy(item)

    def _commit(self, data: ProfileLibrary) -> None:
        validated = validate_library(data)
        _write(self.path, validated)
        with self._state_lock:
            self._data = validated
            self._generation += 1

    def save_machine(self, record: Mapping[str, object]) -> ProfileRecord:
        return self._save_record("machines", record)

    def save_tool(self, record: Mapping[str, object]) -> ProfileRecord:
        return self._save_record("tools", record)

    def update_tools(self, records: Iterable[Mapping[str, object]], expected_generation: int) -> list[ProfileRecord]:
        """Atomically replace reviewed existing cutters; reject stale local reviews."""
        with self._lock:
            if expected_generation != self._generation:
                raise ProfileError("Library changed after review. Review the paste again.")
            if self.path.exists() and _read(self.path) != self._data:
                raise ProfileError("Library file changed outside this editor. Reload the table before reviewing.")
            items = [validate_record("tools", record) for record in records]
            ids = [item["id"] for item in items]
            if not items or len(ids) != len(set(ids)):
                raise ProfileError("Select distinct existing cutters to update")
            data = self.data
            known = {item["id"] for item in data["tools"]}
            if not set(ids) <= known:
                raise ProfileError("Reviewed cutter is missing. Review the paste again.")
            updates = {item["id"]: item for item in items}
            data["tools"] = [updates.get(item["id"], item) for item in data["tools"]]
            self._commit(data)
            return copy.deepcopy(items)

    def save_toolset(self, record: Mapping[str, object]) -> ProfileRecord:
        return self._save_record("toolsets", record)

    def delete(self, kind: ProfileKind, identifier: str) -> None:
        if kind not in KINDS:
            raise ProfileError("Unknown profile type")
        with self._lock:
            data = self.data
            data[kind] = [r for r in data[kind] if r["id"] != identifier]
            # References prevent accidental deletion of a tool still assigned to a set.
            self._commit(data)

    def import_file(self, path: str | os.PathLike[str]) -> dict[ProfileKind, int]:
        incoming = _read(Path(path).expanduser())
        with self._lock:
            merged = self.data
            for kind in KINDS:
                records = {r["id"]: r for r in merged[kind]}
                records.update({r["id"]: r for r in incoming[kind]})
                merged[kind] = list(records.values())
            self._commit(merged)
        return {kind: len(incoming[kind]) for kind in KINDS}

    def export_file(self, path: str | os.PathLike[str]) -> Path:
        _write(path, self.data)
        return Path(path).expanduser()

    def toolset_definitions(self, toolset: object, units: str = "mm") -> list[ToolDefinition]:
        validated = validate_record("toolsets", toolset)
        tools = {r["id"]: r for r in self.data["tools"]}
        try:
            return [
                to_tool_definition(tools[identifier], number=int(slot), units=units)
                for slot, identifier in sorted(validated["slots"].items())
            ]
        except KeyError as exc:
            raise ProfileError("Toolset references a missing tool") from exc


def to_tool_definition(profile: object, number: int | None = None, units: str = "mm") -> ToolDefinition:
    """Convert library mm to a viewer's G-code units; never measured TLO."""
    item = validate_record("tools", profile)
    if units not in ("mm", "in"):
        raise ProfileError("Tool definition units must be mm or in")
    scale = 1 if units == "mm" else 1 / 25.4
    dimensions: dict[str, float | None] = {
        key: None if item[key] is None else item[key] * scale
        for key in ("diameter", "shank_diameter", "length", "flute_length", "corner_radius", "thread_pitch", "stickout")
    }
    return ToolDefinition(
        number=item["number"] if number is None else _integer(number, "Tool number", 1, 9999),
        tool_type=ToolType(item["shape"]),
        description=item["name"],
        vendor=item["vendor"],
        product_id=item["product_id"],
        type_name=item["shape"],
        geometry_path=item["geometry_path"],
        holder_geometry_path=item["holder_geometry_path"],
        drawing_path=item["drawing_path"],
        source_url=item["source_url"],
        geometry_unit_scale=scale,
        diameter=dimensions["diameter"],
        shank_diameter=dimensions["shank_diameter"],
        length=dimensions["length"],
        flute_length=dimensions["flute_length"],
        tip_diameter=None if item.get("tip_diameter") is None else item["tip_diameter"] * scale,
        taper_angle_deg=item.get("taper_angle_deg"),
        corner_radius=dimensions["corner_radius"],
        thread_pitch=dimensions["thread_pitch"],
        thread_teeth=item.get("thread_teeth"),
        thread_tip_offset=None if item.get("thread_tip_offset") is None else item["thread_tip_offset"] * scale,
        stickout=dimensions["stickout"],
    )
