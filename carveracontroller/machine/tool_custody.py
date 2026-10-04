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
    ids, assemblies, reports, links = set(), set(), set(), set()
    for event in data["events"]:
        if not isinstance(event, dict):
            raise CustodyError("Invalid custody event")
        identity = text(event.get("id"), "event ID")
        if identity in ids:
            raise CustodyError("Duplicate event ID")
        ids.add(identity)
        number(event.get("at"), "event time", positive=True)
        kind = event.get("kind")
        if kind == "assembly":
            text(event.get("name"), "assembly name")
            text(event.get("holder"), "holder", False)
            text(event.get("profile_id"), "cutter design ID", False)
            if event.get("stickout_mm") is not None:
                number(event["stickout_mm"], "stickout", positive=True)
            assemblies.add(identity)
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
        elif kind == "assignment":
            text(event.get("machine_id"), "local machine profile")
            if type(event.get("slot")) is not int or not 1 <= event["slot"] <= 9999:
                raise CustodyError("Invalid tool number")
            if event.get("assembly_id") not in assemblies:
                raise CustodyError("Unknown assembly")
        elif kind == "link":
            if event.get("assembly_id") not in assemblies or event.get("report_id") not in reports:
                raise CustodyError("Unknown assembly or calibration receipt")
            if event["report_id"] in links:
                raise CustodyError("Calibration receipt already linked; original attribution preserved")
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
    def events(self):
        return copy.deepcopy(self._data["events"])

    def append(self, kind, **fields):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CustodyError("Tool history is being written; retry after the writer finishes") from exc
        temporary = None
        try:
            os.close(fd)
            current = self._read()
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

    def create_assembly(self, name, holder="", stickout_mm=None, profile_id=""):
        return self.append("assembly", name=name, holder=holder, stickout_mm=stickout_mm, profile_id=profile_id)

    def assign(self, machine_id, slot, assembly_id):
        return self.append("assignment", machine_id=machine_id, slot=slot, assembly_id=assembly_id)

    def capture(self, tool_number, report, endpoint=""):
        return self.append("report", tool_number=tool_number, report=report.to_dict(), endpoint=endpoint)

    def link(self, report_id, assembly_id, note):
        return self.append("link", report_id=report_id, assembly_id=assembly_id, note=note)

    def locations(self):
        """Latest declared placement; moving one assembly supersedes its old location."""
        locations = {}
        for event in self.events:
            if event["kind"] == "assignment":
                locations = {
                    key: value for key, value in locations.items() if value["assembly_id"] != event["assembly_id"]
                }
                locations[(event["machine_id"], event["slot"])] = event
        return locations

    def assignment(self, machine_id, slot):
        return self.locations().get((machine_id, slot))

    def assembly_reports(self, assembly_id):
        events = self.events
        linked = {e["report_id"] for e in events if e["kind"] == "link" and e["assembly_id"] == assembly_id}
        return [e for e in events if e["kind"] == "report" and e["id"] in linked]
