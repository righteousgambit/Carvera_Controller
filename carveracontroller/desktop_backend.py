"""Actual private backend inspection, separate from the live GUI controller."""

import threading

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, Surface
from carveracontroller.headless.client import SupervisorClient


class BackendPanel(Surface):
    def __init__(self, workspace, client_factory=SupervisorClient, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace, self.client_factory = workspace, client_factory
        self.client = None
        self.closed = self.busy = self.stopping = False
        self.generation = self.catalog_page = 0
        self.catalog = []
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
        for action in (self.start_action, self.snapshot_action, self.catalog_action, self.stop_action):
            self.actions.add_widget(action)
        self.add_widget(self.actions)
        self.status = flowing_text("No backend observations yet.", 52)
        self.add_widget(self.status)
        self.age_note = flowing_text("No private response observed.", 28)
        self.add_widget(self.age_note)
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

    def start(self):
        if self.closed or self.busy or self.client is not None:
            return
        profile = self.workspace.selected_machine_profile or {}
        host, port = profile.get("host") or "127.0.0.1", profile.get("port", 2222)
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
        if self.closed or self.busy or self.client is None or method not in ("snapshot", "catalog"):
            return
        client, generation = self.client, self.generation
        self.busy = True
        self.note.text = "Waiting for the private backend…"
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
                    self.note.text = error or "The backend refused this observation request."
                    self.note.color = AMBER
                else:
                    result = response.envelope["result"]
                    elapsed = "unknown" if response.elapsed_ms is None else f"{response.elapsed_ms:.2f} ms"
                    self.note.text = f"Private backend response: {elapsed}. This is local IPC time, not CNC acknowledgment or physical response."
                    self.note.color = MUTED
                    if method == "snapshot":
                        connected = result.get("connected") is True
                        self.status.text = (
                            f"Reported connection: {'connected' if connected else 'disconnected'}\n"
                            f"Unresolved command outcome: {'reported' if result['unknown_outcome'] else 'none reported'}\n"
                            f"Transfer: {'reported active' if result['transfer_active'] else 'none reported active'}"
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

    def refresh_if_visible(self):
        if self.workspace.active_section == "Settings" and self.workspace.machine_tasks.active == "Backend":
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
        self.heading.text = "Local backend · stopping"
        self.note.text = "Closing this private child. This is not a physical machine stop."
        self.stop_action.disabled = True
        self.snapshot_action.disabled = self.catalog_action.disabled = True

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
