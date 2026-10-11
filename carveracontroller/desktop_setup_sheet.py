"""Explicit offline setup handoff using the shared local file picker."""

import copy
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from kivy.clock import Clock

from carveracontroller.desktop_job_packages import _import_owner, capture_recording_job
from carveracontroller.machine.setup_readiness import evaluate_setup, fingerprint
from carveracontroller.machine.setup_sheet import save_setup_sheet, setup_sheet


def _capture(workspace):
    if not workspace.app.selected_local_filename:
        raise ValueError("Choose a local program before exporting a setup sheet")
    job = capture_recording_job(workspace, include_camera=False)
    program = workspace.operation_panel.program
    job.inspection_plan["loaded_preview_sha256"] = program.file_hash if program else None
    readiness = workspace.readiness
    machine, snapshots, present = readiness.snapshot()
    checks = [asdict(item) for item in evaluate_setup(machine, snapshots, present, readiness.store, time.time())]
    declarations = {
        key: copy.deepcopy(getattr(job, key))
        for key in ("machine", "tools", "toolsets", "stock", "fixtures", "vise", "inspection_plan")
    }
    return job, checks, (_import_owner(workspace), fingerprint(declarations), fingerprint(snapshots))


def export_setup_sheet(workspace):
    if getattr(workspace, "_setup_sheet_pending", False) or workspace._profile_load_closed:
        return
    try:
        _job, _checks, owner = _capture(workspace)
    except (ValueError, OSError, TypeError) as exc:
        workspace.package_note.text = str(exc)
        return

    def selected(path):
        if workspace._profile_load_closed or getattr(workspace, "_setup_sheet_pending", False):
            return
        try:
            job, checks, current = _capture(workspace)
            if current != owner:
                raise ValueError("Program or setup changed while choosing the destination; export again")
            destination = Path(path).expanduser().resolve()
            sources = {Path(workspace.app.selected_local_filename).expanduser().resolve()}
            sources.update(asset.expanduser().resolve() for asset in job.assets.values() if isinstance(asset, Path))
            if destination in sources:
                raise ValueError("Choose a separate HTML destination; source program and CAD assets are preserved")
        except (ValueError, OSError, TypeError) as exc:
            workspace.package_note.text = str(exc)
            return
        workspace._setup_sheet_pending = True
        captured = datetime.now(timezone.utc).isoformat()
        filename = Path(workspace.app.selected_local_filename)
        workspace.package_note.text = "Preparing revision-bound setup sheet…"

        def finished(error, digest):
            workspace._setup_sheet_pending = False
            if workspace._profile_load_closed:
                return
            if error:
                workspace.package_note.text = "Setup sheet failed: " + error
                return
            try:
                _job, _checks, current = _capture(workspace)
                stale = current != owner
            except (ValueError, OSError, TypeError):
                stale = True
            workspace.package_note.text = f"Saved setup sheet: {path}\nHTML SHA256 {digest}" + (
                "\nSetup changed during export; retained sheet is a historical snapshot." if stale else ""
            )

        def run():
            try:
                with filename.open("rb") as source:
                    job.program = source.read(64 * 1024 * 1024 + 1)
                digest = save_setup_sheet(setup_sheet(job, checks, captured), path)
                error = None
            except (ValueError, OSError, TypeError) as exc:
                digest, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finished(error, digest), 0)

        threading.Thread(target=run, name="setup-sheet-export", daemon=True).start()

    workspace.choose_profile_file(
        selected, save=True, extension=".html", title="Export setup sheet for screen or print"
    )
