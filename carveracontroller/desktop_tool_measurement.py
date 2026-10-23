"""Reviewed setter measurement with retained asynchronous output and explicit custody."""

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

from carveracontroller.desktop_backend_transactions import measurement_pending, require_idle_transaction
from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface
from carveracontroller.desktop_planning import planning_popup
from carveracontroller.headless.client import Response
from carveracontroller.headless.job_identity import reported_identity
from carveracontroller.headless.probe_settings_receipts import ipc_record
from carveracontroller.headless.tool_measurement import ToolMeasurementReview, projection
from carveracontroller.machine.backend_live_report import finite
from carveracontroller.machine.desktop_control_owner import reported_state
from carveracontroller.machine.probe_settings_workflow import append_journal, canonical, load_journal
from carveracontroller.machine.tool_history import TloReport


class ToolMeasurementPanel(Surface):
    def __init__(self, workspace, storage_root=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.root_path = Path(storage_root or Path.home() / ".carvera" / "tool-measurements")
        self.closed = self.busy = False
        self.identity = self.review = self.popup = None
        self.latest_record = self.journal_path = None
        self.observation_review = self.acknowledged_at = None
        self.operation_binding = None
        self.bank_handoff = None
        self.atc_offset_record = self.atc_offset_path = self.atc_offset_observation = None
        self.signature = None
        self.add_widget(flowing_text("Measure the installed tool", 28))
        self.add_widget(
            flowing_text(
                "Review calibration at the fixed setter for the reported current tool. Confirm its installed kind and clear travel. Library and assembly selections describe intent; they do not identify the physical cutter.",
                58,
            )
        )
        self.target = Choice(text="Choose current reported tool", values=())
        self.add_widget(self.target)
        self.kind = Choice(
            text="Confirm installed tool kind",
            values=("Confirm installed tool kind", "Installed cutter", "Installed probe"),
        )
        self.repeats = Choice(text="3", values=("1", "2", "3", "4", "5"))
        self.add_widget(self.kind)
        self.add_widget(flowing_text("Setter repetitions · one pass may produce no sample block", 34))
        self.add_widget(self.repeats)
        self.summary = flowing_text("Choose the same T number as the fresh report.", 58)
        self.add_widget(self.summary)
        self.preview_action = Action("Use preview tools", self.clear_bank, disabled=True)
        self.add_widget(self.preview_action)
        actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        self.identity_action = Action("Read model & firmware", self.read_identity)
        self.review_action = Action("Review measurement", self.review_measurement, disabled=True)
        self.receipt_action = Action("Export latest receipt…", self.export_receipt, disabled=True)
        self.history_action = Action("Inspect retained attempts", self.inspect_attempts)
        self.capture_action = Action("Save samples to tool passport", self.capture_samples, disabled=True)
        for action in (self.identity_action, self.review_action, self.receipt_action, self.history_action):
            actions.add_widget(action)
        self.add_widget(actions)
        self.add_widget(self.capture_action)
        from carveracontroller.desktop_atc_offset import export_offset, read_offset

        offsets = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        self.atc_offset_action = Action("Read current ATC offset", lambda: read_offset(self), disabled=True)
        self.atc_offset_export = Action("Export ATC offset receipt…", lambda: export_offset(self), disabled=True)
        offsets.add_widget(self.atc_offset_action)
        offsets.add_widget(self.atc_offset_export)
        self.add_widget(offsets)
        self.atc_offset_summary = flowing_text("", 80)
        self.add_widget(self.atc_offset_summary)
        self.note = flowing_text(
            "Select the private backend connection to request a measurement. Preview assignments remain local.", 58
        )
        self.add_widget(self.note)
        self.refresh()

    def _profile(self):
        return copy.deepcopy(self.workspace.selected_machine_profile or {})

    def use_bank(self, handoff):
        if self.closed or self.busy or self.operation_binding is not None or self.observation_review is not None:
            raise ValueError("Finish or inspect the pending measurement before changing bank context")
        handoff.resolve()
        self.review = None
        if self.popup:
            self.popup.dismiss()
        self.bank_handoff, self.signature = handoff, None
        self.kind.text = "Confirm installed tool kind"
        self.refresh()

    def clear_bank(self):
        if self.closed or self.busy or self.operation_binding is not None or self.observation_review is not None:
            return
        self.bank_handoff = self.review = self.signature = None
        if self.popup:
            self.popup.dismiss()
        self.refresh()

    def _binding(self, *, allow_pending=False):
        require_idle_transaction(self.workspace, "measurement")
        if not allow_pending and measurement_pending(self.workspace):
            raise ValueError(
                "This connection's measurement is pending or unresolved; inspect the retained attempt first"
            )
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
        bank = self.bank_handoff.resolve() if self.bank_handoff is not None else None
        try:
            target = int(self.target.text.split(" · ", 1)[0][1:])
        except (ValueError, IndexError):
            raise ValueError("Choose the current reported T0–T6") from None
        definition = self.workspace.machine.gcode_viewer.library_tool_table_mm.get(target)
        if bank is not None:
            target = bank["controller_tool"]
        if type(target) is not int or not 0 <= target <= 6 or definition is None and target != 0 and bank is None:
            raise ValueError("Selected preview tool is no longer loaded")
        tool = asdict(definition) if definition else {"description": "Declared probe T0", "tool_type": "probe"}
        if definition:
            tool["tool_type"] = definition.tool_type.value
        comparison = getattr(self.workspace, "tool_comparison", None)
        custody = getattr(comparison, "custody", None)
        store = self.workspace.machine.tool_custody
        assembly = store.assembly(custody.selected_id) if custody and custody.selected_id else None
        context = {
            "profile": self._profile(),
            "target": target,
            "declared_tool_mm": tool,
            "toolset": copy.deepcopy(getattr(self.workspace, "loaded_toolset", None)),
            "setup": copy.deepcopy(self.workspace.readiness.snapshot()[1]),
            "assembly": copy.deepcopy(assembly),
            "custody_generation": store.generation,
            "custody_store_identity": id(store),
            "repeats": int(self.repeats.text),
            "tool_kind": "probe" if self.kind.text == "Installed probe" else "cutter",
            "installed_kind_asserted": self.kind.text in ("Installed probe", "Installed cutter"),
        }
        if bank is not None:
            context.update(declared_tool_mm=bank["declared_tool_mm"], assembly=bank["assembly"], bank_handoff=bank)
        return context

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

        threading.Thread(target=worker, name="desktop-tool-measurement", daemon=True).start()

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
            "command_attribution_verified": False,
            "endpoint": f"{client.host}:{client.port}",
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
                        raise ValueError("Measurement panel retired during identity read")
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
                self.note.text = error + ". No measurement request submitted."
                return
            try:
                current, _state, _connection = self._binding()
                if current is not client or self._context() != context or self.identity != identity:
                    raise ValueError("Machine, selected cutter or identity changed during the state read")
                callback()
            except ValueError as failure:
                self.note.text = str(failure)

        self._background(read, finish)

    def review_measurement(self, *, _warmed=False):
        if self.closed or self.busy or self.observation_review is not None:
            return
        try:
            client, state, connection = self._binding()
            if not _warmed:
                self._warm_state(client, lambda: self.review_measurement(_warmed=True))
                return
            context = self._context()
            review = ToolMeasurementReview.create(
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
                f"{context['profile'].get('name', 'Selected C1')} · current T{review.target}\nDeclared tool: {tool['description'] or tool['tool_type']}\n{review.repeats} setter passes · {review.plan['commands'][0]}",
                80,
            )
        )
        body.add_widget(
            flowing_text(
                "This requests physical setter travel and updates the firmware's tool offset. Your installed-kind assertion must match the current reported T number. This review expires in 30 seconds; changed setup, tooling or reported position requires another review.",
                116,
            )
        )
        body.add_widget(
            flowing_text(
                "Acknowledgement, later output and later Idle status are retained separately. Normalized late text cannot be imported as byte-qualified millimetre calibration. The printed Using value is not proof of the applied offset. No automatic repeat is performed.",
                84,
            )
        )
        self.measurement_action = Action(
            f"Measure current T{review.target} · {review.repeats} passes", lambda: self.measurement(review)
        )
        body.add_widget(self.measurement_action)
        body.add_widget(Action("Return without measuring", lambda: self.popup.dismiss()))
        if self.popup:
            self.popup.dismiss()
        self.popup = planning_popup("Review physical tool measurement", body)
        self.popup.open()
        self.refresh()

    def _admit(self, review, client):
        current, state, connection = self._binding(allow_pending=True)
        if current is not client or self.review is not review:
            raise ValueError("Tool review or private child changed; review again")
        return review.authorize(client.session_id, connection, self._context(), state, time.monotonic())

    def measurement(self, review, *, _warmed=False):
        if self.closed or self.busy or self.observation_review is not None:
            return
        try:
            client, _state, connection = self._binding()
            if reported_state(_state) is None and not _warmed:
                self._warm_state(client, lambda: self.measurement(review, _warmed=True))
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
        if not self._start("Retaining reviewed intent before rechecking the measurement request…"):
            return
        self.operation_binding = (client.session_id, connection)
        self.observation_review = self.acknowledged_at = None

        def dispatch():
            submitted = saved = False
            record = self._record("measurement_pending", client, connection, context)
            record["review"] = asdict(review)
            record["identity"] = identity
            record["identity_receipt_file"] = str(identity_path)
            record["output_cursor"] = client.text_receipts()["latest_sequence"]
            record["received_output"] = []
            record["activity_observed"] = False
            try:
                if load_journal(identity_path)[-1]["record"].get("identity") != identity:
                    raise ValueError("Retained identity receipt changed before measurement intent")
                record["identity_receipt_sha256"] = hashlib.sha256(identity_path.read_bytes()).hexdigest()
                append_journal(path, record, new=True)
                saved = True
                persisted = handoff.verify_saved() if handoff is not None else None
                if client.submit("snapshot").result().envelope.get("ok") is not True:
                    raise ValueError("Current private state unavailable")
                ready, abandoned, lock, admitted = threading.Event(), threading.Event(), threading.Lock(), []

                def preflight(_dt):
                    with lock:
                        try:
                            if abandoned.is_set():
                                return
                            if handoff is not None:
                                handoff.verify_unchanged(persisted)
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
                    raise ValueError("Measurement admission expired before submission")
                if isinstance(admitted[0], Exception):
                    raise admitted[0]
                submitted = True
                response = admitted[0].result()
                record["response"] = ipc_record(response)
                record["acknowledgement"] = review.accept(response, time.time())
                record["phase"] = "measurement_acknowledged"
            except Exception as failure:
                record["phase"] = "measurement_unresolved" if submitted else "not_submitted"
                record["error"] = str(failure)
            record["submitted"] = submitted
            try:
                if not saved:
                    raise ValueError("Intent durability unavailable; no measurement submitted")
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
            if error or record["phase"] != "measurement_acknowledged":
                if self.latest_record is not None and self.latest_record.get("submitted") is False:
                    self.operation_binding = None
                self.note.text = (
                    error or record.get("error", "Measurement unresolved")
                ) + ". Inspect retained receipts; no automatic retry or recovery."
            else:
                self.observation_review = review
                self.acknowledged_at = record["response"]["received_at_s"]
                self.note.text = f"M491 for T{review.target} acknowledged. Following late output and later Idle status. Offset application, physical identity and clearance remain unverified."

        self._background(dispatch, finish)

    def _observe(self):
        if self.busy or self.observation_review is None:
            return
        review = self.observation_review
        owner = self.workspace.control_owner.binding
        if owner is None or (owner.session_id, owner.connection_id) != (review.session_id, review.connection_id):
            self.observation_review = None
            self.note.text = "Prior measurement receipt remains historical and unconfirmed on its original connection. Read identity before reviewing this connection."
            return
        backend = self.workspace.backend_panel
        client = backend.client if backend else None
        if client is None or client.session_id != review.session_id:
            return
        if backend.closed or backend.stopping or self._profile() != self.latest_record["context"]["profile"]:
            self.observation_review = None
            self.note.text = "Measurement observation retired after a profile or backend change. Original receipts remain historical and unresolved."
            return
        record = copy.deepcopy(self.latest_record)
        path = self.journal_path
        try:
            cursor = record["output_cursor"]
            rows = review.normalized_output(client.text_receipts(cursor), cursor)
            if len(record["received_output"]) + len(rows) > 256:
                raise ValueError("Measurement output exceeded its bounded receipt budget")
            if rows:
                record["received_output"].extend(rows)
                record["output_cursor"] = rows[-1]["sequence"]
                lines = [r["text"] for r in record["received_output"]]
                if any(r["text_may_be_truncated"] for r in rows) or any(
                    line.lower().startswith(("error", "alarm", "halted")) for line in lines
                ):
                    raise ValueError("Late measurement output reports failure or may be truncated")
                if "-----------------------------------------------------------" in lines:
                    record["normalized_projection"] = projection(lines, review.repeats, time.time())
                record["normalized_output_is_qualified_calibration"] = False
            state = client.snapshot()
            snapshot = state.get("last_machine_snapshot") or {}
            status = snapshot.get("status") or {}
            age, cached = finite(snapshot.get("status_age_ms")), finite(state.get("last_machine_snapshot_age_s"))
            observed = time.monotonic() - cached - age / 1000 if cached is not None and age is not None else 0
            if observed > self.acknowledged_at and (
                status.get("is_playing") is True or status.get("state") in ("Run", "Home")
            ):
                record["activity_observed"] = True
            qualification = record.get("acknowledgement", {}).get("calibration")
            has_output = qualification is not None or record.get("normalized_projection") is not None
            after = max([self.acknowledged_at, *(r["received_at_s"] for r in record["received_output"])])
            finished = (has_output or record["activity_observed"]) and review.target_reported(
                state, time.monotonic(), after
            )
            changed = rows or record["activity_observed"] != self.latest_record["activity_observed"]
            if not finished and not changed:
                return
            record["phase"] = "later_idle_reported" if finished else "measurement_output_retained"
            if finished:
                record["observation"] = {"state": state, "observed_at_s": time.monotonic()}
        except ValueError as failure:
            record["phase"], record["error"] = "measurement_output_unresolved", str(failure)
            finished = False
            self.observation_review = None
        if finished:
            self.observation_review = None
        self.busy = True

        def retain():
            record["result_durability"] = "retained"
            append_journal(path, record)
            self.latest_record = record
            return record

        def retained(_value, error):
            if error:
                self.observation_review = None
                self.note.text = error + ". Output durability unconfirmed; inspect before any retry."
            elif finished:
                self.operation_binding = None
                self.note.text = "Later Idle/tool status retained. " + (
                    "Original command-window samples can be reviewed for import; applied TLO remains unknown."
                    if qualification
                    else "Late output is normalized, lacks original controller bytes and cannot be imported as qualified calibration. One-pass output may contain no samples."
                )
            elif record.get("error"):
                self.note.text = record["error"] + ". Retained output remains unresolved; no automatic retry."

        self._background(retain, retained)

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

        self.workspace.choose_profile_file(
            selected, save=True, extension=".json", title="Export tool measurement receipt"
        )

    def inspect_attempts(self):
        if not self._start("Reading retained measurement attempts; no command will be replayed…"):
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
            if type(n) is int and 0 <= n <= 6
        )
        if self.bank_handoff is not None:
            tool = bank["declared_tool_mm"] if bank else None
            signature = (
                ((bank["controller_tool"], tool["description"], tool["tool_type"], tool["diameter"]),) if tool else ()
            )
        if signature != self.signature:
            self.signature = signature
            self.target.values = tuple(f"T{n} · {name or kind}" for n, name, kind, _diameter in signature)
            if self.bank_handoff is None and not any(n == 0 for n, *_ in signature):
                self.target.values = ("T0 · Declared probe", *self.target.values)
            if self.target.text not in self.target.values and self.target.values:
                backend = getattr(self.workspace, "backend_panel", None)
                client = getattr(backend, "client", None)
                state = client.snapshot() if client else {}
                current = (state.get("last_machine_snapshot") or {}).get("status") or {}
                number = current.get("tool")
                self.target.text = (
                    next((v for v in self.target.values if v.startswith(f"T{int(number)} ·")), self.target.values[0])
                    if type(number) in (int, float) and finite(number) is not None
                    else self.target.values[0]
                )
            self.summary.text = (
                "\n".join(
                    f"T{n} · {name or kind} · Ø{diameter:g} mm"
                    if diameter is not None
                    else f"T{n} · {name or kind} · diameter unknown"
                    for n, name, kind, diameter in signature
                )
                or "No preview cutter loaded. T0 requires your installed-probe assertion; load a cutter profile to measure T1–T6."
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
        awaiting = measurement_pending(self.workspace)
        self.identity_action.disabled = self.busy or awaiting or not available
        self.review_action.disabled = (
            self.busy or awaiting or not available or self.identity is None or bool(bank_error)
        )
        self.receipt_action.disabled = self.busy or self.latest_record is None
        self.history_action.disabled = self.busy
        self.capture_action.disabled = (
            self.busy
            or self.latest_record is None
            or self.latest_record.get("phase") != "later_idle_reported"
            or self.latest_record.get("acknowledgement", {}).get("calibration") is None
            or self.latest_record.get("imported_receipt_id") is not None
        )
        if self.review is not None and hasattr(self, "measurement_action"):
            try:
                client, _state, _connection = self._binding()
                self._admit(self.review, client)
                admitted = True
            except ValueError:
                admitted = False
            self.measurement_action.disabled = self.busy or not admitted
        from carveracontroller.desktop_atc_offset import refresh_offset

        refresh_offset(self, available, awaiting)
        self._observe()

    def capture_samples(self):
        record = copy.deepcopy(self.latest_record)
        if self.closed or self.busy or record is None or record.get("phase") != "later_idle_reported":
            return
        qualified = record.get("acknowledgement", {}).get("calibration")
        if qualified is None or record.get("imported_receipt_id"):
            return
        store = self.workspace.machine.tool_custody
        if id(store) != record["context"]["custody_store_identity"]:
            self.note.text = "The tool passport store changed; retain this measurement as historical evidence."
            return
        if not self._start("Retaining byte-qualified samples as an unassigned receipt…"):
            return
        path = self.journal_path

        def capture():
            # No automatic assembly or logical-tool attribution. The passport
            # provides its existing explicit operator-attribution review.
            import base64

            source = record["response"]
            raw = base64.b64decode(source["original_ipc_bytes_base64"], validate=True)
            response = Response(
                source["envelope"],
                source["request_sha256"],
                source["response_sha256"],
                source["received_at_s"],
                source["elapsed_ms"],
                raw,
            )
            review = ToolMeasurementReview(**record["review"])
            accepted = review.accept(response, qualified["report"]["timestamp"])
            if accepted["calibration"] != qualified:
                raise ValueError("Retained calibration differs from its original command window")
            record["phase"] = "sample_import_pending"
            append_journal(path, record)
            attempt = path.name
            existing = next((e for e in store.events if e.get("measurement_attempt") == attempt), None)
            event = existing or store.append(
                "report",
                tool_number=None,
                report=TloReport.from_dict(qualified["report"]).to_dict(),
                endpoint=record["endpoint"],
                measurement_attempt=attempt,
                source_evidence={
                    "response": source,
                    "qualification": qualified,
                    "command_window_sha256": accepted["command_window_sha256"],
                    "assembly_attribution_verified": False,
                    "command_attribution_verified": False,
                },
            )
            record["imported_receipt_id"] = event["id"]
            record["phase"] = "samples_imported_unassigned"
            record["assembly_attribution_verified"] = False
            try:
                append_journal(path, record)
            finally:
                self.latest_record = record
            return event

        self._background(
            capture,
            lambda result, error: setattr(
                self.note,
                "text",
                error
                or "Samples saved unassigned in the tool passport. Use its receipt-attribution review to select an assembly. Applied TLO remains unknown.",
            ),
        )

    def dispose(self):
        self.closed = True
        self.review = self.observation_review = None
        if self.popup:
            self.popup.dismiss()
