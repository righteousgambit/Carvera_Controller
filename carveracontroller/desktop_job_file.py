"""Backend-owned job transfer and independent controller file readback."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface
from carveracontroller.desktop_planning import PlanningCard
from carveracontroller.headless.arguments import MAX_FILE
from carveracontroller.headless.client import ClientUnavailable
from carveracontroller.headless.job_file import JobFile, context_digest
from carveracontroller.machine.desktop_control_owner import reported_state


class JobFilePanel(Surface):
    def __init__(self, workspace, journal_root=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.journal_root = Path(journal_root or Path.home() / ".carvera" / "backend-jobs")
        self.journal_path = None
        self.job = None
        self.busy = self.closed = False
        self.generation = 0
        self.heading = flowing_text("Controller job file", 26)
        self.add_widget(self.heading)
        self.note = flowing_text(
            "Use the backend for workbench controls, then choose a local program. Freeze its bytes, transfer it, and verify the controller's copy by downloading it.",
            52,
        )
        self.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=2, min_width=160, row_height=38, spacing=dp(6))
        self.freeze_action = Action("Freeze selected program", self.freeze)
        self.upload_action = Action("Upload frozen file", lambda: self.request("upload"), disabled=True)
        self.verify_action = Action("Read back & verify", lambda: self.request("download"), disabled=True)
        self.review_action = Action("Review start command", lambda: self.request("compile"), disabled=True)
        for button in (self.freeze_action, self.upload_action, self.verify_action, self.review_action):
            actions.add_widget(button)
        self.add_widget(actions)
        self.summary = flowing_text("No file frozen for this backend connection.", 26)
        self.add_widget(self.summary)
        self.identity_card = PlanningCard("File identity & receipts")
        self.details = flowing_text("", 26)
        self.identity_card.content.add_widget(self.details)
        self.add_widget(self.identity_card)
        self.review = flowing_text(
            "Execution admission remains open: the backend command dialect is not an actual firmware identity, and setup measurements do not grant run permission.",
            48,
        )
        self.add_widget(self.review)
        from carveracontroller.desktop_job_run import JobRunPanel

        self.run_panel = JobRunPanel(self)
        self.add_widget(self.run_panel)

    def _context(self):
        ws = self.workspace
        machine_id, snapshots, present = ws.readiness.snapshot()
        path = Path(ws.app.selected_local_filename) if ws.app.selected_local_filename else None
        try:
            stat = path.stat() if path is not None else None
            source_revision = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns] if stat is not None else None
        except OSError:
            source_revision = None
        return {
            "local_file": ws.app.selected_local_filename,
            "source_revision": source_revision,
            "machine_id": machine_id,
            "profile": ws.selected_machine_profile,
            "setup": snapshots,
            "present": present,
            "evidence": [
                {"key": item.key, "state": item.state, "receipt": item.receipt} for item in ws.readiness.items
            ],
        }

    def _binding(self):
        ws = self.workspace
        panel = getattr(ws, "backend_panel", None)
        client = panel.client if panel is not None else None
        if (
            self.closed
            or client is None
            or panel.closed
            or panel.stopping
            or not ws.control_owner.matches(client.session_id, client.snapshot())
            or panel.endpoint_profile != panel._profile_key()
        ):
            raise ValueError("Select the connected backend as the workbench owner first")
        state = client.snapshot()
        snapshot = state["last_machine_snapshot"]
        if snapshot.get("unknown_outcome") is not False or snapshot.get("transfer_active") is not False:
            raise ValueError("The backend has an active transfer or an unresolved outcome")
        return client, state, snapshot["connection_id"]

    def _validate_job(self, action):
        client, state, identity = self._binding()
        if self.job is None or not self.job.matches(client.session_id, identity, self._context()):
            raise ValueError("Program, setup evidence, profile or connection changed; freeze a new file")
        if action == "upload":
            status = state["last_machine_snapshot"].get("status") or {}
            if (
                reported_state(state) != "Idle"
                or status.get("is_playing") is not False
                or type(status.get("spindle_rpm")) not in (int, float)
                or status["spindle_rpm"] != 0
                or type(status.get("spindle_target_rpm")) not in (int, float)
                or status["spindle_target_rpm"] != 0
            ):
                raise ValueError("Upload requires a fresh Idle report with no playing job and zero spindle reports")
        return client

    def can_review(self):
        try:
            _client, state, _identity = self._binding()
            status = state["last_machine_snapshot"].get("status") or {}
            return (
                reported_state(state) == "Idle"
                and status.get("is_playing") is False
                and type(status.get("spindle_rpm")) in (int, float)
                and status["spindle_rpm"] == 0
                and type(status.get("spindle_target_rpm")) in (int, float)
                and status["spindle_target_rpm"] == 0
            )
        except ValueError:
            return False

    def _journal(self, job=None, path=None, *, new=False):
        # A new attempt gets a distinct append-only file. Failure to retain a
        # pending intent prevents submission; no receipt can imply execution.
        path = None if new else path or self.journal_path
        if path is None:
            self.journal_root.mkdir(parents=True, exist_ok=True)
            path = self.journal_root / f"{uuid4().hex}.jsonl"
            mode = "x"
        else:
            mode = "a"
        with path.open(mode, encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"observed_at": datetime.now(timezone.utc).isoformat(), **(job or self.job).record()},
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        return path

    def freeze(self):
        if self.closed or self.busy or self.run_panel.active or self.run_panel.journaling:
            return
        try:
            client, _state, identity = self._binding()
            context = self._context()
            source = self.workspace.app.selected_local_filename
            if not source:
                raise ValueError("Choose a local program before freezing its bytes")
            context_hash = context_digest(context)
        except ValueError as error:
            self.note.text = str(error)
            return
        self.busy = True
        self.generation += 1
        generation = self.generation
        self.note.text = "Reading selected program off the UI thread…"
        self._controls()

        def read():
            job, path, error = None, None, None
            try:
                with Path(source).open("rb") as stream:
                    data = stream.read(MAX_FILE + 1)
                job = JobFile(str(source), data, context_hash, client.session_id, identity)
                path = self._journal(job, new=True)
            except Exception as failure:
                error = f"Could not freeze the selected program: {type(failure).__name__}"

            def finish(_dt):
                if self.closed or self.generation != generation:
                    return
                self.busy = False
                try:
                    current, _state, current_id = self._binding()
                    if (
                        error
                        or current is not client
                        or not job.matches(current.session_id, current_id, self._context())
                    ):
                        raise ValueError(error or "The source context changed while reading; freeze again")
                    self.job, self.journal_path = job, path
                    self.run_panel.reset()
                    self.identity_card.set_expanded(False, reveal=False)
                    self.note.text = "Frozen local bytes. Upload is an explicit machine file write."
                except Exception as failure:
                    self.job = None
                    self.note.text = str(failure)
                self.refresh()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=read, name="desktop-job-file-read", daemon=True).start()

    def request(self, action):
        if self.closed or self.busy or action not in ("upload", "download", "compile"):
            return
        try:
            client = self._validate_job(action)
            expected = {"upload": "staged", "download": "uploaded", "compile": "verified"}
            if self.job.phase != expected[action]:
                raise ValueError("This file operation is unavailable; unresolved operations are never retried")
        except Exception as error:
            self.note.text = str(error)
            self._controls()
            return
        job, generation, path = self.job, self.generation, self.journal_path
        self.busy = True
        self.note.text = {
            "upload": "Uploading exact frozen bytes…",
            "download": "Reading controller bytes for independent verification…",
            "compile": "Compiling the exact start command without executing it…",
        }[action]
        self._controls()

        def run():
            begun = False
            submitted = False
            try:
                params = job.begin(action)
                begun = True
                self._journal(job, path)
                if self.closed or self.generation != generation:
                    raise ClientUnavailable("Panel retired before submission")
                # Pipe IO, base64/JSON encoding, readback comparison and durable
                # journaling all run off the Kivy thread. Stop uses its separate
                # urgent request lane while this worker awaits its own response.
                future = client.submit(action, params)
                submitted = True
                response = future.result()
                job.accept(action, response)
                if action in ("upload", "download"):
                    # The transfer receipt establishes its own file result.
                    # Independently read the child's current lease flags before
                    # enabling the next UI step; a mid-transfer cache may still
                    # say active even after the acknowledged transfer ended.
                    state_response = client.submit("snapshot").result()
                    state = state_response.envelope.get("result")
                    current = (
                        state_response.envelope.get("ok") is True
                        and isinstance(state, dict)
                        and state.get("connection_id") == job.connection_id
                        and state.get("connected") is True
                        and state.get("unknown_outcome") is False
                        and state.get("transfer_active") is False
                    )
                    job.receipts[-1]["post_transfer_state"] = {
                        "request_id": state_response.envelope.get("id"),
                        "request_sha256": state_response.request_sha256,
                        "response_sha256": state_response.response_sha256,
                        "received_at_s": state_response.received_at_s,
                        "outcome": "current_connection_idle_transfer" if current else "state_unavailable_or_changed",
                    }
                    if not current:
                        raise ValueError("Transfer receipt retained; current connection state requires review")
                message = {
                    "upload": "Upload acknowledged. The controller copy still needs readback.",
                    "download": "Independent readback matches every frozen byte.",
                    "compile": "Start command compiled for review. No job was started.",
                }[action]
            except Exception as failure:
                if begun and job.phase.endswith("_pending"):
                    job.fail(action, failure if submitted else ClientUnavailable(type(failure).__name__))
                message = str(failure) + ". This operation will not be retried."
            retained = True
            try:
                self._journal(job, path)
            except Exception:
                job.phase = "unresolved"
                retained = False

            def finish(_dt):
                if self.closed or self.generation != generation or self.job is not job:
                    return
                self.busy = False
                self.note.text = (
                    message if retained else "Could not retain the result receipt; this attempt remains unresolved."
                )
                if action == "compile" and job.phase == "reviewed":
                    self.identity_card.set_expanded(True)
                self.refresh()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, name="desktop-job-file-operation", daemon=True).start()

    def _controls(self):
        self.freeze_action.disabled = self.closed or self.busy or self.run_panel.active or self.run_panel.journaling
        phase = self.job.phase if self.job else None
        for button, expected in (
            (self.upload_action, "staged"),
            (self.verify_action, "uploaded"),
            (self.review_action, "verified"),
        ):
            button.disabled = self.closed or self.busy or phase != expected

    def refresh(self):
        if self.closed:
            return
        self.run_panel.refresh()
        if self.job:
            job = self.job
            caption = {
                "staged": "Local bytes frozen",
                "uploaded": "Uploaded · verification needed",
                "verified": "Controller bytes verified",
                "reviewed": "Controller bytes verified · start command reviewed",
                "unresolved": "Unresolved result · inspect receipts",
            }.get(job.phase, "Waiting for backend result")
            self.summary.text = f"{Path(job.source).name} · {len(job.data):,} bytes\n{caption}"
            self.details.text = f"{Path(job.source).name} · {len(job.data):,} bytes · {job.phase}\nSHA-256 {job.sha256}\nController file: {job.remote_path}\nReceipt: {self.journal_path}"
            if job.launch_plan is not None:
                self.details.text += "\nCompiled command: " + " / ".join(job.launch_plan["commands"])
                self.review.text = "File bytes and start command are verified. Read machine identity and review the run below before approving execution."
            else:
                self.review.text = "Verify the controller copy before reviewing its start command. Backend execution qualification remains open."
            try:
                self._validate_job("compile")
            except ValueError:
                self.details.text += "\nRetained attempt · current program/setup/connection differs or is unavailable."
                self.summary.text += "\nPrior context · freeze a new file for the current setup."
                self.review.text = "This receipt belongs to an earlier or unavailable context. Inspect it before freezing a new attempt."
                self.upload_action.disabled = self.verify_action.disabled = self.review_action.disabled = True
                return
        self._controls()

    def dispose(self):
        self.closed = True
        self.run_panel.dispose()
        self.generation += 1
        self._controls()
