"""Operator-facing capability explanations from current-session observations.

This inspector does not authorize commands or claim physical qualification.
Firmware identity implies published protocol support, not installed accessories.
"""

import math
from dataclasses import dataclass

from .capabilities import FirmwareIdentity, Support, carvera_capabilities


@dataclass(frozen=True)
class CapabilityDescription:
    key: str
    title: str
    section: str
    prerequisite: str
    alternative: str
    simulation: bool = False


DESCRIPTIONS = (
    CapabilityDescription(
        "status", "Live machine position", "Overview", "Current status response", "Use local program preview"
    ),
    CapabilityDescription(
        "spindle",
        "Spindle commands",
        "Spindle",
        "Recognized firmware and spindle setup",
        "Inspect spindle settings without running",
    ),
    CapabilityDescription(
        "probe",
        "Probing workflows",
        "Setup",
        "Installed, calibrated probe and reviewed approach",
        "Enter independently measured setup dimensions",
    ),
    CapabilityDescription(
        "atc",
        "Automatic tool changer",
        "Setup",
        "Current hardware flag, loaded tools and calibration",
        "Use reviewed manual tool changes",
    ),
    CapabilityDescription(
        "feed_override",
        "Feed override",
        "Spindle",
        "Supported transport and fresh override readback",
        "Revise programmed feed in CAM",
    ),
    CapabilityDescription(
        "custom_slots",
        "Custom tool pockets",
        "Setup",
        "Supported firmware and measured pocket coordinates",
        "Use the standard magazine layout",
    ),
    CapabilityDescription(
        "inverse_time",
        "Inverse-time feed",
        "Program",
        "Compatible postprocessor and rotary setup",
        "Use a supported indexed program",
    ),
    CapabilityDescription(
        "rotary",
        "Rotary machining",
        "Scene",
        "Verified rotary attachment and calibrated axis",
        "Prepare indexed setup geometry locally",
        True,
    ),
    CapabilityDescription(
        "tcp",
        "Five-axis tool-center control",
        "Scene",
        "Qualified TCP backend and machine kinematics",
        "Inspect tool/joint geometry in simulation",
        True,
    ),
    CapabilityDescription(
        "rigid_tapping",
        "Rigid tapping",
        "Setup",
        "Encoder synchronization and qualified tapping backend",
        "Use the thread-milling planner with a suitable cutter",
    ),
    CapabilityDescription(
        "coolant",
        "Flood coolant",
        "Settings",
        "Supported output and observed supply feedback",
        "Review supported air/extraction accessories",
    ),
    CapabilityDescription(
        "named_io",
        "Air, light and extraction",
        "Settings",
        "Mapped outputs and installed accessory feedback",
        "Inspect machine-specific accessory configuration",
    ),
)


def capability_rows(observations, *, connected, now):
    """Never promote saved profile state or an old connection's identity."""
    firmware = observations.get("firmware", "")
    model = observations.get("model", "")
    stamp = observations.get("status_at")
    fresh = connected and stamp is not None and math.isfinite(now) and 0 <= now - stamp <= 0.8
    capabilities = None
    if fresh and model in ("C1", "CA1", "Air") and firmware:
        capabilities = carvera_capabilities(
            "observed",
            model,
            FirmwareIdentity("community" if "c" in firmware.lower() else "vendor", firmware),
            stamp,
            has_atc=observations.get("has_atc"),
        )
    rows = []
    for description in DESCRIPTIONS:
        evidence = capabilities.features.get(description.key) if capabilities else None
        support = evidence.actual if evidence else Support.UNKNOWN
        if support == Support.SUPPORTED:
            state = "Protocol available"
            reason = (
                "Current hardware flag"
                if description.key == "atc"
                else "Published support inferred from observed firmware"
            )
        elif support == Support.UNSUPPORTED:
            state = (
                "Not detected"
                if description.key == "atc"
                else "Simulation only"
                if description.simulation
                else "Unsupported by adapter"
            )
            reason = evidence.source
        else:
            state = "Simulation only" if description.simulation else "Needs verification"
            reason = (
                "Disconnected; prior session observations do not establish availability"
                if not connected
                else "Status is missing or stale"
                if not fresh
                else "Firmware, hardware or backend capability is unresolved"
            )
        rows.append(
            {
                "key": description.key,
                "title": description.title,
                "state": state,
                "reason": reason,
                "prerequisite": description.prerequisite,
                "alternative": description.alternative,
                "section": description.section,
                "source": evidence.source if evidence else "No current capability evidence",
                "status_at": stamp,
                "identity_observed_at": observations.get("identity_at"),
                "generation": observations.get("generation"),
            }
        )
    return rows
