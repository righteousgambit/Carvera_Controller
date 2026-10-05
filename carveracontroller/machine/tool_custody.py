"""Raw calibration receipts and operator-declared physical assembly custody.

Assignments and report links are assertions, never physical readback. Reports
remain unassigned until explicitly linked. Invalid existing files are preserved.
"""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import time
import uuid
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024
_UNREVIEWED = object()


class CustodyError(ValueError):
    pass


def text(value, field, required=True):
    if not isinstance(value, str) or len(value) > 512 or any(ord(c) < 32 for c in value):
        raise CustodyError(f"Invalid {field}")
    if required and not value.strip():
        raise CustodyError(f"{field} is required")
    return value


def number(value, field, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise CustodyError(f"Invalid {field}")
    return value


def validate(data):
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("events"), list):
        raise CustodyError("Unsupported or corrupt tool custody file; original preserved")
    ids, assemblies, reports, links = set(), {}, set(), set()
    revisions, locations = {}, {}
    for event in data["events"]:
        if not isinstance(event, dict):
            raise CustodyError("Invalid custody event")
        identity = text(event.get("id"), "event ID")
        if identity in ids:
            raise CustodyError("Duplicate event ID")
        ids.add(identity)
        number(event.get("at"), "event time", positive=True)
        kind = event.get("kind")
        if kind in ("assembly", "revision"):
            text(event.get("name"), "assembly name")
            text(event.get("holder"), "holder", False)
            text(event.get("profile_id"), "cutter design ID", False)
            text(event.get("holder_geometry_path", ""), "holder geometry path", False)
            if event.get("stickout_mm") is not None:
                number(event["stickout_mm"], "stickout", positive=True)
            if kind == "assembly":
                assemblies[identity] = identity
                revisions[identity] = identity
            else:
                assembly_id = event.get("assembly_id")
                if assembly_id not in assemblies:
                    raise CustodyError("Unknown assembly")
                if event.get("previous_revision_id") != assemblies[assembly_id]:
                    raise CustodyError("Assembly changed since review; reopen the editor")
                text(event.get("note"), "revision note")
                assemblies[assembly_id] = identity
                revisions[identity] = assembly_id
        elif kind == "report":
            tool = event.get("tool_number")
            if tool is not None and (type(tool) is not int or not 1 <= tool <= 9999):
                raise CustodyError("Invalid reported tool number")
            text(event.get("endpoint"), "connection source", False)
            report = event.get("report")
            if (
                not isinstance(report, dict)
                or not isinstance(report.get("measurements"), list)
                or not report["measurements"]
            ):
                raise CustodyError("Missing raw calibration samples")
            for value in report["measurements"]:
                number(value, "sample")
            number(report.get("timestamp"), "report timestamp")
            if number(report.get("max_delta"), "reported spread") < 0:
                raise CustodyError("Negative reported spread")
            if report.get("applied") is not None:
                number(report["applied"], "applied TLO")
            reports.add(identity)
        elif kind in ("assignment", "release"):
            text(event.get("machine_id"), "local machine profile")
            if type(event.get("slot")) is not int or not 1 <= event["slot"] <= 9999:
                raise CustodyError("Invalid tool number")
            if event.get("assembly_id") not in assemblies:
                raise CustodyError("Unknown assembly")
            assembly_id = event["assembly_id"]
            key = (event["machine_id"], event["slot"])
            if kind == "release":
                previous = locations.get(key)
                if (
                    not previous
                    or previous["id"] != event.get("expected_assignment_id")
                    or previous["assembly_id"] != assembly_id
                ):
                    raise CustodyError("Declared location changed since review; reopen removal")
                text(event.get("note"), "removal note")
                del locations[key]
            else:
                if "expected_assignment_id" in event:
                    previous = locations.get(key)
                    if event["expected_assignment_id"] != (previous["id"] if previous else None):
                        raise CustodyError("Declared location changed since review; reopen declaration")
                if "revision_id" in event and event["revision_id"] != assemblies[assembly_id]:
                    raise CustodyError("Assembly changed since review; reopen declaration")
                locations = {k: v for k, v in locations.items() if v["assembly_id"] != assembly_id}
                locations[key] = event
        elif kind in {"facing_recipe", "hole_recipe"}:
            assembly_id = event.get("assembly_id")
            if assembly_id not in assemblies or event.get("revision_id") != assemblies[assembly_id]:
                raise CustodyError("Assembly changed since recipe review; reopen review")
            text(event.get("note"), "recipe attribution note")
            recipe = event.get("recipe")
            if not isinstance(recipe, dict):
                raise CustodyError("Invalid recipe reference")
            for key in ("sha256", "design_fingerprint"):
                value = recipe.get(key)
                if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                    raise CustodyError("Invalid recipe content identity")
            for key in ("path", "tool_id", "wcs"):
                text(recipe.get(key), "recipe " + key)
            for key in ("feed_mm_min", "spindle_rpm"):
                number(recipe.get(key), "recipe " + key, positive=True)
            if kind == "facing_recipe":
                text(recipe.get("material"), "recipe material")
                for key in ("pass_depth_mm", "stepover_mm"):
                    number(recipe.get(key), "recipe " + key, positive=True)
            else:
                from carveracontroller.machine.tool_process import HOLE_STAGE_SHAPES

                if recipe.get("stage") not in HOLE_STAGE_SHAPES:
                    raise CustodyError("Invalid hole recipe stage")
                text(recipe.get("thread"), "recipe thread")
                if type(recipe.get("hole_count")) is not int or not 1 <= recipe["hole_count"] <= 1000:
                    raise CustodyError("Invalid recipe hole count")
                number(recipe.get("tip_angle_deg"), "recipe tip angle", positive=True)
        elif kind == "link":
            if event.get("assembly_id") not in assemblies or event.get("report_id") not in reports:
                raise CustodyError("Unknown assembly or calibration receipt")
            if event["report_id"] in links:
                raise CustodyError("Calibration receipt already linked; original attribution preserved")
            if "revision_id" in event and revisions.get(event["revision_id"]) != event["assembly_id"]:
                raise CustodyError("Unknown assembly revision")
            text(event.get("note"), "attribution note")
            links.add(event["report_id"])
        else:
            raise CustodyError("Unknown custody event")
    return copy.deepcopy(data)


