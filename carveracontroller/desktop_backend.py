"""Actual private backend inspection, separate from the live GUI controller."""

import threading
import time
from collections import deque

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, Surface
from carveracontroller.headless.client import SupervisorClient
from carveracontroller.headless.desktop_observation import describe_backend


class BackendPanel(Surface):
    def __init__(self, workspace, client_factory=SupervisorClient, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace, self.client_factory = workspace, client_factory
        self.client = None
        self.closed = self.busy = self.stopping = False
        self.generation = self.catalog_page = 0
        self.catalog = []
        self.endpoint_profile = None
        self.monitoring = False
        self.next_poll_at = 0
        self.control_pending = set()
        self.control_receipts = deque(maxlen=16)
        self._owner_lock = threading.Lock()
        self.heading = flowing_text("Local backend · stopped", 26)
        self.add_widget(self.heading)
        self.note = flowing_text(
            "Start the private backend to inspect its state and supported operations. Starting it leaves the CNC disconnected. Your live controller connection is separate.",
            62,
        )
        self.add_widget(self.note)
        self.actions = AdaptiveGrid(max_cols=2, min_width=160, row_height=38, spacing=dp(6))
        self.start_action = Action("Start local backend", self.start)
        self.snapshot_action = Action("Read backend state", lambda: self.request("snapshot"), disabled=True)
        self.catalog_action = Action("Read operation catalog", lambda: self.request("catalog"), disabled=True)
        self.stop_action = Action("Stop local backend", self.stop, disabled=True)
        self.connect_action = Action("Connect backend to machine", lambda: self.request("connect"), disabled=True)
        self.disconnect_action = Action("Disconnect backend", lambda: self.request("disconnect"), disabled=True)
        for action in (
            self.start_action,
            self.connect_action,
            self.snapshot_action,
            self.disconnect_action,
            self.catalog_action,
            self.stop_action,
        ):
            self.actions.add_widget(action)
        self.add_widget(self.actions)
        self.stop_requests = AdaptiveGrid(max_cols=2, min_width=160, row_height=38, spacing=dp(6))
        self.hold_action = Action("Feed hold · backend", lambda: self.request_stop("feed_hold"), disabled=True)
        self.abort_action = Action(
            "Software abort · backend", lambda: self.request_stop("software_abort"), disabled=True, danger=True
        )
        self.stop_requests.add_widget(self.hold_action)
        self.stop_requests.add_widget(self.abort_action)
        self.add_widget(self.stop_requests)
        self.control_note = flowing_text(
            "Stop requests target this backend's connection. They do not confirm a physical stop.", 32
        )
        self.add_widget(self.control_note)
        ownership = AdaptiveGrid(max_cols=2, min_width=160, row_height=38, spacing=dp(6))
        self.claim_action = Action(
            "Use backend for workbench controls", lambda: self.workspace.claim_backend_controls()
        )
        self.release_action = Action("Return to job controller", lambda: self.workspace.release_backend_controls())
        ownership.add_widget(self.claim_action)
        ownership.add_widget(self.release_action)
        self.add_widget(ownership)
        self.ownership_note = flowing_text("Workbench controls currently use the job controller.", 32)
        self.add_widget(self.ownership_note)
        self.status = flowing_text("No backend observations yet.", 52)
        self.add_widget(self.status)
        self.age_note = flowing_text("No private response observed.", 28)
        self.add_widget(self.age_note)
        self.telemetry = flowing_text("No machine reports observed.", 32)
        self.add_widget(self.telemetry)
        self.catalog_note = flowing_text("Read the catalog to inspect the operations compiled into this backend.", 32)
        self.add_widget(self.catalog_note)
        self.catalog_rows = flowing_text("", 0)
        self.add_widget(self.catalog_rows)
        paging = AdaptiveGrid(max_cols=2, min_width=160, row_height=34, spacing=dp(6))
        self.previous = Action("Previous operations", lambda: self.page(-1), disabled=True)
        self.next = Action("Next operations", lambda: self.page(1), disabled=True)
        paging.add_widget(self.previous)
        paging.add_widget(self.next)
        self.add_widget(paging)

    def _controls(self, state=None):
        state = self.client.snapshot() if state is None and self.client else state
        ready = state is not None and state["ready"] and state["running"]
        self.start_action.disabled = self.closed or self.busy or self.client is not None
        self.snapshot_action.disabled = self.catalog_action.disabled = self.closed or self.busy or not ready
        self.stop_action.disabled = self.closed or self.client is None or self.stopping
        observation = describe_backend(state or {})
        owner = getattr(self.workspace, "control_owner", None)
        selected = owner is not None and owner.backend_selected
        self.claim_action.disabled = (
            self.closed or self.stopping or not ready or owner is None or selected or observation.connected is not True
        )
        self.release_action.disabled = self.closed or owner is None or not selected
        self.start_action.disabled = self.start_action.disabled or selected
        self.connect_action.disabled = (
            self.closed
            or self.busy
            or not ready
            or observation.connected is not False
            or observation.unknown_outcome is not False
            or selected
        )
        self.disconnect_action.disabled = self.closed or self.busy or not ready or not observation.connected
        for action, button in (("feed_hold", self.hold_action), ("software_abort", self.abort_action)):
            button.disabled = (
                self.closed
                or self.stopping
                or not ready
                or observation.connected is not True
                or observation.connection_id is None
                or action in self.control_pending
            )

    def _profile_key(self):
        profile = self.workspace.selected_machine_profile or {}
        return profile.get("id"), profile.get("host") or "127.0.0.1", profile.get("port", 2222)

    def start(self):
        owner = getattr(self.workspace, "control_owner", None)
        if self.closed or self.busy or self.client is not None or (owner is not None and owner.backend_selected):
            return
        profile = self.workspace.selected_machine_profile or {}
        host, port = profile.get("host") or "127.0.0.1", profile.get("port", 2222)
        self.endpoint_profile = self._profile_key()
        self.control_pending.clear()
        self.busy = True
        self.generation += 1
        generation = self.generation
        self.heading.text = "Local backend · starting"
        self.note.text = "Starting a private child without opening a CNC connection…"
        self._controls()

        def run():
            client, error = None, None
            try:
                client = self.client_factory(host, port)
                with self._owner_lock:
                    if self.closed or generation != self.generation:
                        return
                    self.client = client
                Clock.schedule_once(
                    lambda _dt: self._controls() if not self.closed and generation == self.generation else None, 0
                )
                client.start()
            except Exception:
                error = "Backend could not start. Check the saved private IPv4 address and this application's backend entry point."
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        error = (
                            "Backend startup and shutdown did not finish. This session remains owned until it stops."
                        )

            def finish(_dt):
                if self.closed or generation != self.generation or self.client is not client:
                    return
                self.busy = False
                if error:
                    if client is None or not client.snapshot()["running"]:
                        self.client = None
                    self.heading.text = "Local backend · unavailable"
                    self.note.text = error
                    self._controls()
                else:
                    self.heading.text = "Local backend · ready"
                    self.note.text = f"Configured endpoint {host}:{port}. No CNC connection has been opened. State reads are local backend observations."
                    self.request("snapshot")

            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, name="desktop-backend-start", daemon=True).start()

    def request(self, method):
        if (
            self.closed
            or self.busy
            or self.client is None
            or method not in ("snapshot", "catalog", "connect", "disconnect")
        ):
            return
        if method == "connect":
            owner = getattr(self.workspace, "control_owner", None)
            if owner is not None and owner.backend_selected:
                self.note.text = (
                    "Return workbench controls to the job controller before opening a replacement backend connection."
                )
                return
            observation = describe_backend(self.client.snapshot())
            if observation.connected is not False or observation.unknown_outcome is not False:
                self.note.text = "This backend already owns a connection or retains an unresolved outcome. Read its state before proceeding."
                return
            if self.endpoint_profile != self._profile_key():
                self.note.text = "The selected machine profile changed. Stop and restart the backend for that profile before connecting."
                return
            controller = getattr(getattr(self.workspace, "machine", None), "controller", None)
            if controller is not None and getattr(controller, "stream", None) is not None:
                self.note.text = "The job controller owns a connection. Disconnect it before connecting the backend; that connection will not be closed automatically."
                return
        client, generation = self.client, self.generation
        self.busy = True
        self.note.text = {
            "connect": "Opening this backend's saved machine connection…",
            "disconnect": "Closing this backend's machine connection…",
        }.get(method, "Waiting for the private backend…")
        self._controls()
        try:
            future = client.submit(method)
        except Exception:
            self.busy = False
            self.note.text = "Backend request was refused. Stop this session before starting another."
            self._controls()
            return

        def received(future):
            try:
                response, error = future.result(), None
            except Exception:
                response, error = None, "The backend response is unavailable. This request was not retried."

            def finish(_dt):
                if self.closed or generation != self.generation or self.client is not client:
                    return
                self.busy = False
                if error or not response.envelope.get("ok"):
                    if error:
                        self.heading.text = "Local backend · unavailable"
                    self.note.text = error or (
                        "This machine endpoint is already owned by another controller. Disconnect that owner before trying again."
                        if response.envelope.get("error") == "EndpointBusyError"
                        else "The backend refused this connection request. It was not retried."
                        if method in ("connect", "disconnect")
                        else "The backend refused this observation request."
                    )
                    self.note.color = AMBER
                else:
                    result = response.envelope["result"]
                    elapsed = "unknown" if response.elapsed_ms is None else f"{response.elapsed_ms:.2f} ms"
                    self.note.text = f"Private backend response: {elapsed}. This is local IPC time, not CNC acknowledgment or physical response."
                    self.note.color = MUTED
                    if method in ("snapshot", "connect", "disconnect"):
                        connected = result.get("connected") is True
                        self.monitoring = connected
                        self.status.text = describe_backend(client.snapshot()).summary
                        if method in ("connect", "disconnect"):
                            self.note.text = (
                                "Backend connection opened. Reported position, spindle and inputs appear below; job controls still use the job controller."
                                if connected
                                else "Backend connection closed. This does not establish a physical machine stop."
                            )
                    else:
                        self.catalog = [
                            row
                            for row in result.get("operations", [])
                            if isinstance(row, dict)
                            and all(isinstance(row.get(key), str) for key in ("id", "label", "group", "consequence"))
                        ]
                        self.catalog_page = 0
                        self.catalog_note.text = f"{len(self.catalog)} declared backend operations · {result.get('profile_id', 'profile unknown')}. Catalog availability does not establish execution qualification."
                        self.page(0)
                self._controls()
                self.refresh()

            Clock.schedule_once(finish, 0)

        future.add_done_callback(received)

    def request_stop(self, action):
        if action in ("feed_hold", "software_abort"):
            self._request_realtime(action)

    def can_resume(self):
        from carveracontroller.machine.desktop_control_owner import reported_state

        owner = getattr(self.workspace, "control_owner", None)
        if self.client is None or owner is None or self.closed or self.stopping or self.busy:
            return False
        state = self.client.snapshot()
        snapshot = state.get("last_machine_snapshot", {})
        return (
            owner.matches(self.client.session_id, state)
            and reported_state(state) == "Hold"
            and snapshot.get("unknown_outcome") is False
            and snapshot.get("transfer_active") is False
            and "cycle_resume" not in self.control_pending
        )

    def request_resume(self):
        if not self.can_resume():
            self.control_note.text = "Resume withheld: the selected backend requires a fresh Hold report and no unresolved command or transfer. No request was submitted."
            return
        self._request_realtime("cycle_resume")

    def _request_realtime(self, action):
        if (
            self.closed
            or self.stopping
            or self.client is None
            or action not in ("feed_hold", "software_abort", "cycle_resume")
            or action in self.control_pending
        ):
            return
        client, generation = self.client, self.generation
        state = client.snapshot()
        observation = describe_backend(state)
        if (
            not state["ready"]
            or not state["running"]
            or observation.connected is not True
            or observation.connection_id is None
        ):
            self.control_note.text = "A current backend connection is required. No request was submitted."
            return
        identity = observation.connection_id
        self.control_pending.add(action)
        self.control_note.text = (
            "Submitting a backend resume request…" if action == "cycle_resume" else "Submitting a backend stop request…"
        )
        self._controls(state)
        try:
            future = client.submit("realtime", {"action": action})
        except Exception:
            self.control_pending.discard(action)
            self.control_note.text = (
                "The backend did not accept this resume request. It was not retried; motion completion is unconfirmed."
                if action == "cycle_resume"
                else "The backend did not accept this stop request. It was not retried; no physical stop is confirmed."
            )
            self._controls()
            return

        def received(future):
            record = {
                "action": action,
                "backend_session_id": client.session_id,
                "connection_id": identity,
                "outcome": "backend_response_unknown",
            }
            try:
                response = future.result()
                record.update(
                    request_id=response.envelope["id"],
                    request_sha256=response.request_sha256,
                    response_sha256=response.response_sha256,
                )
                result = response.envelope.get("result", {})
                if (
                    response.envelope.get("ok") is True
                    and result.get("action") == action
                    and result.get("connection_id") == identity
                    and result.get("outcome") == "sent_unacknowledged"
                    and result.get("motion_completed") is False
                ):
                    record["outcome"] = "sent_unacknowledged"
                elif response.envelope.get("ok") is False:
                    record["outcome"] = (
                        "unknown_outcome" if response.envelope.get("error") == "unknown_outcome" else "backend_refused"
                    )
            except Exception as error:
                record["request_id"] = getattr(error, "request_id", None)
                record["submission"] = getattr(error, "submission", "backend_response_unknown")
            with self._owner_lock:
                self.control_receipts.append(record)

            def finish(_dt):
                if self.closed or generation != self.generation or self.client is not client:
                    return
                self.control_pending.discard(action)
                title = (
                    "Feed hold"
                    if action == "feed_hold"
                    else "Software abort"
                    if action == "software_abort"
                    else "Resume motion"
                )
                self.control_note.text = (
                    f"{title} sent without acknowledgment. "
                    + (
                        "Motion completion is unconfirmed; inspect current machine reports."
                        if action == "cycle_resume"
                        else "Physical stop is unconfirmed; inspect current machine reports."
                    )
                    if record["outcome"] == "sent_unacknowledged"
                    else f"{title} outcome unresolved or refused. The request was not retried; "
                    + (
                        "motion completion is unconfirmed."
                        if action == "cycle_resume"
                        else "physical stop is unconfirmed."
                    )
                )
                if describe_backend(client.snapshot()).connection_id != identity:
                    self.control_note.text += " This receipt belongs to the prior connection."
                self._controls()

            Clock.schedule_once(finish, 0)

        future.add_done_callback(received)

    def refresh_if_visible(self):
        owner = getattr(self.workspace, "control_owner", None)
        if (owner is not None and owner.backend_selected) or (
            self.workspace.active_section == "Settings" and self.workspace.machine_tasks.active == "Backend"
        ):
            self.refresh()

    def refresh(self):
        if self.closed or self.client is None:
            return
        state = self.client.snapshot()
        self._controls(state)
        age = state["last_response_age_s"]
        self.age_note.text = (
            "Last private response age unknown"
            if age is None
            else f"Last private response {age:.2f}s ago · {state['pending_requests']} pending"
        )
        if not state["ready"] and not self.busy:
            self.heading.text = "Local backend · unavailable"
        observation = describe_backend(state)
        self.status.text = observation.summary
        self.telemetry.text = observation.telemetry
        visible = (
            getattr(self.workspace, "active_section", None) == "Settings"
            and getattr(getattr(self.workspace, "machine_tasks", None), "active", None) == "Backend"
        )
        owner = getattr(self.workspace, "control_owner", None)
        visible = visible or (owner is not None and owner.backend_selected)
        if (
            visible
            and self.monitoring
            and not self.busy
            and not self.stopping
            and state["ready"]
            and state["running"]
            and time.monotonic() >= self.next_poll_at
        ):
            self.next_poll_at = time.monotonic() + 0.5
            self.request("snapshot")

    def page(self, delta):
        maximum = max(0, (len(self.catalog) - 1) // 8)
        self.catalog_page = max(0, min(maximum, self.catalog_page + delta))
        rows = self.catalog[self.catalog_page * 8 : (self.catalog_page + 1) * 8]
        self.catalog_rows.text = "\n".join(f"{row['label']} · {row['group']} / {row['consequence']}" for row in rows)
        self.previous.disabled = self.catalog_page == 0
        self.next.disabled = self.catalog_page == maximum

    def stop(self):
        if self.closed or self.client is None or self.stopping:
            return
        client = self.client
        self.generation += 1
        generation = self.generation
        self.busy = self.stopping = True
        self.monitoring = False
        self.heading.text = "Local backend · stopping"
        self.note.text = "Closing this private child. This is not a physical machine stop."
        self.stop_action.disabled = True
        self.snapshot_action.disabled = self.catalog_action.disabled = True
        self._controls()

        def run():
            error = False
            try:
                client.close()
            except Exception:
                error = True

            def finish(_dt):
                if self.closed or generation != self.generation or self.client is not client:
                    return
                self.busy = self.stopping = False
                if error:
                    self.heading.text = "Local backend · shutdown pending"
                    self.note.text = (
                        "This session could not finish shutdown. Its ownership is retained; no replacement was started."
                    )
                else:
                    self.client = None
                    self.heading.text = "Local backend · stopped"
                    self.note.text = "Private child stopped. The live controller connection is separate."
                self._controls()

            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, name="desktop-backend-stop", daemon=True).start()

    def dispose(self):
        with self._owner_lock:
            self.closed = True
            self.generation += 1
            client = self.client
        if client is not None and not self.stopping:
            threading.Thread(target=client.close, name="desktop-backend-dispose", daemon=True).start()
