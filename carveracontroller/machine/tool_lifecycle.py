"""Read-only physical-identity lifecycle evidence, with bounded history pages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from carveracontroller.machine.tool_custody import ToolCustodyStore

PAGE_SIZE = 20


def summary(store: ToolCustodyStore, assembly_id: str) -> list[str]:
    events = store.lifecycle_events(assembly_id)
    uses = [e for e in events if e["kind"] == "use"]
    seconds = sum(e["seconds"] for e in uses)
    retired = next((e for e in events if e["kind"] == "replacement" and e["assembly_id"] == assembly_id), None)
    incoming = next((e for e in events if e.get("replacement_id") == assembly_id), None)
    inspections = [e for e in events if e["kind"] == "inspection"]
    lines = [
        f"{len(uses)} attributed cutting intervals · {seconds / 60:.6g} minutes recorded",
        "Usage is operator-attributed evidence; unrecorded use and remaining life are unknown.",
    ]
    if inspections:
        latest = max(inspections, key=lambda e: (e["occurred_at"], e["at"]))
        lines.append(f"Latest operator inspection: {latest['condition']} · {latest['method']}")
    else:
        lines.append("No operator inspection recorded.")
    if retired:
        replacement = store.assembly(retired["replacement_id"])
        lines.append("Declared replaced by: " + (replacement["name"] if replacement else retired["replacement_id"]))
        lines.append(
            "Retired identity: new location declarations are blocked; existing locations require reconciliation."
        )
    if incoming:
        previous = store.assembly(incoming["assembly_id"])
        lines.append("Replaces: " + (previous["name"] if previous else incoming["assembly_id"]))
        lines.append("Earlier use and calibration receipts remain with the previous identity.")
    lines.append(f"{len(events)} lifecycle receipts · View lifecycle exposes every saved receipt.")
    return lines


def page(store: ToolCustodyStore, assembly_id: str, index: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Newest observation first; clamp page after context changes."""
    events = sorted(store.lifecycle_events(assembly_id), key=lambda e: (e["occurred_at"], e["at"]), reverse=True)
    pages = max(1, (len(events) + PAGE_SIZE - 1) // PAGE_SIZE)
    if type(index) is not int:
        raise ValueError("Lifecycle page must be an integer")
    index = max(0, min(index, pages - 1))
    return events[index * PAGE_SIZE : (index + 1) * PAGE_SIZE], pages


def describe(event: dict[str, Any]) -> str:
    observed = datetime.fromtimestamp(event["occurred_at"], timezone.utc).isoformat(timespec="seconds")
    recorded = datetime.fromtimestamp(event["at"], timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"{observed} · {event['kind']} · receipt {event['id']}",
        f"Assembly {event['assembly_id']} · definition {event['revision_id']}",
        f"Saved {recorded} · source: {event['source']}",
    ]
    if event["kind"] == "use":
        lines.append(
            f"{event['seconds'] / 60:.6g} cutting minutes · material {event['material']} · reference {event['reference']}"
        )
    elif event["kind"] == "inspection":
        value = event["measured_diameter_mm"]
        measurement = (
            "No cutting diameter measurement" if value is None else f"Measured cutting diameter {value:.6g} mm"
        )
        lines.append(f"Operator condition: {event['condition']} · method: {event['method']} · {measurement}")
    else:
        lines.append(f"Replacement {event['replacement_id']} · definition {event['replacement_revision_id']}")
    lines.append("Observation: " + event["note"])
    return "\n".join(lines)
