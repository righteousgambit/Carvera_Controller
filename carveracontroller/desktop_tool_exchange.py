"""Library-to-fixed-rack reviewed exchange through the selected private child."""

import copy
import hashlib
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_backend_transactions import exchange_pending, require_idle_transaction
from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface
from carveracontroller.desktop_planning import planning_popup
from carveracontroller.headless.job_identity import reported_identity
from carveracontroller.headless.probe_settings_receipts import ipc_record
from carveracontroller.headless.tool_exchange import ToolExchangeReview
from carveracontroller.machine.desktop_control_owner import reported_state
from carveracontroller.machine.probe_settings_workflow import append_journal, canonical, load_journal


class ToolExchangePanel(Surface):
    def __init__(self, workspace, storage_root=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.root_path = Path(storage_root or Path.home() / ".carvera" / "tool-exchanges")
        self.closed = self.busy = False
        self.identity = self.review = self.popup = None
        self.latest_record = self.journal_path = None
        self.observation_review = self.acknowledged_at = None
        self.operation_binding = None
        self.bank_handoff = None
        self.signature = None
        self.add_widget(flowing_text("Reviewed rack exchange", 28))
        self.add_widget(
            flowing_text(
                "Choose a loaded preview cutter, then review its physical T1–T6 rack exchange. The library describes the intended cutter; it does not identify the rack contents.",
                58,
            )
        )
        self.target = Choice(text="Choose declared rack tool", values=())
        self.add_widget(self.target)
        self.summary = flowing_text("No declared preview cutters in the fixed rack.", 58)
        self.add_widget(self.summary)
        self.preview_action = Action("Use preview tools", self.clear_bank, disabled=True)
        self.add_widget(self.preview_action)
        actions = AdaptiveGrid(max_cols=2, min_width=160, row_height=36, spacing=dp(6))
        self.identity_action = Action("Read model & firmware", self.read_identity)
        self.review_action = Action("Review rack exchange", self.review_exchange, disabled=True)
        self.receipt_action = Action("Export latest receipt…", self.export_receipt, disabled=True)
        self.history_action = Action("Inspect retained attempts", self.inspect_attempts)
        for action in (self.identity_action, self.review_action, self.receipt_action, self.history_action):
            actions.add_widget(action)
        self.add_widget(actions)
        self.next_measurement_action = Action("Continue to measurement", self.open_measurement, disabled=True)
        self.add_widget(self.next_measurement_action)
        self.note = flowing_text(
            "Select the private backend connection to request an exchange. Preview assignments remain local.", 58
        )
        self.add_widget(self.note)
        self.refresh()

    def _profile(self):
        return copy.deepcopy(self.workspace.selected_machine_profile or {})

    def use_bank(self, handoff):
        if self.closed or self.busy or self.operation_binding is not None or self.observation_review is not None:
            raise ValueError("Finish or inspect the pending exchange before changing bank context")
        handoff.resolve()
        self.review = None
        if self.popup:
            self.popup.dismiss()
        self.bank_handoff, self.signature = handoff, None
        self.refresh()

    def clear_bank(self):
        if self.closed or self.busy or self.operation_binding is not None or self.observation_review is not None:
            return
        self.bank_handoff = self.review = self.signature = None
        if self.popup:
            self.popup.dismiss()
        self.refresh()

    def open_measurement(self):
        try:
            self._binding()
            if self.bank_handoff is None:
                return
            handoff = self.bank_handoff.after_exchange(self)
            self.workspace.open_tool_measurement(handoff)
        except ValueError as error:
            self.note.text = str(error)

    def _binding(self, *, allow_pending=False):
        require_idle_transaction(self.workspace, "exchange")
        if not allow_pending and exchange_pending(self.workspace):
            raise ValueError("This connection's exchange is pending or unresolved; inspect the retained attempt first")
        backend = getattr(self.workspace, "backend_panel", None)
        client = backend.client if backend else None
        if (
            self.closed
            or not backend
            or backend.closed
            or backend.stopping
            or client is None
            or backend.endpoint_profile != backend._profile_key()
        ):
            raise ValueError("Select the connected private backend as the workbench owner")
        state = client.snapshot()
        if not self.workspace.control_owner.matches(client.session_id, state):
            raise ValueError("The selected backend connection is unavailable or replaced")
        machine = state["last_machine_snapshot"]
        if machine.get("unknown_outcome") is not False or machine.get("transfer_active") is not False:
            raise ValueError("An unresolved backend outcome or transfer blocks this workflow")
        return client, state, state["last_machine_snapshot"]["connection_id"]

    def _context(self):
        if self.bank_handoff is not None:
            bank = self.bank_handoff.resolve()
            return {
                "profile": self._profile(),
                "target": bank["controller_tool"],
                "declared_tool_mm": bank["declared_tool_mm"],
                "toolset": copy.deepcopy(getattr(self.workspace, "loaded_toolset", None)),
                "setup": copy.deepcopy(self.workspace.readiness.snapshot()[1]),
                "bank_handoff": bank,
            }
        try:
            target = int(self.target.text.split(" · ", 1)[0][1:])
        except (ValueError, IndexError):
            raise ValueError("Choose a declared preview tool in T1–T6") from None
        definition = self.workspace.machine.gcode_viewer.library_tool_table_mm.get(target)
        if definition is None or type(target) is not int or not 1 <= target <= 6:
            raise ValueError("Selected preview tool is no longer loaded")
        tool = asdict(definition)
        tool["tool_type"] = definition.tool_type.value
        return {
            "profile": self._profile(),
            "target": target,
            "declared_tool_mm": tool,
            "toolset": copy.deepcopy(getattr(self.workspace, "loaded_toolset", None)),
            "setup": copy.deepcopy(self.workspace.readiness.snapshot()[1]),
        }

    def _start(self, message):
        if self.closed or self.busy:
            return False
        self.busy = True
        self.note.text = message
        self.refresh()
        return True

    def _background(self, work, finish):
        def worker():
            value, error = None, None
            try:
                value = work()
            except Exception as failure:
                error = str(failure)

            def deliver(_dt):
                self.busy = False
                if not self.closed:
                    finish(value, error)
                    self.refresh()

            Clock.schedule_once(deliver, 0)

        threading.Thread(target=worker, name="desktop-tool-exchange", daemon=True).start()

    def _record(self, phase, client, connection, context):
        return {
            "phase": phase,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "session_id": client.session_id,
            "connection_id": connection,
            "context": context,
            "physical_tool_identity_verified": False,
            "tool_length_verified": False,
            "clearance_verified": False,
            "motion_completed": False,
        }

    def read_identity(self):
        if self.closed or self.busy or self.observation_review is not None:
            return
        try:
            client, _state, connection = self._binding()
        except ValueError as failure:
            self.note.text = str(failure)
            return
        profile = self._profile()
        self.identity = self.review = None
        path = self.root_path / (uuid4().hex + ".jsonl")
        if not self._start("Reading original model and firmware reports…"):
            return

        def read():
            record = self._record("identity_pending", client, connection, {"profile": profile})
            record["responses"] = []
            append_journal(path, record, new=True)
            try:
                identity = {"session_id": client.session_id, "connection_id": connection}
                for query in ("model", "version"):
                    if self.closed:
                        raise ValueError("Exchange panel retired during identity read")
                    response = client.submit(
                        "operation", {"operation": "observe.query", "parameters": {"query": query}}
                    ).result()
                    record["responses"].append(ipc_record(response))
                    if response.envelope.get("ok") is not True:
                        raise ValueError("Backend refused identity discovery")
                    identity[query] = reported_identity(response.envelope["result"], query, connection)
                record["identity"] = identity
                record["phase"] = "identity_reported"
            except Exception as failure:
                record["phase"], record["error"] = "identity_unresolved", str(failure)
            try:
                record["result_durability"] = "retained"
                append_journal(path, record)
            except Exception:
                record["result_durability"] = "unconfirmed"
                raise
            finally:
                self.latest_record, self.journal_path = record, path
            return record

        def finish(record, error):
            if error or record["phase"] != "identity_reported":
                self.note.text = error or record.get("error", "Identity read unresolved")
                return
            try:
                current, _state, current_connection = self._binding()
                if current is not client or current_connection != connection or self._profile() != profile:
                    raise ValueError("Machine or connection changed during identity read")
                self.identity = record["identity"]
                self.note.text = f"Reported {self.identity['model']['reported_model']} / {self.identity['version']['reported_version']}. Original reports retained; firmware is not authenticated."
            except ValueError as failure:
                self.note.text = str(failure) + ". Retained as historical; read again."

        self._background(read, finish)

    def _warm_state(self, client, callback):
        context, identity = self._context(), copy.deepcopy(self.identity)
        if not self._start("Reading current private state before admitting this review…"):
            return

        def read():
            if client.submit("snapshot").result().envelope.get("ok") is not True:
                raise ValueError("Current private state unavailable")

        def finish(_value, error):
            if error:
                self.note.text = error + ". No exchange request submitted."
                return
            try:
                current, _state, _connection = self._binding()
                if current is not client or self._context() != context or self.identity != identity:
                    raise ValueError("Machine, selected cutter or identity changed during the state read")
                callback()
            except ValueError as failure:
                self.note.text = str(failure)

        self._background(read, finish)

    def review_exchange(self, *, _warmed=False):
        if self.closed or self.busy or self.observation_review is not None:
            return
        try:
            client, state, connection = self._binding()
            if not _warmed:
                self._warm_state(client, lambda: self.review_exchange(_warmed=True))
                return
            context = self._context()
            review = ToolExchangeReview.create(
                client.session_id, connection, context, self.identity or {}, state, time.monotonic()
            )
        except ValueError as failure:
            self.note.text = str(failure)
            return
        self.review = review
        body = Surface(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        tool = context["declared_tool_mm"]
        if self.bank_handoff is not None:
            body.add_widget(flowing_text(self.bank_handoff.label, 62))
        body.add_widget(
            flowing_text(
                f"{context['profile'].get('name', 'Selected C1')} · T{review.target}\nDeclared cutter: {tool['description'] or tool['tool_type']}\nRack command: {review.plan['commands'][0]}",
                80,
            )
        )
        body.add_widget(
            flowing_text(
                "This requests a physical rack exchange. Confirm the selected pocket contains the intended assembly and the machine is clear for the exchange. The controller manages the ATC sequence. This review expires in 30 seconds; changed setup, tooling or reported position requires another review.",
                116,
            )
        )
        body.add_widget(
            flowing_text(
                "The result retains acknowledgment separately from later reported Idle/tool status. Neither proves cutter identity, measured length or collision clearance. No automatic repeat or recovery motion is performed.",
                84,
            )
        )
        self.exchange_action = Action(f"Request reviewed exchange · T{review.target}", lambda: self.exchange(review))
        body.add_widget(self.exchange_action)
        body.add_widget(Action("Return without exchanging", lambda: self.popup.dismiss()))
        if self.popup:
            self.popup.dismiss()
        self.popup = planning_popup("Review physical tool exchange", body)
        self.popup.open()
        self.refresh()

    def _admit(self, review, client):
        current, state, connection = self._binding(allow_pending=True)
        if current is not client or self.review is not review:
            raise ValueError("Tool review or private child changed; review again")
        return review.authorize(client.session_id, connection, self._context(), state, time.monotonic())

    def exchange(self, review, *, _warmed=False):
        if self.closed or self.busy or self.observation_review is not None:
            return
        try:
            client, _state, connection = self._binding()
            if reported_state(_state) is None and not _warmed:
                self._warm_state(client, lambda: self.exchange(review, _warmed=True))
                return
            self._admit(review, client)
            context = self._context()
        except ValueError as failure:
            self.note.text = str(failure)
            return
        identity = copy.deepcopy(self.identity)
        handoff = self.bank_handoff
        identity_path = self.journal_path
        path = self.root_path / (uuid4().hex + ".jsonl")
        if not self._start("Retaining reviewed intent before rechecking the exchange request…"):
            return
        self.operation_binding = (client.session_id, connection)
        self.observation_review = self.acknowledged_at = None

        def dispatch():
            submitted = saved = False
            record = self._record("exchange_pending", client, connection, context)
            record["review"] = asdict(review)
            record["identity"] = identity
            record["identity_receipt_file"] = str(identity_path)
            try:
                if load_journal(identity_path)[-1]["record"].get("identity") != identity:
                    raise ValueError("Retained identity receipt changed before exchange intent")
                record["identity_receipt_sha256"] = hashlib.sha256(identity_path.read_bytes()).hexdigest()
                append_journal(path, record, new=True)
                saved = True
                if client.submit("snapshot").result().envelope.get("ok") is not True:
                    raise ValueError("Current private state unavailable")
                persisted = handoff.verify_saved() if handoff is not None else None
                ready, abandoned, lock, admitted = threading.Event(), threading.Event(), threading.Lock(), []

                def preflight(_dt):
                    with lock:
                        try:
                            if abandoned.is_set():
                                return
                            if handoff is not None:
                                handoff.require_fresh(persisted)
                            admitted.append(client.submit("operation", self._admit(review, client)))
                        except Exception as failure:
                            admitted.append(failure)
                        finally:
                            ready.set()

                Clock.schedule_once(preflight, 0)
                if not ready.wait(5):
                    with lock:
                        if not ready.is_set():
                            abandoned.set()
                if abandoned.is_set() or len(admitted) != 1:
                    raise ValueError("Exchange admission expired before submission")
                if isinstance(admitted[0], Exception):
                    raise admitted[0]
                submitted = True
                response = admitted[0].result()
                record["response"] = ipc_record(response)
                review.accept(response)
                record["phase"] = "exchange_acknowledged"
            except Exception as failure:
                record["phase"] = "exchange_unresolved" if submitted else "not_submitted"
                record["error"] = str(failure)
            record["submitted"] = submitted
            try:
                if not saved:
                    raise ValueError("Intent durability unavailable; no exchange submitted")
                record["result_durability"] = "retained"
                append_journal(path, record)
            except Exception:
                record["result_durability"] = "unconfirmed"
                raise
            finally:
                self.latest_record, self.journal_path = record, path
            return record

        def finish(record, error):
            self.review = None
            if self.popup:
                self.popup.dismiss()
            if error or record["phase"] != "exchange_acknowledged":
                if self.latest_record is not None and self.latest_record.get("submitted") is False:
                    self.operation_binding = None
                self.note.text = (
                    error or record.get("error", "Exchange unresolved")
                ) + ". Inspect retained receipts; no automatic retry or recovery."
            else:
                self.observation_review = review
                self.acknowledged_at = record["response"]["received_at_s"]
                self.note.text = f"T{review.target} exchange acknowledged. Awaiting a later Idle/tool report; physical identity, length and clearance remain unverified."

        self._background(dispatch, finish)

    def _observe(self):
        if self.busy or self.observation_review is None:
            return
        review = self.observation_review
        owner = self.workspace.control_owner.binding
        if owner is None or (owner.session_id, owner.connection_id) != (review.session_id, review.connection_id):
            self.observation_review = None
            self.note.text = "Prior exchange receipt remains historical and unconfirmed on its original connection. Read identity before reviewing this connection."
            return
        try:
            client, state, connection = self._binding(allow_pending=True)
            if (client.session_id, connection) != (review.session_id, review.connection_id):
                return
            if self._profile() != self.latest_record["context"]["profile"]:
                return
            if not review.target_reported(state, time.monotonic(), self.acknowledged_at):
                return
        except ValueError:
            return
        # Stop following this transition exactly once. A retained result is
        # historical evidence, never an enduring claim about current tooling.
        self.observation_review = None
        record = copy.deepcopy(self.latest_record)
        path = self.journal_path
        record["phase"] = "target_tool_reported"
        record["observation"] = {"state": state, "observed_at_s": time.monotonic()}
        record["observed_at"] = datetime.now(timezone.utc).isoformat()
        self.busy = True

        def save():
            try:
                record["result_durability"] = "retained"
                append_journal(path, record)
            except Exception:
                record["result_durability"] = "unconfirmed"
                raise
            finally:
                self.latest_record = record
            return record

        def finish(_record, error):
            if not error:
                self.operation_binding = None
            self.note.text = (
                error
                or f"Later status reported Idle with T{review.target}. Receipt retained; physical cutter identity, measured length and clearance remain unverified."
            )

        self._background(save, finish)

    def export_receipt(self):
        if self.closed or self.busy or self.latest_record is None:
            return
        record = copy.deepcopy(self.latest_record)

        def selected(path):
            if not path or not self._start("Saving and reading back the receipt export…"):
                return

            def save():
                raw = canonical(record).encode() + b"\n"
                with Path(path).open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if Path(path).read_bytes() != raw:
                    raise ValueError("Export readback differs")
                return str(path)

            self._background(
                save,
                lambda result, error: setattr(self.note, "text", error or "Receipt retained and read back: " + result),
            )

        self.workspace.choose_profile_file(selected, save=True, extension=".json", title="Export tool exchange receipt")

    def inspect_attempts(self):
        if not self._start("Reading retained exchange attempts; no command will be replayed…"):
            return

        def read():
            paths = sorted(self.root_path.glob("*.jsonl"))
            if len(paths) > 512:
                raise ValueError("More than 512 retained attempts; inspect the directory directly")
            rows = []
            for path in paths[-12:]:
                try:
                    record = load_journal(path)[-1]["record"]
                    phase = record.get("phase")
                    phase = phase if isinstance(phase, str) else "unresolved"
                except (ValueError, OSError, IndexError):
                    phase = "unresolved"
                rows.append(path.name + " · " + phase)
            return "\n".join(rows) or "No retained attempts."

        self._background(
            read,
            lambda result, error: setattr(
                self.note, "text", error or result + "\nHistorical only; no replay or reconciliation was performed."
            ),
        )

    def refresh(self):
        if self.closed:
            return
        table = self.workspace.machine.gcode_viewer.library_tool_table_mm
        bank_error = None
        bank = None
        if self.bank_handoff is not None:
            try:
                bank = self.bank_handoff.resolve()
            except ValueError as error:
                bank_error = str(error)
        signature = tuple(
            (n, t.description, t.tool_type.value, t.diameter)
            for n, t in sorted(table.items())
            if type(n) is int and 1 <= n <= 6
        )
        if self.bank_handoff is not None:
            tool = bank["declared_tool_mm"] if bank else None
            signature = (
                ((bank["controller_tool"], tool["description"], tool["tool_type"], tool["diameter"]),) if tool else ()
            )
        if signature != self.signature:
            self.signature = signature
            self.target.values = tuple(f"T{n} · {name or kind}" for n, name, kind, _diameter in signature)
            if self.target.text not in self.target.values:
                self.target.text = self.target.values[0] if self.target.values else "Choose declared rack tool"
            self.summary.text = (
                "\n".join(
                    f"T{n} · {name or kind} · Ø{diameter:g} mm"
                    if diameter is not None
                    else f"T{n} · {name or kind} · diameter unknown"
                    for n, name, kind, diameter in signature
                )
                or "No declared preview cutters in the fixed rack. Load a library cutter or ATC toolset preview first."
            )
        self.target.disabled = self.bank_handoff is not None
        self.preview_action.disabled = self.bank_handoff is None or self.busy or self.operation_binding is not None
        if self.bank_handoff is not None:
            self.summary.text = bank_error or self.bank_handoff.label
        available = True
        try:
            self._binding()
        except ValueError:
            available = False
        awaiting = exchange_pending(self.workspace)
        self.identity_action.disabled = self.busy or awaiting or not available
        self.review_action.disabled = (
            self.busy or awaiting or not available or self.identity is None or not signature or bool(bank_error)
        )
        self.receipt_action.disabled = self.busy or self.latest_record is None
        self.history_action.disabled = self.busy
        if self.review is not None and hasattr(self, "exchange_action"):
            try:
                client, _state, _connection = self._binding()
                self._admit(self.review, client)
                admitted = True
            except ValueError:
                admitted = False
            self.exchange_action.disabled = self.busy or not admitted
        self._observe()
        try:
            if self.busy or self.bank_handoff is None:
                raise ValueError("No settled bank exchange")
            self._binding()
            self.bank_handoff.after_exchange(self)
            next_available = True
        except ValueError:
            next_available = False
        self.next_measurement_action.disabled = not next_available

    def dispose(self):
        self.closed = True
        self.review = self.observation_review = None
        if self.popup:
            self.popup.dismiss()
