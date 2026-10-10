"""Closed wire plans for a supervised Community 2.1.0c gateway.

Compilation is not authorization. The supervisor binds the approved plan,
profile, setup, lease and fresh state before dispatching these exact commands.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .link import READ_ONLY_COMMANDS, remote_path
from .probing import compile_probe, probe_catalog

PROFILE_ID = "carvera-community-c1-2.1.0c-v2"
OPERATION_VERSION = "carvera.operations.v2"
AXES = frozenset(("X", "Y", "Z", "A", "B"))
OPERATIONS = {
    "observe.refresh": ("Refresh observations", "observation", "read"),
    "observe.query": ("Read controller state", "observation", "read"),
    "machine.home": ("Home the machine", "position", "motion"),
    "machine.jog": ("Jog one bounded step", "position", "motion"),
    "machine.move": ("Move to a reviewed position", "position", "motion"),
    "machine.hold": ("Request feed hold", "job", "hold"),
    "machine.abort": ("Request software abort", "job", "abort"),
    "machine.jog_cancel": ("Cancel jogging", "position", "hold"),
    "tool.clamp": ("Clamp the supported tool", "tooling", "tooling"),
    "tool.unclamp": ("Release the supported tool", "tooling", "tooling"),
    "tool.select": ("Assign the installed tool", "tooling", "setting"),
    "tool.change": ("Change the tool through the rack", "tooling", "motion"),
    "tool.measure": ("Measure tool length at the fixed setter", "tooling", "probing"),
    "tool.offset": ("Write the measured tool offset", "tooling", "setting"),
    "probe.operation": ("Run a reviewed probing sequence", "probing", "probing"),
    "probe.touch": ("Probe one bounded travel", "probing", "probing"),
    "wcs.select": ("Select a work coordinate system", "coordinates", "setting"),
    "wcs.set": ("Set a work coordinate system", "coordinates", "setting"),
    "accessory.light": ("Set the work light", "accessories", "accessory"),
    "accessory.air": ("Set air assist", "accessories", "accessory"),
    "accessory.vacuum": ("Set vacuum power", "accessories", "accessory"),
    "accessory.fan": ("Set spindle fan power", "accessories", "accessory"),
    "accessory.probe_charge": ("Set wireless probe charging", "accessories", "accessory"),
    "accessory.tool_sensor": ("Set tool sensor power", "accessories", "accessory"),
    "accessory.external": ("Set external output power", "accessories", "accessory"),
    "override.feed": ("Set feed override", "overrides", "setting"),
    "override.spindle": ("Set spindle override", "overrides", "setting"),
    "spindle.set": ("Set spindle state and speed", "spindle", "spindle"),
    "files.list": ("List controller job files", "files", "read"),
    "files.remove": ("Remove a controller job file", "files", "file_write"),
    "files.rename": ("Rename a controller job file", "files", "file_write"),
    "job.start": ("Start the exact verified job file", "job", "job_start"),
    "job.pause": ("Pause the controller job", "job", "hold"),
    "job.resume": ("Resume the exact retained job", "job", "job_resume"),
    "job.cancel": ("Cancel the controller job", "job", "abort"),
    "recovery.unlock": ("Clear the inspected controller alarm", "recovery", "recovery"),
    "leveling.clear": ("Clear auto-level compensation", "coordinates", "setting"),
    "expert.mdi": ("Execute one reviewed expert command", "expert", "expert"),
}


def catalog() -> dict:
    return {
        "schema_version": OPERATION_VERSION,
        "profile_id": PROFILE_ID,
        "operations": [
            {"id": key, "label": label, "group": group, "consequence": consequence}
            for key, (label, group, consequence) in OPERATIONS.items()
        ],
        "probe_variants": probe_catalog(),
        "unsupported": [
            {"id": "machine.jog_continuous", "reason": "Needs a gateway-owned deadman and expiry qualification"},
            {"id": "maintenance.firmware", "reason": "Needs a separate backed-up firmware migration workflow"},
            {"id": "maintenance.laser", "reason": "Laser actuation is not admitted by this milling profile"},
            {
                "id": "maintenance.factory",
                "reason": "Factory mechanism and rotary calibration require separate admission",
            },
            {
                "id": "connection.usb",
                "reason": "USB opening toggles DTR and can reset firmware; Wi-Fi is the admitted transport",
            },
        ],
    }


def number(value, low: float, high: float) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError("A finite number inside the operation's range is required")
    return f"{value:.6f}".rstrip("0").rstrip(".") if value else "0"


def integer(value, low: int, high: int) -> int:
    number(value, low, high)
    if value != int(value):
        raise ValueError("An integer is required")
    return int(value)


def boolean(value) -> bool:
    if type(value) is not bool:
        raise ValueError("An explicit boolean is required")
    return value


def keys(params: dict, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(params, dict) or not required.issubset(params) or set(params) - required - (optional or set()):
        raise ValueError("Operation parameters do not match the closed contract")


def coordinates(value: dict, *, low: float = -500, high: float = 500) -> str:
    if not isinstance(value, dict) or not value or set(value) - AXES:
        raise ValueError("Named X/Y/Z/A/B coordinates are required")
    return " ".join(f"{axis}{number(value[axis], low, high)}" for axis in sorted(value))


def compile_operation(operation: str, params: dict) -> dict:
    if operation not in OPERATIONS:
        raise ValueError("Unknown controller operation")
    consequence = OPERATIONS[operation][2]
    plan: dict[str, Any] = {
        "schema_version": OPERATION_VERSION,
        "profile_id": PROFILE_ID,
        "operation": operation,
        "consequence": consequence,
        "commands": [],
        "realtime": None,
        "read_only": consequence == "read",
        "motion_completed": False,
        "manual_instructions": [],
    }
    commands = []
    if operation in ("observe.refresh", "files.list"):
        keys(params, set())
        commands = ["diagnose", "$G", "$#"] if operation == "observe.refresh" else ["ls /sd/gcodes"]
    elif operation == "observe.query":
        keys(params, {"query"})
        if params["query"] not in READ_ONLY_COMMANDS:
            raise ValueError("Query is not admitted as read-only")
        commands = [params["query"]]
    elif operation in ("machine.hold", "machine.abort", "machine.jog_cancel"):
        keys(params, set())
        plan["realtime"] = {
            "machine.hold": "feed_hold",
            "machine.abort": "software_abort",
            "machine.jog_cancel": "jog_cancel",
        }[operation]
    elif operation in ("machine.home", "tool.clamp", "tool.unclamp", "recovery.unlock", "leveling.clear"):
        keys(params, set())
        commands = [
            {
                "machine.home": "$H",
                "tool.clamp": "M490.1",
                "tool.unclamp": "M490.2",
                "recovery.unlock": "M999",
                "leveling.clear": "M370",
            }[operation]
        ]
    elif operation in ("machine.jog", "probe.touch"):
        keys(params, {"axis", "distance", "feed"})
        if params["axis"] not in AXES or (operation == "probe.touch" and params["axis"] not in {"X", "Y", "Z"}):
            raise ValueError("Unsupported operation axis")
        distance = number(
            params["distance"], -25 if operation == "machine.jog" else -50, 25 if operation == "machine.jog" else 50
        )
        if float(distance) == 0:
            raise ValueError("Travel distance must be nonzero")
        feed = number(params["feed"], 1, 2000 if operation == "machine.jog" else 300)
        line = (
            f"$J {params['axis']}{distance} F{feed}"
            if operation == "machine.jog"
            else (f"G91 G38.2 {params['axis']}{distance} F{feed}")
        )
        commands = ["M120", "G21", line, "M400", "M121"]
    elif operation == "machine.move":
        keys(params, {"frame", "coordinates", "feed"})
        if params["frame"] not in ("machine", "work"):
            raise ValueError("An explicit machine or work frame is required")
        target = coordinates(params["coordinates"])
        feed = number(params["feed"], 1, 3000)
        commands = [
            "M120",
            "G21",
            "G90",
            f"{'G53 ' if params['frame'] == 'machine' else ''}G1 {target} F{feed}",
            "M400",
            "M121",
        ]
    elif operation in ("tool.select", "tool.change"):
        keys(params, {"tool"})
        tool = integer(params["tool"], -1, 999999)
        commands = [f"{'M493.2' if operation == 'tool.select' else 'M6'} T{tool}"]
    elif operation == "tool.measure":
        keys(params, {"repeats", "tool_kind"})
        if params["tool_kind"] not in ("probe", "cutter"):
            raise ValueError("Installed tool kind must be explicit and verified by the supervisor")
        commands = [f"M491 R{integer(params['repeats'], 1, 5)}"]
    elif operation == "tool.offset":
        keys(params, {"method", "value"})
        if params["method"] not in ("contact_machine_z", "height_above_work_zero"):
            raise ValueError("Tool offset method is unknown")
        value = number(params["value"], -150, 150)
        commands = [f"M493.3 {'Z' if params['method'] == 'contact_machine_z' else 'H'}{value}"]
    elif operation == "probe.operation":
        keys(params, {"variant", "values"})
        plan.update(compile_probe(params["variant"], params["values"]))
        commands = plan["commands"]
    elif operation in ("wcs.select", "wcs.set"):
        keys(
            params,
            {"wcs"} if operation == "wcs.select" else {"wcs", "method", "coordinates"},
            {"rotation_degrees"} if operation == "wcs.set" else None,
        )
        wcs = integer(params["wcs"], 1, 6)
        if operation == "wcs.select":
            commands = [f"G{53 + wcs}"]
        else:
            if params["method"] not in ("machine_origin", "current_position"):
                raise ValueError("Work-zero method must be explicit")
            target = coordinates(params["coordinates"])
            rotation = f" R{number(params['rotation_degrees'], -180, 180)}" if "rotation_degrees" in params else ""
            commands = [
                "M120",
                "G21",
                f"G10 L{2 if params['method'] == 'machine_origin' else 20} P{wcs} {target}{rotation}",
                "M121",
            ]
    elif operation in ("accessory.light", "accessory.air", "accessory.probe_charge", "accessory.tool_sensor"):
        keys(params, {"enabled"})
        enabled = boolean(params["enabled"])
        commands = [
            {
                "accessory.light": ("M822", "M821"),
                "accessory.air": ("M9", "M7"),
                "accessory.probe_charge": ("M842", "M841"),
                "accessory.tool_sensor": ("M832", "M831"),
            }[operation][enabled]
        ]
    elif operation in ("accessory.vacuum", "accessory.fan", "accessory.external"):
        keys(params, {"power_percent"})
        power = integer(params["power_percent"], 0, 100)
        on, off = {
            "accessory.vacuum": ("M801", "M802"),
            "accessory.fan": ("M811", "M812"),
            "accessory.external": ("M851", "M852"),
        }[operation]
        commands = [f"{on} S{power}" if power else off]
    elif operation in ("override.feed", "override.spindle"):
        keys(params, {"percent"})
        percent = integer(params["percent"], 10, 200)
        commands = [f"{'M220' if operation == 'override.feed' else 'M223'} S{percent}"]
    elif operation == "spindle.set":
        keys(params, {"enabled", "rpm"})
        rpm = integer(params["rpm"], 0, 24000)
        enabled = boolean(params["enabled"])
        if enabled and rpm < 1000:
            raise ValueError("Enabled spindle requires an explicit supported speed")
        commands = [f"M3 S{rpm}" if enabled else "M5"]
    elif operation in ("files.remove", "files.rename", "job.start"):
        keys(params, {"path", "destination"} if operation == "files.rename" else {"path"})
        path = remote_path(params["path"])
        commands = [
            f"{'rm' if operation == 'files.remove' else 'mv' if operation == 'files.rename' else 'play'} {path}"
            + (f" {remote_path(params['destination'])}" if operation == "files.rename" else "")
        ]
    elif operation in ("job.pause", "job.resume", "job.cancel"):
        keys(params, set())
        commands = [{"job.pause": "suspend", "job.resume": "resume", "job.cancel": "abort"}[operation]]
    elif operation == "expert.mdi":
        keys(params, {"command"})
        command = params["command"]
        if not isinstance(command, str) or not re.fullmatch(r"(?:G|M|T)[0-9][A-Z0-9 .+-]*", command):
            raise ValueError("Expert MDI is one numeric G/M/T line; shell, macros and comments are excluded")
        # Settings, laser and firmware actions need their own admission, not
        # a bypass through expert MDI. Multi-code lexical matching is explicit.
        tokens = re.findall(r"([GMT])([0-9]+(?:\.[0-9]+)?)", command)
        # Only the geometry/modal/readout subset is an expert escape hatch.
        # Accessory, tooling, probe and configuration codes stay named and
        # therefore carry their own prerequisites. Unknown firmware codes fail.
        admitted_g = {
            "0",
            "1",
            "2",
            "3",
            "4",
            "17",
            "18",
            "19",
            "20",
            "21",
            "53",
            "54",
            "55",
            "56",
            "57",
            "58",
            "59",
            "90",
            "91",
            "92",
            "92.1",
            "94",
        }
        admitted_m = {"5", "105", "114", "114.2", "115", "400"}
        for letter, code in tokens:
            if (
                (letter == "G" and code not in admitted_g)
                or (letter == "M" and code not in admitted_m)
                or letter == "T"
            ):
                raise ValueError("This MDI command requires its own named operation or maintenance admission")
        commands = [command]
    for line in commands:
        if not line or len(line.encode("ascii")) + (6 if line[0].islower() else 1) > 126:
            raise ValueError("Operation exceeds the firmware line budget")
    plan["commands"] = commands
    return plan
