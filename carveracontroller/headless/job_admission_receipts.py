"""Bounded final-admission diagnostics; never grants or repeats a dispatch."""

from __future__ import annotations

from typing import Any

from ..machine.backend_live_report import finite

KNOWN_REASONS = frozenset(
    (
        "Run context retired before submission",
        "The private child changed before submission",
        "Select the connected backend as the workbench owner first",
        "The backend has an active transfer or an unresolved outcome",
        "The selected connection has a pending or unresolved tool exchange; inspect its receipt first",
        "The probe-settings workflow owns an unfinished transaction",
        "The retained job needs its current unambiguous backend connection and fresh status",
        "Run review requires fresh Idle, no playing job, zero spindle and known coordinates",
        "Run review requires complete reported XYZ coordinates",
        "The job belongs to another private child",
        "Program, profile or setup changed after run review",
        "Reported machine identity changed",
        "Run review is expired or already submitted; review again",
        "Reported position, coordinates, tooling or overrides changed after review",
        "Resume requires this retained suspended job and unchanged review context",
        "Setup measurements are missing, changed or expired",
        "Review all four setup evidence groups before a machine run",
        "Setup evidence groups are missing or duplicated",
        "Setup evidence needs a finite current UTC time",
    )
)


def admission_refusal(error: Exception, state: dict[str, Any] | None) -> dict[str, Any]:
    """Retain owned validation reasons and clock evidence, not arbitrary errors."""
    text = str(error) if type(error) is ValueError else ""
    state = state or {}
    snapshot = state.get("last_machine_snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    cached, child_ms = finite(state.get("last_machine_snapshot_age_s")), finite(snapshot.get("status_age_ms"))
    cached = cached if cached is not None and cached >= 0 else None
    child_s = child_ms / 1000 if child_ms is not None and child_ms >= 0 else None
    combined = finite(cached + child_s) if cached is not None and child_s is not None else None
    return {
        "error_type": type(error).__name__[:100],
        "reason": text
        if text in KNOWN_REASONS
        else "Final UI admission refused; inspect the retained context and current state",
        "cached_snapshot_age_s": cached,
        "child_status_age_s": child_s,
        "combined_report_age_s": combined,
        "timing_source": "client cache and child host receipt ages; not firmware sample age",
    }
