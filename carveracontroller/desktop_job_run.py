"""Reported identity, explicit operator review and retained backend job controls."""

import copy
import json
import threading
import time
from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_backend_transactions import require_idle_transaction
from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface
from carveracontroller.desktop_planning import PlanningCard, planning_popup
from carveracontroller.headless.job_identity import reported_identity, supported_identity
from carveracontroller.headless.job_run import JobRun, require_setup
from carveracontroller.machine.desktop_control_owner import reported_state


def wcs_name(index):
    return f"G{54 + int(index)}" if index < 6 else f"G59.{int(index) - 5}"


class JobRunPanel(Surface):
    def __init__(self, file_panel, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(7), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.file_panel = file_panel
        self.identity = self.run = self.popup = None
        self.journaling = False
        self.status = flowing_text("Machine run · read actual model and version before reviewing execution.", 32)
        self.add_widget(self.status)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.identity_action = Action("Read machine identity", self.read_identity)
        self.review_action = Action("Review machine run", self.review_run, disabled=True)
        self.pause_action = Action("Pause job", lambda: self.dispatch_run("job.pause"), disabled=True)
        self.resume_action = Action("Resume job", lambda: self.dispatch_run("job.resume"), disabled=True)
        self.cancel_action = Action("Cancel job", lambda: self.dispatch_run("job.cancel"), disabled=True, danger=True)
        for action in (
            self.identity_action,
            self.review_action,
            self.pause_action,
            self.resume_action,
            self.cancel_action,
        ):
            actions.add_widget(action)
        self.add_widget(actions)
        self.note = flowing_text(
            "Each start requires an explicit operator approval of the exact file and reported setup. Reported measurements and job state do not establish physical accuracy or completed motion.",
            44,
        )
        self.add_widget(self.note)

    @property
    def active(self):
        return self.run is not None and self.run.phase not in ("review", "settled_reported")

    def reset(self):
        if self.popup is not None:
            self.popup.dismiss()
        self.identity = self.run = self.popup = None
        self.status.text = "Machine run · read actual model and version before reviewing execution."

    def read_identity(self):
        panel = self.file_panel
        if panel.busy or panel.closed or self.active or self.journaling:
            return
        try:
            client = panel._validate_job("compile")
        except ValueError as error:
            self.note.text = str(error)
            return
        job, path, generation = panel.job, panel.journal_path, panel.generation
        panel.busy = True
        self.identity = None
        self.run = None
        if self.popup is not None:
            self.popup.dismiss()
        self.status.text = "Reading model and version from this connection…"
        self.refresh()

        def read():
            record = {
                "session_id": client.session_id,
                "connection_id": job.connection_id,
                "receipts": [],
                "authenticated": False,
            }
            error = None
            try:
                for query in ("model", "version"):
                    if panel.closed or panel.generation != generation:
                        raise ValueError("Panel retired during identity discovery")
                    response = client.submit(
                        "operation", {"operation": "observe.query", "parameters": {"query": query}}
                    ).result()
                    record["receipts"].append(
                        {
                            "query": query,
                            "request_id": response.envelope.get("id"),
                            "request_sha256": response.request_sha256,
                            "response_sha256": response.response_sha256,
                            "result": response.envelope,
                        }
                    )
                    job.identity_record = copy.deepcopy(record)
                    panel._journal(job, path)
                    if response.envelope.get("ok") is not True:
                        raise ValueError("The backend refused the identity query")
                    record[query] = reported_identity(response.envelope["result"], query, job.connection_id)
                job.identity_record = copy.deepcopy(record)
                panel._journal(job, path)
            except Exception as failure:
                error = str(failure)

            def finish(_dt):
                if panel.closed or panel.generation != generation or panel.job is not job:
                    return
                panel.busy = False
                if error:
                    self.note.text = error + ". Identity discovery was not retried."
                else:
                    try:
                        if panel._validate_job("compile") is not client:
                            raise ValueError("The backend child changed during identity discovery")
                        self.identity = record
                        self.note.text = (
                            "Model and version were reported on this connection. These are unsigned controller reports."
                        )
                    except ValueError as failure:
                        self.note.text = str(failure)
                panel.refresh()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=read, name="desktop-job-identity", daemon=True).start()

    def review_run(self):
        panel = self.file_panel
        if panel.closed or panel.busy or self.active or self.journaling:
            return
        try:
            client = panel._validate_job("compile")
            if self.identity is None:
                raise ValueError("Read this connection's actual model and version first")
            context = panel._context()
            run = JobRun(panel.job, context, self.identity, client.snapshot(), time.monotonic(), time.time())
        except (ValueError, TypeError) as error:
            self.note.text = str(error)
            return
        self.run = run
        body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        body.add_widget(
            flowing_text(
                f"{panel.job.source}\nController copy: {panel.job.remote_path}\nSHA-256: {panel.job.sha256}", 52
            )
        )
        body.add_widget(
            flowing_text(
                f"Reported machine: {self.identity['model']['reported_model']} · firmware {self.identity['version']['reported_version']}\nWCS: {wcs_name(run.review_reports['active_wcs'])} · tool: {run.review_reports.get('tool')}\nFour setup groups have current operator measurement records.",
                52,
            )
        )
        body.add_widget(
            flowing_text(
                "Starting approves execution of this exact program using the displayed reported machine and setup. Confirm the physical stock, workholding, tools, offsets and clear travel before starting. This review expires after 30 seconds.",
                68,
            )
        )
        body.add_widget(
            flowing_text(
                "Reported machine XYZ (mm): "
                + json.dumps(run.review_reports["machine_position"], sort_keys=True)
                + "\nReported work XYZ (mm): "
                + json.dumps(run.review_reports["work_position"], sort_keys=True)
                + "\nReported tool offset (firmware units): "
                + str(run.review_reports["tool_offset_reported"]),
                64,
            )
        )
        for item in context["evidence"]:
            receipt = item["receipt"]
            card = PlanningCard(item["key"].title() + " · measured setup")
            card.content.add_widget(
                flowing_text(
                    "Method: "
                    + receipt["method"]
                    + "\nExpires: "
                    + datetime.fromtimestamp(receipt["expires_at"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    + "\n"
                    + json.dumps(context["setup"][item["key"]], indent=2, sort_keys=True, allow_nan=False),
                    40,
                )
            )
            body.add_widget(card)
        confirm = Action(
            "Start reviewed program", lambda: self.dispatch_run("job.start", reviewed_run=run), primary=True
        )
        body.add_widget(confirm)
        body.add_widget(Action("Return to workbench", lambda: self.popup.dismiss()))
        if self.popup is not None:
            self.popup.dismiss()
        self.popup = planning_popup("Review machine run", body)
        self.popup.open()
        self.refresh()

    def can_control(self, operation):
        panel = self.file_panel
        if panel.closed or panel.busy or self.journaling or self.run is None:
            return False
        try:
            if operation in ("job.start", "job.resume"):
                require_idle_transaction(panel.workspace, "job")
            client, state, _identity = panel._binding()
            copy.copy(self.run).authorize(
                operation, client.session_id, state, panel._context(), time.monotonic(), time.time()
            )
            return True
        except (ValueError, TypeError):
            return False

    def dispatch_run(self, operation, *, reviewed_run=None, _state_refreshed=False):
        panel = self.file_panel
        if panel.closed or panel.busy or self.journaling or self.run is None:
            return
        if reviewed_run is not None and reviewed_run is not self.run:
            self.note.text = "This run review was replaced. Review the current file again."
            return
        try:
            if operation in ("job.start", "job.resume"):
                require_idle_transaction(panel.workspace, "job")
            client, state, _identity = panel._binding()
            if operation in ("job.start", "job.resume") and reported_state(state) is None and not _state_refreshed:
                self._refresh_dispatch_state(operation, client, self.run)
                return
            params = self.run.authorize(
                operation, client.session_id, state, panel._context(), time.monotonic(), time.time()
            )
        except (ValueError, TypeError) as error:
            self.note.text = str(error)
            return
        run, job, path, generation = self.run, panel.job, panel.journal_path, panel.generation
        job.run_record = run.record()
        panel.busy = True
        self.note.text = "Saving the approved job intent before dispatch…"
        if operation == "job.start":
            panel.note.text = "Operator-approved run · saving intent and rechecking context before submission."
        self.refresh()

        def dispatch():
            submitted = False
            error = None
            try:
                panel._journal(job, path)
                if panel.closed or panel.generation != generation:
                    raise ValueError("Panel retired before job submission")
                # Durable intent IO can outdate the UI's cached lease report.
                # Read the child's cache off the UI thread before the existing
                # final UI/context/freshness admission check. This is observation
                # only; it neither sends a firmware command nor grants admission.
                state_response = client.submit("snapshot").result()
                if state_response.envelope.get("ok") is not True:
                    raise ValueError("Current backend state unavailable before job submission")
                ready = threading.Event()
                admitted = []
                admission_lock = threading.Lock()
                abandoned = threading.Event()

                def preflight(_dt):
                    with admission_lock:
                        try:
                            if (
                                abandoned.is_set()
                                or panel.closed
                                or panel.generation != generation
                                or panel.job is not job
                                or self.run is not run
                            ):
                                raise ValueError("Run context retired before submission")
                            current, current_state, _identity = panel._binding()
                            if current is not client:
                                raise ValueError("The private child changed before submission")
                            if operation in ("job.start", "job.resume"):
                                require_idle_transaction(panel.workspace, "job")
                            check = copy.copy(run)
                            check.phase = run.pending_previous_phase
                            check.authorize(
                                operation,
                                current.session_id,
                                current_state,
                                panel._context(),
                                time.monotonic(),
                                time.time(),
                            )
                            # The SDK queues without waiting for pipe IO. Submit in
                            # this same UI callback so a later UI edit cannot slip
                            # between the final context check and admission.
                            admitted.append(current.submit("operation", params))
                        except Exception:
                            admitted.append(False)
                        finally:
                            ready.set()

                Clock.schedule_once(preflight, 0)
                if not ready.wait(5):
                    with admission_lock:
                        if not ready.is_set():
                            abandoned.set()
                if abandoned.is_set() or len(admitted) != 1 or admitted[0] is False:
                    raise ValueError("Run context or machine state changed before dispatch; review again")
                future = admitted[0]
                submitted = True
                run.accept(operation, future.result())
            except Exception as failure:
                error = str(failure)
                run.phase = "unresolved"
                run.receipts.append(
                    {
                        "operation": operation,
                        "outcome": "backend_response_unknown" if submitted else "not_submitted",
                        "error_type": type(failure).__name__,
                    }
                )
            try:
                job.run_record = run.record()
                panel._journal(job, path)
            except Exception:
                run.phase = "unresolved"
                error = "The run result could not be retained"

            def finish(_dt):
                if panel.closed or panel.generation != generation or panel.job is not job or self.run is not run:
                    return
                panel.busy = False
                if self.popup is not None:
                    self.popup.dismiss()
                if operation == "job.start":
                    panel.note.text = (
                        "Run submission unresolved · inspect the retained receipt."
                        if error
                        else "Reviewed program command acknowledged · see the reported job state below."
                    )
                self.note.text = (
                    error + ". No automatic retry or replay."
                    if error
                    else "Controller acknowledged the job command. Observe subsequent machine state; completed motion is unconfirmed."
                )
                panel.refresh()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=dispatch, name="desktop-job-run-operation", daemon=True).start()

    def _refresh_dispatch_state(self, operation, client, run):
        """One private cache read per click; no machine command or replay.

        Constructing a rich review can outdate the last UI-driven cache poll.
        Refresh off the UI thread before the original admission and intent
        journal. The same expiring run is checked again; limits stay unchanged.
        """
        panel = self.file_panel
        job, generation = panel.job, panel.generation
        panel.busy = True
        self.note.text = "Reading the current private state before admitting this reviewed request…"
        self.refresh()

        def read():
            error = None
            try:
                if client.submit("snapshot").result().envelope.get("ok") is not True:
                    raise ValueError("Current private state unavailable")
            except Exception:
                error = "Current private state could not be read; no job request submitted"

            def finish(_dt):
                if panel.closed or panel.generation != generation or panel.job is not job or self.run is not run:
                    return
                panel.busy = False
                if error:
                    self.note.text = error
                    panel.refresh()
                    return
                try:
                    current, _state, _identity = panel._binding()
                    if current is not client:
                        raise ValueError("The private child changed before admission")
                except ValueError as failure:
                    self.note.text = str(failure)
                    panel.refresh()
                    return
                self.dispatch_run(operation, reviewed_run=run, _state_refreshed=True)

            Clock.schedule_once(finish, 0)

        threading.Thread(target=read, name="desktop-job-run-state", daemon=True).start()

    def refresh(self):
        panel = self.file_panel
        if panel.closed:
            return
        self.identity_action.disabled = panel.busy or self.journaling or self.active or panel.job is None
        self.review_action.disabled = (
            panel.busy
            or self.journaling
            or self.active
            or self.identity is None
            or panel.job is None
            or panel.job.phase != "reviewed"
        )
        if self.identity is not None:
            self.status.text = f"Reported {self.identity['model']['reported_model']} · firmware {self.identity['version']['reported_version']}"
        if self.run is not None:
            if not panel.busy and not self.journaling:
                client = getattr(panel.workspace.backend_panel, "client", None)
                before = self.run.phase
                if client is not None and client.session_id == self.run.file.session_id:
                    self.run.observe(client.snapshot())
                if before != self.run.phase:
                    self._retain_observation()
            self.status.text += "\nJob: " + self.run.phase.replace("_", " ")
        for button, operation in (
            (self.pause_action, "job.pause"),
            (self.resume_action, "job.resume"),
            (self.cancel_action, "job.cancel"),
        ):
            button.disabled = not self.can_control(operation)

    def _retain_observation(self):
        panel = self.file_panel
        run, job, path = self.run, panel.job, panel.journal_path
        job.run_record = run.record()
        self.journaling = True

        def save():
            error = None
            try:
                panel._journal(job, path)
            except Exception:
                run.phase = "unresolved"
                error = "Could not retain the reported job state; inspect the current connection before recovery."

            def finish(_dt):
                self.journaling = False
                if panel.closed or self.run is not run:
                    return
                if error:
                    self.note.text = error
                self.refresh()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=save, name="desktop-job-run-report", daemon=True).start()

    def allows_hold_resume(self):
        if not self.active:
            return True
        panel = self.file_panel
        if self.run.phase == "unresolved" or panel.busy or self.journaling:
            return False
        try:
            client, state, identity = panel._binding()
            context = panel._context()
            require_setup(context, time.time())
            status = (state.get("last_machine_snapshot") or {}).get("status") or {}
            return self.run.file.matches(client.session_id, identity, context) and supported_identity(
                self.run.identity["model"], self.run.identity["version"], status
            )
        except ValueError:
            return False

    def dispose(self):
        if self.popup is not None:
            self.popup.dismiss()
