"""Named probe configurations.

A mechanical touch probe and an inductive one have different effective tip
diameters and different trigger behaviour, and swapping between them with one
shared configuration silently corrupts every measurement taken afterwards.

Kivy-free by contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

PROFILES_FORMAT_VERSION = 1


class ProbeKind(Enum):
    MECHANICAL = "mechanical"
    INDUCTIVE = "inductive"
    OEM_WIRELESS = "oem_wireless"


@dataclass(frozen=True)
class ProbeProfile:
    name: str
    kind: ProbeKind = ProbeKind.MECHANICAL
    tip_diameter: float = 2.0
    normally_closed: bool = False
    shank_diameter: float | None = None
    tlo_correction: float = 0.0
    """Matches zprobe.three_axis_probe_tlo_correction for this probe."""

    note: str = ""

    @property
    def is_calibrated(self) -> bool:
        """False while the tip diameter is still the firmware default.

        M460 measures the effective diameter but does not persist it, so a
        profile left at 2.0 has almost certainly never been calibrated.
        """
        return abs(self.tip_diameter - 2.0) > 1e-6

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "tip_diameter": self.tip_diameter,
            "normally_closed": self.normally_closed,
            "shank_diameter": self.shank_diameter,
            "tlo_correction": self.tlo_correction,
            "note": self.note,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ProbeProfile:
        try:
            kind = ProbeKind(str(data.get("kind", "mechanical")))
        except ValueError:
            kind = ProbeKind.MECHANICAL
        return ProbeProfile(
            name=str(data["name"]),
            kind=kind,
            tip_diameter=float(data.get("tip_diameter", 2.0)),
            normally_closed=bool(data.get("normally_closed", False)),
            shank_diameter=(None if data.get("shank_diameter") is None else float(data["shank_diameter"])),
            tlo_correction=float(data.get("tlo_correction", 0.0)),
            note=str(data.get("note", "")),
        )

    def config_commands(self) -> list[str]:
        """Commands that make this profile the machine's active settings."""
        return [
            f"config-set sd zprobe.probe_tip_diameter {self.tip_diameter:.4f}",
            f"config-set sd zprobe.three_axis_probe_tlo_correction {self.tlo_correction:.4f}",
        ]


class ProbeProfiles:
    def __init__(self, profiles: list[ProbeProfile] | None = None, active: str = "") -> None:
        self._profiles: dict[str, ProbeProfile] = {p.name: p for p in (profiles or [])}
        self._active = active if active in self._profiles else ""

    def add(self, profile: ProbeProfile) -> None:
        self._profiles[profile.name] = profile
        if not self._active:
            self._active = profile.name

    def remove(self, name: str) -> None:
        self._profiles.pop(name, None)
        if self._active == name:
            self._active = next(iter(sorted(self._profiles)), "")

    def names(self) -> list[str]:
        return sorted(self._profiles)

    def get(self, name: str) -> ProbeProfile | None:
        return self._profiles.get(name)

    @property
    def active(self) -> ProbeProfile | None:
        return self._profiles.get(self._active)

    def activate(self, name: str) -> ProbeProfile | None:
        if name in self._profiles:
            self._active = name
        return self.active

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": PROFILES_FORMAT_VERSION,
                "active": self._active,
                "profiles": [self._profiles[n].to_dict() for n in self.names()],
            },
            indent=2,
        )

    @staticmethod
    def from_json(text: str) -> ProbeProfiles:
        if not text.strip():
            return ProbeProfiles()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return ProbeProfiles()
            entries = data.get("profiles", [])
            if not isinstance(entries, list):
                return ProbeProfiles()
            return ProbeProfiles([ProbeProfile.from_dict(p) for p in entries], active=str(data.get("active", "")))
        except (ValueError, KeyError, TypeError, AttributeError):
            return ProbeProfiles()
