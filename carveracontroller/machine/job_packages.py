"""Portable, inert job archives. Loading never configures or commands a machine.

Asset references are logical strings supplied in ``assets``. Export replaces them
throughout the setup with content-addressed ``asset://`` references. Unmapped
nonempty CAD/drawing/geometry paths and photographs fail rather than disappearing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from carveracontroller.machine.camera_calibration_file import DecodedCalibration

SCHEMA = 1
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_MEMBERS = 1024
MAX_MANIFEST = 4 * 1024 * 1024
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
SETUP_FIELDS = (
    "machine",
    "tools",
    "toolsets",
    "stock",
    "fixtures",
    "vise",
    "material_recipes",
    "inspection_plan",
    "photographs",
)


class JobPackageError(ValueError):
    """Invalid archive, unavailable asset, or unsafe installation request."""


@dataclass
class JobPackage:
    name: str
    program: bytes
    program_name: str = "program.nc"
    machine: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    toolsets: list[dict[str, Any]] = field(default_factory=list)
    stock: dict[str, Any] = field(default_factory=dict)
    fixtures: list[dict[str, Any]] = field(default_factory=list)
    vise: dict[str, Any] = field(default_factory=dict)
    material_recipes: list[dict[str, Any]] = field(default_factory=list)
    inspection_plan: dict[str, Any] = field(default_factory=dict)
    photographs: list[str] = field(default_factory=list)
    assets: dict[str, Path | bytes] = field(default_factory=dict)
    # Immutable camera declarations are captured on the UI thread; JPEG encoding
    # and validation occur only in the archive worker. Never part of manifest JSON.
    camera_calibration: DecodedCalibration | None = None


@dataclass(frozen=True)
class RestoreReport:
    missing_inventory: tuple[str, ...] = ()
    conflicting_inventory: tuple[str, ...] = ()
    missing_assets: tuple[str, ...] = ()
    notes: tuple[str, ...] = ("Preview data only; physical setup requires reconciliation.",)


@dataclass
class LoadedJob:
    package: JobPackage
    report: RestoreReport
    asset_paths: dict[str, Path] = field(default_factory=dict)
    asset_bytes: dict[str, bytes] = field(default_factory=dict)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_check(value: Any, depth: int = 0) -> None:
    if depth > 32:
        raise JobPackageError("Setup nesting exceeds 32 levels")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 16384:
            raise JobPackageError("Setup string too long")
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or abs(value) > 1e12:
            raise JobPackageError("Setup numbers must be finite and bounded")
        return
    if isinstance(value, list):
        for item in value:
            _json_check(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        for item in value.values():
            _json_check(item, depth + 1)
        return
    raise JobPackageError("Setup must contain JSON values")


def _transform(value: Any, refs: Mapping[str, str], key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: _transform(v, refs, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_transform(v, refs, key) for v in value]
    if isinstance(value, str):
        if value in refs:
            return refs[value]
        if value and (key.endswith("_path") or key == "photographs" or value.startswith("asset://")):
            raise JobPackageError(f"Missing asset: {value}")
    return value


def _setup(job: JobPackage) -> dict[str, Any]:
    result = {key: copy.deepcopy(getattr(job, key)) for key in SETUP_FIELDS}
    _json_check(result)
    expected = {
        "machine": dict,
        "tools": list,
        "toolsets": list,
        "stock": dict,
        "fixtures": list,
        "vise": dict,
        "material_recipes": list,
        "inspection_plan": dict,
        "photographs": list,
    }
    if any(not isinstance(result[k], kind) for k, kind in expected.items()):
        raise JobPackageError("Invalid setup field type")
    if any(
        not isinstance(v, dict) for key in ("tools", "toolsets", "fixtures", "material_recipes") for v in result[key]
    ):
        raise JobPackageError("Setup records must be objects")
    if any(not isinstance(v, str) for v in result["photographs"]):
        raise JobPackageError("Photographs must be asset references")
    return result


def save_package(job: JobPackage, path: str | Path) -> Path:
    """Atomically export a self-contained archive; missing assets raise explicitly."""
    if not isinstance(job.name, str) or not job.name.strip() or len(job.name) > 256:
        raise JobPackageError("Job name required (maximum 256 characters)")
    if not isinstance(job.program, bytes) or len(job.program) > MAX_MEMBER:
        raise JobPackageError("Program must be bytes within size limit")
    if (
        not isinstance(job.program_name, str)
        or not job.program_name
        or PurePosixPath(job.program_name).name != job.program_name
        or "\\" in job.program_name
    ):
        raise JobPackageError("Program name must be a filename")
    camera_calibration = job.camera_calibration
    if camera_calibration is not None:
        from carveracontroller.machine.camera_calibration_file import calibration_data, encode_calibration

        job = copy.copy(job)
        job.assets = dict(job.assets)
        job.inspection_plan = copy.deepcopy(job.inspection_plan)
        reference = "camera-calibration.cvcal"
        if reference in job.assets:
            raise JobPackageError("Camera calibration asset reference conflicts")
        job.assets[reference] = encode_calibration(calibration_data(*camera_calibration))
        job.inspection_plan.pop("camera_registration", None)
        job.inspection_plan["camera_calibration_path"] = reference
    payloads = {}
    suffixes = {}
    refs = {}
    for ref, source in job.assets.items():
        if not isinstance(ref, str) or not ref:
            raise JobPackageError("Asset reference must be nonempty text")
        if isinstance(source, bytes):
            data, suffix = source, Path(ref).suffix.lower()
        else:
            source = Path(source)
            if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_MEMBER:
                raise JobPackageError(f"Missing, linked, or oversized asset: {ref}")
            with source.open("rb") as stream:
                data = stream.read(MAX_MEMBER + 1)
            suffix = source.suffix.lower()
        if len(data) > MAX_MEMBER:
            raise JobPackageError(f"Oversized asset: {ref}")
        digest = _hash(data)
        payloads[digest] = data
        suffixes[digest] = suffix if re.fullmatch(r"\.[a-z0-9]{1,15}", suffix) else ""
        refs[ref] = f"asset://{digest}"
    setup = _transform(_setup(job), refs)
    manifest = {
        "schema": SCHEMA,
        "name": job.name,
        "program_name": job.program_name,
        "program_sha256": _hash(job.program),
        "setup": setup,
        "assets": {digest: {"size": len(data), "suffix": suffixes[digest]} for digest, data in payloads.items()},
    }
    encoded = json.dumps(manifest, allow_nan=False, sort_keys=True).encode()
    if (
        len(encoded) > MAX_MANIFEST
        or len(payloads) + 2 > MAX_MEMBERS
        or sum(map(len, payloads.values())) + len(encoded) + len(job.program) > MAX_TOTAL
    ):
        raise JobPackageError("Job exceeds archive limits")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".job-export-", dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("manifest.json", encoded)
            archive.writestr("program.bin", job.program)
            for digest, data in payloads.items():
                archive.writestr(f"assets/{digest}", data)
        with open(temporary, "rb") as completed:
            os.fsync(completed.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JobPackageError("Duplicate manifest key")
        result[key] = value
    return result


def load_package(
    path: str | Path | IO[bytes],
    destination: str | Path | None = None,
    inventory: Mapping[str, Mapping[str, Any]] | None = None,
) -> LoadedJob:
    """Validate completely, then optionally install into a NEW directory atomically.

    ``inventory`` maps physical tool IDs to locally recorded tool definitions.
    It is read-only; absent IDs and mismatched definitions are reported.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > MAX_MEMBERS or len(set(names)) != len(names):
                raise JobPackageError("Too many or duplicate archive members")
            total = 0
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if name.is_absolute() or ".." in name.parts or "\\" in entry.filename or str(name) != entry.filename:
                    raise JobPackageError("Unsafe archive path")
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode)) or entry.flag_bits & 1:
                    raise JobPackageError("Linked, special, or encrypted member")
                total += entry.file_size
                if (
                    entry.file_size > MAX_MEMBER
                    or total > MAX_TOTAL
                    or entry.file_size > max(1024 * 1024, entry.compress_size * 200)
                ):
                    raise JobPackageError("Archive exceeds extraction limits")
            if "manifest.json" not in names or "program.bin" not in names:
                raise JobPackageError("Missing manifest or program")
            if archive.getinfo("manifest.json").file_size > MAX_MANIFEST:
                raise JobPackageError("Manifest too large")
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=_pairs)
            _json_check(manifest)
            if (
                not isinstance(manifest, dict)
                or type(manifest.get("schema")) is not int
                or manifest["schema"] != SCHEMA
            ):
                raise JobPackageError("Unsupported package schema")
            assets = manifest.get("assets")
            if not isinstance(assets, dict) or any(not _DIGEST.fullmatch(d) for d in assets):
                raise JobPackageError("Invalid asset manifest")
            if set(names) != {"manifest.json", "program.bin", *(f"assets/{d}" for d in assets)}:
                raise JobPackageError("Missing or undeclared archive member")
            payloads = {}
            for digest, metadata in assets.items():
                data = archive.read(f"assets/{digest}")
                if (
                    not isinstance(metadata, dict)
                    or type(metadata.get("size")) is not int
                    or metadata["size"] != len(data)
                    or _hash(data) != digest
                ):
                    raise JobPackageError("Asset size or digest mismatch")
                suffix = metadata.get("suffix", "")
                if not isinstance(suffix, str) or (suffix and not re.fullmatch(r"\.[a-z0-9]{1,15}", suffix)):
                    raise JobPackageError("Invalid asset suffix")
                payloads[f"asset://{digest}"] = data
            program = archive.read("program.bin")
            if _hash(program) != manifest.get("program_sha256"):
                raise JobPackageError("Program digest mismatch")
            setup = manifest.get("setup")
            if not isinstance(setup, dict) or set(setup) != set(SETUP_FIELDS):
                raise JobPackageError("Incomplete setup schema")
            job_name, program_name = manifest.get("name"), manifest.get("program_name")
            if not isinstance(job_name, str) or not job_name.strip() or len(job_name) > 256:
                raise JobPackageError("Invalid job name")
            if (
                not isinstance(program_name, str)
                or not program_name
                or PurePosixPath(program_name).name != program_name
                or "\\" in program_name
            ):
                raise JobPackageError("Invalid program filename")
            job = JobPackage(name=job_name, program=program, program_name=program_name, **setup)
            _setup(job)
            # Identity transform validates every referenced asset without changing refs.
            _transform(setup, {ref: ref for ref in payloads})
    except (
        OSError,
        zipfile.BadZipFile,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        OverflowError,
    ) as exc:
        raise JobPackageError(f"Unreadable job archive: {exc}") from exc
    missing, conflicts = [], []
    if inventory is not None:
        for tool in job.tools:
            tool_id = tool.get("id")
            if not isinstance(tool_id, str) or not tool_id:
                raise JobPackageError("Inventory reconciliation requires tool IDs")
            if tool_id not in inventory:
                missing.append(tool_id)
            elif inventory[tool_id] != tool:
                conflicts.append(tool_id)
    try:
        retained_camera_calibration(LoadedJob(job, RestoreReport(), asset_bytes=payloads))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise JobPackageError("Invalid retained camera calibration: " + str(exc)) from exc
    paths = {}
    if destination is not None:
        target = Path(destination)
        if target.exists() or target.is_symlink():
            raise JobPackageError("Installation destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".job-install-", dir=target.parent))
        try:
            (temporary / "assets").mkdir()
            for ref, data in payloads.items():
                digest = ref.removeprefix("asset://")
                (temporary / "assets" / (digest + assets[digest].get("suffix", ""))).write_bytes(data)
            (temporary / "program.bin").write_bytes(program)
            (temporary / "manifest.json").write_text(json.dumps(manifest, allow_nan=False, sort_keys=True))
            # rename cannot replace a populated directory; do not overwrite existing data.
            if target.exists() or target.is_symlink():
                raise JobPackageError("Installation destination appeared during restore")
            temporary.rename(target)
            paths = {
                ref: target
                / "assets"
                / (ref.removeprefix("asset://") + assets[ref.removeprefix("asset://")].get("suffix", ""))
                for ref in payloads
            }
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    job.assets = dict(paths)
    return LoadedJob(job, RestoreReport(tuple(missing), tuple(conflicts)), paths, payloads)


def resolve_setup_assets(loaded: LoadedJob) -> dict[str, Any]:
    """Return an independent setup with installed local asset paths.

    Keep portable references in the saved package. Use this resolved copy only
    when preparing application preview objects. Requires ``destination`` during
    load if any embedded assets exist; it never applies controller settings.
    """
    refs = {ref: str(path) for ref, path in loaded.asset_paths.items()}
    # _setup validates the string-keyed object; transformation changes only
    # declared string references, preserving its mapping structure.
    return cast(dict[str, Any], _transform(_setup(loaded.package), refs))


def retained_camera_calibration(loaded: LoadedJob) -> DecodedCalibration | None:
    """Validate camera evidence from hash-checked retained bytes, never a live image."""
    inspection = loaded.package.inspection_plan
    reference = inspection.get("camera_calibration_path")
    legacy = inspection.get("camera_registration")
    if reference is not None and not isinstance(reference, str):
        raise JobPackageError("Retained camera calibration reference must be text")
    if legacy is not None and not isinstance(legacy, dict):
        raise JobPackageError("Retained camera registration must be an object")
    if not reference and not legacy:
        return None
    from carveracontroller.machine.camera_calibration_file import MAX_CALIBRATION_BYTES, decode_calibration

    if reference:
        raw = loaded.asset_bytes.get(reference)
        if raw is None or len(raw) > MAX_CALIBRATION_BYTES:
            raise JobPackageError("Retained camera calibration asset unavailable or oversized")
        return decode_calibration(json.loads(raw))
    return decode_calibration({**legacy, "schema": 1}) if legacy else None
