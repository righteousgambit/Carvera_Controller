"""Read-only local startup inspector; never polls or connects the CNC."""

import json
from datetime import datetime, timezone

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, AMBER, PANEL, TEXT, Action, Surface
from carveracontroller.desktop_planning import planning_popup


def capture_startup(client, endpoint_profile):
    state = client.snapshot()
    return {
        "schema_version": "carvera.desktop_startup_diagnostic.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "session_id": state.get("session_id"),
        "pid": state.get("pid"),
        "profile_id_at_start": endpoint_profile[0] if endpoint_profile else None,
        "host": state.get("host"),
        "port": state.get("port"),
        "startup": state.get("startup"),
        "running_at_observation": state.get("running"),
        "ready_at_observation": state.get("ready"),
        "failure_at_observation": state.get("failure"),
        "cnc_connection_or_motion_verified": False,
    }


def show_startup(record):
    startup = record.get("startup") or {}
    body = Surface(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None)
    body.bind(minimum_height=body.setter("height"))
    summary = flowing_text(
        "Startup: "
        + startup.get("phase", "timing unavailable").replace("_", " ")
        + f"\nSession {record.get('session_id') or 'unknown'} · PID {record.get('pid') or 'unknown'}"
        + f"\nConfigured endpoint {record.get('host') or 'unknown'}:{record.get('port') or 'unknown'}",
        24,
    )
    summary.color = AMBER if startup.get("phase") in ("timed_out", "failed") else TEXT
    body.add_widget(summary)

    def duration(key):
        value = startup.get(key)
        return "Unknown" if value is None else f"{value:.2f} ms"

    def flag(key):
        return {True: "Yes", False: "No", None: "Unknown"}[record.get(key)]

    timing = flowing_text(
        "Process launch: "
        + duration("process_launch_ms")
        + "\nLaunch to validated ready report: "
        + duration("ready_wait_ms")
        + "\nTotal startup: "
        + duration("total_startup_ms")
        + f"\nReadiness wait limit: {startup.get('configured_ready_wait_limit_s', 'unknown')} s",
        24,
    )
    body.add_widget(timing)
    body.add_widget(
        flowing_text(
            f"Observed running: {flag('running_at_observation')} · ready: {flag('ready_at_observation')}"
            + f"\nStartup failure: {startup.get('failure_code') or 'none recorded'}"
            + f"\nCurrent client failure: {record.get('failure_at_observation') or 'none recorded'}"
            + f"\nChild exit code: {startup.get('process_returncode') if startup.get('process_returncode') is not None else 'not observed'}"
            + f"\nPrivate stderr drained: {startup.get('stderr_bytes_drained', 'unknown')} bytes; content not retained.",
            24,
        )
    )
    body.add_widget(
        flowing_text(
            "This report captures local child startup and a single runtime observation. Readiness timing is host receipt timing. The wait limit starts after the child and its pipe workers are launched; process creation adds to total startup. CNC connection, network latency, physical readiness and motion are unverified. No retry or connection is requested.",
            24,
        )
    )
    popup = planning_popup("Local backend startup", body)
    popup.background = ""
    popup.background_color = PANEL
    popup.separator_color = ACCENT
    popup.title_color = TEXT
    popup.title_size = sp(14)
    popup.startup_summary, popup.startup_timing = summary, timing
    popup.startup_record = record
    popup.copy_action = Action(
        "Copy diagnostic report", lambda: Clipboard.copy(json.dumps(record, indent=2, allow_nan=False))
    )
    body.add_widget(popup.copy_action)
    body.add_widget(Action("Close", popup.dismiss))
    popup.open()
    return popup
