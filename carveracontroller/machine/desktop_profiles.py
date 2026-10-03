"""Local, validated profile library. Profiles never issue controller commands."""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

MAX_BYTES = 2 * 1024 * 1024
KINDS = ("machines", "tools", "toolsets")


class ProfileError(ValueError):
    """Invalid or unreadable local profile data."""


def _text(value, field, required=False, limit=512):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ProfileError(f"{field} must be text of at most {limit} characters")
    value = value.strip()
    if required and not value:
        raise ProfileError(f"{field} is required")
    return value


def _integer(value, field, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ProfileError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _dimension(value, field, maximum=1000, allow_zero=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{field} must be a dimension in mm")
    if not math.isfinite(value) or value > maximum or (value < 0 if allow_zero else value <= 0):
        raise ProfileError(f"{field} must be {'non-negative' if allow_zero else 'positive'} and at most {maximum} mm")
    return float(value)


def validate_record(kind, record):
    if kind not in KINDS or not isinstance(record, dict):
        raise ProfileError("Unknown profile type or invalid record")
    result = {
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
    elif kind == "tools":
        shape = record.get("shape", "flat_end_mill")
        if shape not in {item.value for item in ToolType}:
            raise ProfileError("Unknown tool shape")
        result.update(number=_integer(record.get("number", 1), "Tool number", 1, 9999), shape=shape)
        for key in ("diameter", "shank_diameter", "length", "flute_length", "corner_radius", "thread_pitch"):
            result[key] = _dimension(record.get(key), key.replace("_", " ").title(), allow_zero=key == "corner_radius")
        if result["diameter"] is None or result["shank_diameter"] is None:
            raise ProfileError("Cutting and shank diameters are required")
        if result["length"] and result["flute_length"] and result["flute_length"] > result["length"]:
            raise ProfileError("Flute length cannot exceed overall tool length")
        if result["corner_radius"] and result["corner_radius"] > result["diameter"] / 2:
            raise ProfileError("Corner radius cannot exceed half the cutting diameter")
        result.update(
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


def validate_library(data):
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data.get("schema") != 1:
        raise ProfileError("Expected a profile library with schema 1")
    result = {"schema": 1}
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


def _read(path):
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ProfileError("Profile library exceeds 2 MiB")
        return validate_library(json.loads(raw))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Cannot read profile library: {exc}") from exc


def _write(path, data):
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


def initial_library():
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

    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/profiles.json").expanduser()
        self._lock = threading.RLock()
        self._data = _read(self.path) if self.path.exists() else initial_library()

    @property
    def data(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def _save_record(self, kind, record):
        record = dict(record)
        record.setdefault("id", str(uuid.uuid4()))
        item = validate_record(kind, record)
        with self._lock:
            next_data = self.data
            next_data[kind] = [r for r in next_data[kind] if r["id"] != item["id"]] + [item]
            self._commit(next_data)
        return copy.deepcopy(item)

    def _commit(self, data):
        validated = validate_library(data)
        _write(self.path, validated)
        self._data = validated

    def save_machine(self, record):
        return self._save_record("machines", record)

    def save_tool(self, record):
        return self._save_record("tools", record)

    def save_toolset(self, record):
        return self._save_record("toolsets", record)

    def delete(self, kind, identifier):
        if kind not in KINDS:
            raise ProfileError("Unknown profile type")
        with self._lock:
            data = self.data
            data[kind] = [r for r in data[kind] if r["id"] != identifier]
            # References prevent accidental deletion of a tool still assigned to a set.
            self._commit(data)

    def import_file(self, path):
        incoming = _read(Path(path).expanduser())
        with self._lock:
            merged = self.data
            for kind in KINDS:
                records = {r["id"]: r for r in merged[kind]}
                records.update({r["id"]: r for r in incoming[kind]})
                merged[kind] = list(records.values())
            self._commit(merged)
        return {kind: len(incoming[kind]) for kind in KINDS}

    def export_file(self, path):
        _write(path, self.data)
        return Path(path).expanduser()

    def toolset_definitions(self, toolset, units="mm"):
        validated = validate_record("toolsets", toolset)
        tools = {r["id"]: r for r in self.data["tools"]}
        try:
            return [
                to_tool_definition(tools[identifier], number=int(slot), units=units)
                for slot, identifier in sorted(validated["slots"].items())
            ]
        except KeyError as exc:
            raise ProfileError("Toolset references a missing tool") from exc


def to_tool_definition(profile, number=None, units="mm"):
    """Convert library mm to a viewer's G-code units; never measured TLO."""
    item = validate_record("tools", profile)
    if units not in ("mm", "in"):
        raise ProfileError("Tool definition units must be mm or in")
    scale = 1 if units == "mm" else 1 / 25.4
    dimensions = {
        key: None if item[key] is None else item[key] * scale
        for key in ("diameter", "shank_diameter", "length", "flute_length", "corner_radius", "thread_pitch")
    }
    return ToolDefinition(
        number=item["number"] if number is None else _integer(number, "Tool number", 1, 9999),
        tool_type=ToolType(item["shape"]),
        description=item["name"],
        vendor=item["vendor"],
        product_id=item["product_id"],
        type_name=item["shape"],
        **dimensions,
    )
