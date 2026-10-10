"""Named local probe presets and explicit fixed-key backend settings reviews."""

import base64
import copy
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Field, QuantityField, Surface
from carveracontroller.desktop_planning import PlanningCard, planning_popup
from carveracontroller.headless.probe_settings_receipts import ipc_record, validate_apply, validate_read
from carveracontroller.machine.backend_live_report import backend_live_report
from carveracontroller.machine.probe_settings_workflow import (
    KEYS,
    KINDS,
    MAX_BYTES,
    PresetStore,
    ProbeReview,
    append_journal,
    canonical,
    decimal_token,
    dimension_token,
    fingerprint,
    load_journal,
    preset,
    strict_json,
)


class ProbeSettingsPanel(Surface):
    def __init__(self, workspace, storage_root=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.root_path = Path(storage_root or Path.home() / ".carvera" / "probe-settings")
        self.store = PresetStore(self.root_path / "presets.json")
        self.busy = self.closed = False
        self.baseline = self.review = self.popup = None
        self.presets = []
        self.latest_record = self.journal_path = None
        self.add_widget(flowing_text("Probe settings & presets", 28))
        self.add_widget(
            flowing_text(
                "Read the two SD probe settings, review a named preset, then apply it to the selected backend connection. Presets declare values; they do not prove calibration.",
                56,
            )
        )
        card = PlanningCard("Local preset")
        card.set_expanded(True, reveal=False)
        self.saved = Choice(text="Choose a saved preset", values=())
        self.saved.bind(text=self._choose)
        card.content.add_widget(self.saved)
        self.name = Field(hint_text="Preset name")
        self.kind = Choice(text="mechanical", values=KINDS)
        self.tip = QuantityField(minimum=0.000001, maximum=500, hint_text="Tip diameter · mm or in")
        self.correction = QuantityField(minimum=-500, maximum=500, hint_text="ATC TLO correction · mm or in")
        self.preset_note = Field(hint_text="Optional preset note")
        fields = AdaptiveGrid(max_cols=2, min_width=220, row_height=96, spacing=dp(6))
        for title, field in (
            ("Name", self.name),
            ("Probe kind · local metadata", self.kind),
            ("Probe tip diameter", self.tip),
            ("ATC TLO correction", self.correction),
            ("Note", self.preset_note),
        ):
            cell = Surface(orientation="vertical", padding=dp(6), spacing=dp(4))
            cell.add_widget(flowing_text(title, 22))
            cell.add_widget(field)
            fields.add_widget(cell)
        card.content.add_widget(fields)
        self.local_actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        self.load_action = Action("Load saved presets", self.load_presets)
        self.save_action = Action("Save local preset", self.save_preset)
        self.import_action = Action("Import presets…", lambda: self._pick("import"))
        self.export_action = Action("Export presets…", lambda: self._pick("presets"))
        for action in (self.load_action, self.save_action, self.import_action, self.export_action):
            self.local_actions.add_widget(action)
        card.content.add_widget(self.local_actions)
        self.summary = flowing_text("No original settings read on this connection.", 48)
        self.add_widget(self.summary)
        actions = AdaptiveGrid(max_cols=2, min_width=160, row_height=38, spacing=dp(6))
        self.read_action = Action("Read actual SD settings", self.read_settings)
        self.review_action = Action("Review preset application", self.review_settings, disabled=True)
        self.recovery_action = Action("Inspect retained attempts", self.inspect_attempts)
        self.receipt_action = Action("Export latest receipt…", lambda: self._pick("receipt"), disabled=True)
        for action in (self.read_action, self.review_action, self.recovery_action, self.receipt_action):
            actions.add_widget(action)
        self.add_widget(actions)
        self.add_widget(card)
        self.note = flowing_text(
            "Select the connected private backend as the workbench owner to read machine settings. Local presets can be managed independently.",
            58,
        )
        self.add_widget(self.note)
        self.add_widget(
            flowing_text(
                "Matching SD readback does not verify active ATC TLO, persistence after restart, firmware identity or physical accuracy. Partial or uncertain writes are retained without retry, rollback or restart.",
                64,
            )
        )

    def _profile(self):
        return copy.deepcopy(self.workspace.selected_machine_profile or {})

    def _draft(self):
        def token(field, key):
            value = field.value()
            # Preserve an exact decimal token when already entered in mm.
            try:
                return decimal_token(field.text.strip(), key)
            except ValueError:
                return dimension_token(value, key)

        return preset(
            {
                "name": self.name.text,
                "kind": self.kind.text,
                "tip_diameter_token": token(self.tip, KEYS[0]),
                "tlo_correction_token": token(self.correction, KEYS[1]),
                "note": self.preset_note.text,
            }
        )

    def _context(self):
        return {"profile": self._profile(), "preset": self._draft()}

    def _binding(self, *, write=False):
        ws = self.workspace
        panel = getattr(ws, "backend_panel", None)
        client = panel.client if panel else None
        if (
            self.closed
            or not panel
            or panel.closed
            or panel.stopping
            or client is None
            or panel.endpoint_profile != panel._profile_key()
        ):
            raise ValueError("Select the connected backend as the workbench owner first")
        state = client.snapshot()
        if not ws.control_owner.matches(client.session_id, state):
            raise ValueError("The selected backend connection is unavailable or replaced")
        machine = state["last_machine_snapshot"]
        if machine.get("transfer_active") is not False or machine.get("unknown_outcome") is not False:
            raise ValueError("A backend transfer or unresolved outcome blocks settings reads and writes")
        if write:
            report = backend_live_report(ws.control_owner, client.session_id, state, self._profile(), time.monotonic())
            status, diagnostic = machine.get("status") or {}, machine.get("diagnostics") or {}
            age = machine.get("diagnostics_age_ms")
            cached_age = state.get("last_machine_snapshot_age_s")
            if (
                not report.current
                or status.get("state") != "Idle"
                or status.get("is_playing") is not False
                or any(
                    type(status.get(k)) not in (int, float) or status[k] != 0
                    for k in ("spindle_rpm", "spindle_target_rpm")
                )
                or diagnostic.get("spindle_enabled") is not False
                or type(age) not in (int, float)
                or type(cached_age) not in (int, float)
                or not 0 <= age + cached_age * 1000 <= 3000
            ):
                raise ValueError(
                    "Application requires a fresh matching machine report: Idle, no playing job, zero spindle and spindle disabled"
                )
        return client, machine["connection_id"]

    def _start(self, message):
        if self.closed or self.busy:
            return False
        self.busy = True
        self.note.text = message
        self.refresh()
        return True

    def _background(self, function, finish):
        def run():
            value, error = None, None
            try:
                value = function()
            except Exception as failure:
                error = str(failure)

            def done(_dt):
                self.busy = False
                if not self.closed:
                    finish(value, error)
                    self.refresh()

            Clock.schedule_once(done, 0)

        threading.Thread(target=run, name="desktop-probe-settings", daemon=True).start()

    def _preset_finish(self, entries, error):
        if error:
            self.note.text = error + ". Inspect the retained files before retrying."
            return
        self.presets = entries
        self.saved.values = tuple(p["name"] for p in entries)
        self.note.text = f"{len(entries)} local presets available. Loading a preset sends no machine command."

    def load_presets(self):
        if self._start("Reading local presets…"):
            self._background(self.store.load, self._preset_finish)

    def save_preset(self):
        if self.closed or self.busy:
            return
        try:
            item = self._draft()
        except ValueError as error:
            self.note.text = str(error)
            return
        if self._start("Saving and reading back this local preset…"):
            self._background(lambda: self.store.save(item), self._preset_finish)

    def _choose(self, _widget, name):
        if self.busy or self.closed:
            return
        item = next((p for p in self.presets if p["name"] == name), None)
        if item:
            self.name.text, self.kind.text = item["name"], item["kind"]
            self.tip.text, self.correction.text = item["tip_diameter_token"], item["tlo_correction_token"]
            self.preset_note.text = item["note"]
            self.review = None
            self.note.text = "Local preset loaded. Read and review before applying it."

    def _pick(self, kind):
        if self.closed or self.busy:
            return
        record = copy.deepcopy(self.latest_record)
        if kind == "receipt" and record is None:
            return

        def selected(path):
            if self.closed or self.busy or not path:
                return
            target = Path(path)

            def work():
                if kind == "import":
                    with target.open("rb") as stream:
                        return self.store.replace(strict_json(stream.read(MAX_BYTES + 1)))
                data = record if kind == "receipt" else {"schema": 1, "presets": self.store.load()}
                raw = canonical(data).encode() + b"\n"
                # Picker approval names a new export; existing evidence is never overwritten.
                with target.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    import os

                    os.fsync(stream.fileno())
                if target.read_bytes() != raw:
                    raise ValueError("Export readback differs")
                return str(target)

            def finish(value, error):
                if kind == "import":
                    self._preset_finish(value, error)
                else:
                    self.note.text = error or "Export retained and read back: " + value

            if self._start("Reading local file…" if kind == "import" else "Saving and reading back export…"):
                self._background(work, finish)

        self.workspace.choose_profile_file(
            selected,
            save=kind != "import",
            extension=".json",
            title="Import probe presets" if kind == "import" else "Export probe " + kind,
        )

    def _record(self, phase, client, connection, context, response=None):
        record = {
            "phase": phase,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "session_id": client.session_id,
            "connection_id": connection,
            "context": context,
            "execution_authorized": False,
            "physical_accuracy_verified": False,
        }
        if response is not None:
            # Capture even refused or malformed results before independently validating them.
            record["response"] = {
                "envelope": copy.deepcopy(response.envelope),
                "original_ipc_bytes_base64": base64.b64encode(response.original_line).decode()
                if response.original_line is not None
                else None,
                "response_sha256": response.response_sha256,
                "request_sha256": response.request_sha256,
                "received_at_s": response.received_at_s,
                "elapsed_ms": response.elapsed_ms,
            }
        return record

    def read_settings(self):
        if self.closed or self.busy:
            return
        try:
            client, connection = self._binding()
            profile = self._profile()
        except ValueError as error:
            self.note.text = str(error)
            return
        self.baseline = self.review = None
        path = self.root_path / "receipts" / (uuid4().hex + ".jsonl")
        if not self._start("Reading both original SD settings from the selected backend…"):
            return

        def read():
            record = self._record("read_pending", client, connection, {"profile": profile})
            append_journal(path, record, new=True)
            try:
                response = client.submit("probe_profile_read").result()
                record = self._record("read_observed", client, connection, {"profile": profile}, response)
                ipc_record(response)
                if response.envelope.get("ok") is not True:
                    raise ValueError("Backend refused the settings read; inspect the retained command receipts")
                settings = validate_read(response.envelope.get("result"), connection)
                record["settings"] = settings
            except Exception as error:
                record["phase"], record["error"] = "read_unresolved", str(error)
            try:
                record["result_durability"] = "retained"
                append_journal(path, record)
            except Exception:
                record["result_durability"] = "unconfirmed"
                raise
            finally:
                self.latest_record = record
                self.journal_path = path
            return record

        def finish(record, error):
            if error or record["phase"] != "read_observed":
                self.note.text = error or record.get("error", "Settings read unresolved")
                return
            try:
                current, identity = self._binding()
                if current is not client or identity != connection or self._profile() != profile:
                    raise ValueError(
                        "Machine or connection changed during read; result retained but a fresh read is required"
                    )
                self.baseline = {
                    "session": client.session_id,
                    "connection": connection,
                    "profile_sha256": fingerprint(profile),
                    "settings": record["settings"],
                }
                self.summary.text = "Reported SD settings\n" + "\n".join(
                    f"{title}: {record['settings'][key]['original_numeric_token'] + ' mm' if record['settings'][key]['state'] == 'reported' else 'missing in SD config'}"
                    for title, key in zip(("Tip diameter", "ATC TLO correction"), KEYS)
                )
                self.note.text = (
                    "Original read and IPC receipts retained. Choose or enter a preset, then review the two changes."
                )
            except ValueError as failure:
                self.note.text = str(failure) + ". Original receipts retained; read current settings again."

        self._background(read, finish)

    def review_settings(self):
        if self.closed or self.busy:
            return
        try:
            client, connection = self._binding(write=True)
            original = self.baseline
            if original is None or (original["session"], original["connection"], original["profile_sha256"]) != (
                client.session_id,
                connection,
                fingerprint(self._profile()),
            ):
                raise ValueError("Read settings on the current machine and connection first")
            review = ProbeReview.create(
                client.session_id, connection, self._context(), original["settings"], self._draft(), time.monotonic()
            )
        except ValueError as error:
            self.note.text = str(error)
            return
        self.review = review
        body = Surface(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        body.add_widget(
            flowing_text(
                f"{self._profile().get('name', 'Selected machine')} · {self.name.text}\nConnection: {connection}", 48
            )
        )
        for key, title in zip(KEYS, ("Tip diameter", "ATC TLO correction")):
            before = review.params["expected_settings"][key]["original_numeric_token"]
            body.add_widget(
                flowing_text(
                    f"{title}: {before if before is not None else 'missing'} → {review.params['settings'][key]} mm", 36
                )
            )
        body.add_widget(
            flowing_text(
                "Apply writes both fixed SD keys after rereading the original values. It then reads both back. This review expires in 30 seconds. Active ATC TLO and calibration remain unverified; no automatic restart is performed.",
                94,
            )
        )
        self.apply_action = Action("Apply reviewed SD settings", lambda: self.apply_settings(review))
        body.add_widget(self.apply_action)
        body.add_widget(Action("Return without applying", lambda: self.popup.dismiss()))
        if self.popup:
            self.popup.dismiss()
        self.popup = planning_popup("Review probe settings", body)
        self.popup.open()
        self.refresh()

    def _admit(self, review, client):
        current, connection = self._binding(write=True)
        if current is not client or self.review is not review:
            raise ValueError("Probe review or private child changed; read and review again")
        return review.authorize(current.session_id, connection, self._context(), time.monotonic())

    def apply_settings(self, review):
        if self.closed or self.busy:
            return
        try:
            client, connection = self._binding(write=True)
            params = self._admit(review, client)
            context = self._context()
        except ValueError as error:
            self.note.text = str(error)
            return
        path = self.root_path / "receipts" / (uuid4().hex + ".jsonl")
        if not self._start("Saving the reviewed intent, then rechecking this connection before applying…"):
            return

        def apply():
            submitted, record = False, self._record("apply_pending", client, connection, context)
            record["review"] = {
                "created_at_s": review.created_at,
                "params": params,
                "context_sha256": review.context_sha256,
            }
            intent_saved = False
            try:
                append_journal(path, record, new=True)
                intent_saved = True
                if client.submit("snapshot").result().envelope.get("ok") is not True:
                    raise ValueError("Fresh private state unavailable before application")
                ready, abandoned, lock, admitted = threading.Event(), threading.Event(), threading.Lock(), []

                def preflight(_dt):
                    with lock:
                        try:
                            if abandoned.is_set():
                                return
                            checked = self._admit(review, client)
                            admitted.append(client.submit("probe_profile_apply", checked))
                        except Exception as error:
                            admitted.append(error)
                        finally:
                            ready.set()

                Clock.schedule_once(preflight, 0)
                if not ready.wait(5):
                    with lock:
                        if not ready.is_set():
                            abandoned.set()
                if abandoned.is_set() or len(admitted) != 1:
                    raise ValueError("Application admission expired before submission")
                if isinstance(admitted[0], Exception):
                    raise admitted[0]
                submitted = True
                response = admitted[0].result()
                record["response"] = self._record("", client, connection, context, response)["response"]
                ipc_record(response)
                if response.envelope.get("ok") is not True:
                    raise ValueError("Backend refused or could not complete the settings application")
                validate_apply(response.envelope.get("result"), params)
                record["phase"] = "reported_sd_values_match"
            except Exception as error:
                record["phase"] = "apply_unresolved" if submitted else "not_submitted"
                record["error"] = str(error)
            record["submitted"] = submitted
            try:
                if intent_saved:
                    record["result_durability"] = "retained"
                    append_journal(path, record)
                else:
                    raise ValueError("Intent durability unavailable; no application was submitted")
            except Exception:
                record["result_durability"] = "unconfirmed"
                raise
            finally:
                self.latest_record = record
                self.journal_path = path
            return record

        def finish(record, error):
            self.baseline = self.review = None
            if self.popup:
                self.popup.dismiss()
            if error or record["phase"] != "reported_sd_values_match":
                self.note.text = (
                    error or record.get("error", "Application unresolved")
                ) + ". No retry or rollback. Read actual settings and create a new review before another application."
            else:
                self.note.text = "Both requested SD tokens were reported on readback; original receipts retained. Active ATC TLO, persistence and physical accuracy remain unverified. Read again before another review."
            self.summary.text = (
                "Application receipt: "
                + str(path)
                + "\n"
                + ("Result durability unavailable" if error else record["phase"])
            )

        self._background(apply, finish)

    def inspect_attempts(self):
        if not self._start("Inspecting local receipt chains; no command will be replayed…"):
            return

        def inspect():
            entries = sorted((self.root_path / "receipts").glob("*.jsonl"))
            if len(entries) > 512:
                raise ValueError("More than 512 receipt files; inspect the directory externally")
            results = []
            for path in entries:
                try:
                    rows = load_journal(path)
                    phase = rows[-1]["record"].get("phase", "unknown")
                    if not isinstance(phase, str) or len(phase) > 128:
                        phase = "unresolved record: unsupported phase"
                except (ValueError, OSError) as error:
                    phase = "unresolved chain: " + str(error)
                results.append((path.name, phase))
            return results

        def finish(results, error):
            self.note.text = error or (
                "No retained attempts."
                if not results
                else "Retained attempts · no replay\n"
                + "\n".join(name + " · " + phase for name, phase in results[-12:])
                + f"\n{len(results)} files in {self.root_path / 'receipts'}"
            )

        self._background(inspect, finish)

    def refresh(self):
        if self.closed:
            return
        try:
            self._binding()
            readable = True
        except ValueError:
            readable = False
        self.read_action.disabled = self.busy or not readable
        self.review_action.disabled = self.busy or not readable or self.baseline is None
        self.receipt_action.disabled = self.busy or self.latest_record is None
        self.saved.disabled = self.busy
        for action in (
            self.load_action,
            self.save_action,
            self.import_action,
            self.export_action,
            self.recovery_action,
        ):
            action.disabled = self.busy
        if self.review and hasattr(self, "apply_action"):
            try:
                client, _connection = self._binding(write=True)
                self._admit(self.review, client)
                allowed = True
            except ValueError:
                allowed = False
            self.apply_action.disabled = self.busy or not allowed

    def dispose(self):
        self.closed = True
        self.review = None
        if self.popup:
            self.popup.dismiss()
