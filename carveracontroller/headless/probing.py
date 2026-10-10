"""Typed headless access to the same pure probe generators used by the GUI.

Generated human instructions are returned separately, never sent to firmware.
All values must be finite numbers; whitespace, shell and G-code injection are
excluded before the existing generator sees its string-valued configuration.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..addons.probing.operations.Angle.AngleOperationType import AngleOperationType
from ..addons.probing.operations.Angle.AngleParameterDefinitions import AngleParameterDefinitions
from ..addons.probing.operations.Bore.BoreOperationType import BoreOperationType
from ..addons.probing.operations.Bore.BoreParameterDefinitions import BoreParameterDefinitions
from ..addons.probing.operations.Boss.BossOperationType import BossOperationType
from ..addons.probing.operations.Boss.BossParameterDefinitions import BossParameterDefinitions
from ..addons.probing.operations.Calibration.CalibrationOperationType import CalibrationOperationType
from ..addons.probing.operations.Calibration.CalibrationParameterDefinitions import CalibrationParameterDefinitions
from ..addons.probing.operations.FourthAxis.FourthAxisOperationType import FourthAxisOperationType
from ..addons.probing.operations.FourthAxis.FourthAxisParameterDefinitions import FourthAxisParameterDefinitions
from ..addons.probing.operations.InsideCorner.InsideCornerOperationType import InsideCornerOperationType
from ..addons.probing.operations.InsideCorner.InsideCornerParameterDefinitions import InsideCornerParameterDefinitions
from ..addons.probing.operations.OperationsBase import ProbeSettingDefinition
from ..addons.probing.operations.OutsideCorner.OutsideCornerOperationType import OutsideCornerOperationType
from ..addons.probing.operations.OutsideCorner.OutsideCornerParameterDefinitions import (
    OutsideCornerParameterDefinitions,
)
from ..addons.probing.operations.ProbeTip.ProbeTipOperationType import ProbeTipOperationType
from ..addons.probing.operations.ProbeTip.ProbeTipParameterDefinitions import ProbeTipParameterDefinitions
from ..addons.probing.operations.SingleAxis.SingleAxisProbeOperationType import SingleAxisProbeOperationType
from ..addons.probing.operations.SingleAxis.SingleAxisProbeParameterDefinitions import (
    SingleAxisProbeParameterDefinitions,
)

GROUPS = {
    "single_axis": (SingleAxisProbeOperationType, SingleAxisProbeParameterDefinitions),
    "bore": (BoreOperationType, BoreParameterDefinitions),
    "boss": (BossOperationType, BossParameterDefinitions),
    "inside_corner": (InsideCornerOperationType, InsideCornerParameterDefinitions),
    "outside_corner": (OutsideCornerOperationType, OutsideCornerParameterDefinitions),
    "angle": (AngleOperationType, AngleParameterDefinitions),
    "probe_ball": (ProbeTipOperationType, ProbeTipParameterDefinitions),
    "machine_calibration": (CalibrationOperationType, CalibrationParameterDefinitions),
    "fourth_axis": (FourthAxisOperationType, FourthAxisParameterDefinitions),
}
PROBE_COMMAND = re.compile(r"M(?:46[0-6](?:\.[1-3])?|469\.[1-6])(?: [A-Z][-+]?\d+(?:\.\d+)?)*\Z")


def _definitions(group: str) -> dict[str, ProbeSettingDefinition]:
    definitions = {
        value.code: value for value in vars(GROUPS[group][1]).values() if isinstance(value, ProbeSettingDefinition)
    }
    # These are accepted by 2.1.0c parse_parameters, although the old GUI did
    # not expose them for every group. Polarity must never inherit a setting.
    definitions.setdefault("I", ProbeSettingDefinition("I", "Normally closed (0 = NO, 1 = NC)"))
    definitions.setdefault("D", ProbeSettingDefinition("D", "Effective ball diameter (mm)"))
    if group == "machine_calibration":
        definitions.setdefault("Z", ProbeSettingDefinition("Z", "Z probing distance (mm)"))
        definitions.setdefault("F", ProbeSettingDefinition("F", "Probing feed (mm/min)"))
    return definitions


def _bounds(code: str) -> tuple[float, float]:
    if code in ("F", "K"):
        return 1, 2000 if code == "K" else 300
    if code == "D":
        return 0.1, 20
    if code == "Q":
        return -180, 180
    if code == "L":
        return 1, 5
    if code in ("I", "S"):
        return 0, 2 if code == "S" else 1
    if code in ("X", "Y", "Z", "H", "E", "C", "R", "J"):
        return 0.01, 200
    return -200, 200


def probe_catalog() -> list[dict]:
    variants = []
    for group, (operations, _) in GROUPS.items():
        for member in operations:
            variants.append(
                {
                    "id": f"{group}.{member.name}",
                    "label": member.value.title,
                    "group": group,
                    "parameters": [
                        {
                            "code": code,
                            "label": definition.label,
                            "required": definition.is_required,
                            "minimum": _bounds(code)[0],
                            "maximum": _bounds(code)[1],
                        }
                        for code, definition in _definitions(group).items()
                    ],
                    "changes_calibration": group in ("probe_ball", "machine_calibration"),
                    "requires_reference_measurement": group == "probe_ball",
                }
            )
    return variants


def compile_probe(variant: str, values: dict) -> dict:
    if not isinstance(variant, str) or variant.count(".") != 1 or not isinstance(values, dict):
        raise ValueError("An exact probing variant and numeric parameter object are required")
    group, member = variant.split(".")
    if group not in GROUPS or member not in GROUPS[group][0].__members__:
        raise ValueError("Unknown probing variant")
    definitions = _definitions(group)
    if set(values) - set(definitions):
        raise ValueError("Unknown probing parameter")
    config = {}
    for code, value in values.items():
        low, high = _bounds(code)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Probe parameters must be finite numbers")
        if not low <= value <= high or (code in ("I", "L", "S") and value != int(value)):
            raise ValueError("Probe parameter is outside its supported range")
        config[code] = f"{value:.6f}".rstrip("0").rstrip(".") if value else "0"
    # Diameter, polarity and whether to save zero are explicit. Do not inherit
    # hidden GUI settings, especially the GUI's default S2 (save/rotate WCS).
    if not {"D", "I", "S"}.issubset(config):
        raise ValueError("Probe diameter, polarity and zero-write choice must be explicit")
    # Legacy generator annotations say float although the GUI actually passes
    # numeric strings. Keep that existing interface behind this typed validator.
    operation: Any = GROUPS[group][0][member].value
    missing = operation.get_missing_config(config)
    if missing is not None:
        raise ValueError(f"Required probe parameter {missing.code} is missing")
    generated = operation.generate(config).splitlines()
    command = " ".join(generated[0].split())
    if not PROBE_COMMAND.fullmatch(command) or len(command.encode("ascii")) > 120:
        raise ValueError("Probe generator produced an unsupported wire plan")
    if not any(code in config for code in ("X", "Y", "Z")) and group not in (
        "machine_calibration",
        "fourth_axis",
        "probe_ball",
    ):
        raise ValueError("A bounded probe travel distance is required")
    return {
        "commands": ["M120", "G21", command, "M400", "M121"],
        "manual_instructions": [line.strip() for line in generated[1:] if line.strip()],
        "changes_calibration": group in ("probe_ball", "machine_calibration"),
        "requires_reference_measurement": group == "probe_ball",
        "writes_work_zero": values["S"] != 0,
        "probe_accuracy_verified": False,
    }