class ToolCustodyStore:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/tool-custody.json").expanduser()
        self.error = None
        try:
            self._data = self._read()
        except (OSError, ValueError) as exc:
            self._data = {"schema": 1, "events": []}
            self.error = str(exc)

    def _read(self):
        if not self.path.exists():
            return {"schema": 1, "events": []}
        if self.path.stat().st_size > MAX_BYTES:
            raise CustodyError("Tool custody file exceeds size limit; original preserved")
        return validate(json.loads(self.path.read_text()))

    @property
    def generation(self):
        """Cheap change token for the desktop; events are append-only in this instance."""
        return len(self._data["events"])

    @property
    def events(self):
        return copy.deepcopy(self._data["events"])

    def append(self, kind, **fields):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CustodyError("Tool history writer lock exists; another or interrupted writer may own it") from exc
        temporary = None
        try:
            os.close(fd)
            current = self._read()
            # A rejected stale transaction must still expose the fresh definition
            # on reopen. Reading it does not save or replace any event.
            self._data = current
            event = dict(fields, id=str(uuid.uuid4()), at=time.time(), kind=kind)
            next_data = validate({"schema": 1, "events": current["events"] + [event]})
            payload = json.dumps(next_data, indent=2, allow_nan=False) + "\n"
            if len(payload.encode()) > MAX_BYTES:
                raise CustodyError("Tool custody size limit reached; receipt not saved")
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".tool-custody-")
            with os.fdopen(fd, "w") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            self._data, self.error = next_data, None
            return copy.deepcopy(event)
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            lock.unlink(missing_ok=True)

    def create_assembly(self, name, holder="", stickout_mm=None, profile_id="", holder_geometry_path=""):
        return self.append(
            "assembly",
            name=name,
            holder=holder,
            stickout_mm=stickout_mm,
            profile_id=profile_id,
            holder_geometry_path=holder_geometry_path,
        )

    def revisions(self, assembly_id):
        return [
            e
            for e in self.events
            if (e["kind"] == "assembly" and e["id"] == assembly_id)
            or (e["kind"] == "revision" and e["assembly_id"] == assembly_id)
        ]

    def assembly(self, assembly_id):
        records = self.revisions(assembly_id)
        if not records:
            return None
        latest = records[-1]
        latest.update(id=assembly_id, revision_id=records[-1]["id"], revision_count=len(records))
        return latest

    def assemblies(self):
        return [self.assembly(e["id"]) for e in self._data["events"] if e["kind"] == "assembly"]

    def revise(
        self,
        assembly_id,
        expected_revision_id,
        name,
        holder="",
        stickout_mm=None,
        profile_id="",
        note="",
        holder_geometry_path="",
    ):
        return self.append(
            "revision",
            assembly_id=assembly_id,
            previous_revision_id=expected_revision_id,
            holder_geometry_path=holder_geometry_path,
            name=name,
            holder=holder,
            stickout_mm=stickout_mm,
            profile_id=profile_id,
            note=note,
        )

    def assign(self, machine_id, slot, assembly_id, revision_id=None, *, expected_assignment_id=_UNREVIEWED):
        assembly = self.assembly(assembly_id)
        review = {} if expected_assignment_id is _UNREVIEWED else {"expected_assignment_id": expected_assignment_id}
        return self.append(
            "assignment",
            machine_id=machine_id,
            slot=slot,
            assembly_id=assembly_id,
            revision_id=revision_id or (assembly["revision_id"] if assembly else ""),
            **review,
        )

    def release(self, machine_id, slot, assembly_id, expected_assignment_id, note):
        return self.append(
            "release",
            machine_id=machine_id,
            slot=slot,
            assembly_id=assembly_id,
            expected_assignment_id=expected_assignment_id,
            note=note,
        )

    def capture(self, tool_number, report, endpoint=""):
        return self.append("report", tool_number=tool_number, report=report.to_dict(), endpoint=endpoint)

    def link(self, report_id, assembly_id, note, revision_id=None):
        assembly = self.assembly(assembly_id)
        return self.append(
            "link",
            report_id=report_id,
            assembly_id=assembly_id,
            note=note,
            revision_id=revision_id or (assembly["revision_id"] if assembly else ""),
        )

    def locations(self):
        """Latest declared placement; moving one assembly supersedes its old location."""
        locations = {}
        for event in self.events:
            if event["kind"] == "assignment":
                locations = {
                    key: value for key, value in locations.items() if value["assembly_id"] != event["assembly_id"]
                }
                locations[(event["machine_id"], event["slot"])] = event
            elif event["kind"] == "release":
                locations.pop((event["machine_id"], event["slot"]), None)
        return locations

    def assignment(self, machine_id, slot):
        return self.locations().get((machine_id, slot))

    def assembly_reports(self, assembly_id):
        events = self.events
        linked = {e["report_id"] for e in events if e["kind"] == "link" and e["assembly_id"] == assembly_id}
        return [e for e in events if e["kind"] == "report" and e["id"] in linked]

    def link_facing_recipe(self, assembly_id, revision_id, recipe, note):
        return self.append("facing_recipe", assembly_id=assembly_id, revision_id=revision_id, recipe=recipe, note=note)

    def link_hole_recipe(self, assembly_id, revision_id, recipe, note):
        return self.append("hole_recipe", assembly_id=assembly_id, revision_id=revision_id, recipe=recipe, note=note)
