"""Compact, read-only explanation of measured workbench navigation latency."""

from carveracontroller.desktop_components import AMBER, MUTED


def refresh_navigation_timing(workspace):
    records = workspace.navigation_timings.records
    if not records:
        workspace.navigation_timing_note.text = "Switch a workbench tab to measure navigation."
        return
    record = records[-1]

    def duration(key):
        value = record[key]
        return "unobserved" if value is None else f"{value * 1000:.0f} ms"

    phases = record["phases_s"]
    slowest = max(phases, key=phases.get) if phases else None
    phase = f" · largest phase {slowest.replace('_', ' ')} {phases[slowest] * 1000:.0f} ms" if slowest else ""
    completed_refreshes = [r for r in workspace.refresh_timings.records if r["callback_s"] is not None]
    refresh_note = ""
    if completed_refreshes:
        worst = max(completed_refreshes, key=lambda r: r["callback_s"])
        refresh_phases = worst["phases_s"]
        slow_phase = max(refresh_phases, key=refresh_phases.get) if refresh_phases else None
        refresh_note = f"\nLargest retained UI refresh {worst['callback_s'] * 1000:.0f} ms"
        if slow_phase:
            refresh_note += f" · {slow_phase.replace('_', ' ')} {refresh_phases[slow_phase] * 1000:.0f} ms"
    workspace.navigation_timing_note.text = (
        f"Last tab: {record['target']} · callback {duration('callback_s')}{phase}\n"
        f"Next clock turn {duration('clock_turn_s')} · window flip {duration('window_flip_s')}\n"
        "Measured from callback entry; excludes input dispatch. A flip notification does not prove presentation. "
        "Export signal diagnostics in Spindle for retained phase timings." + refresh_note
    )
    workspace.navigation_timing_note.color = (
        AMBER if any((record[key] or 0) > 0.2 for key in ("callback_s", "clock_turn_s", "window_flip_s")) else MUTED
    )
