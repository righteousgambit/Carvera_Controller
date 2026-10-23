"""Bank review navigation context. Document reads run in the existing workers."""

import copy
import time

from carveracontroller.headless.tool_exchange import ToolExchangeReview
from carveracontroller.machine.bank_tool_handoff import capture_handoff, handoff_label
from carveracontroller.machine.probe_settings_workflow import load_journal
from carveracontroller.machine.tool_bank_review import BankReviewStore


class BankReviewHandoff:
    def __init__(self, panel, pocket):
        self.panel, self.pocket = panel, pocket
        self.store, self.store_path = panel.store, panel.store.path
        self.program = panel.program
        self.banks = panel.banks
        if self.program is None or panel.bank not in self.banks:
            raise ValueError("The selected bank does not belong to the current program")
        self.frozen = self._capture()
        self.saved = copy.deepcopy(panel.record)
        self.exchange_panel = self.exchange_record = self.exchange_path = None

    def _capture(self):
        panel = self.panel
        machine, profiles, custody = panel.context()
        if (
            panel.store is not self.store
            or panel.store.path != self.store_path
            or panel.store.error
            or panel.program is None
            or panel.program is not self.program
            or panel.banks is not self.banks
            or panel.bank is None
            or panel.operations.program is not panel.program
            or machine is None
            or custody is None
        ):
            raise ValueError("The bank's current program or preparation is unavailable; open it again")
        saved = panel.store.get(panel.program.file_hash, machine["id"], panel.bank.index)
        return capture_handoff(
            panel.program, panel.bank, machine, panel.record, saved, panel.choices, custody, profiles, self.pocket
        )

    @property
    def label(self):
        origin = "Following retained exchange" if self.exchange_record is not None else "Saved bank preparation"
        return handoff_label(self.frozen.context()) + "\n" + origin

    def resolve(self):
        if self._capture() != self.frozen:
            raise ValueError("The bank preparation changed; open its exchange review again")
        context = self.frozen.context()
        context["entry"] = "saved_preparation"
        if self.exchange_panel is not None:
            self._require_exchange()
            context["entry"] = "retained_exchange"
            context["exchange_receipt_file"] = str(self.exchange_path)
            context["exchange_review"] = copy.deepcopy(self.exchange_record["review"])
        return context

    def verify_saved(self):
        """Called after durable intent IO, before the final UI admission check."""
        identity = self._file_identity()
        store = BankReviewStore(self.store_path)
        context = self.frozen.context()
        saved = store.get(context["program_hash"], context["machine_profile"]["id"], context["bank_index"])
        if store.error or saved != self.saved:
            raise ValueError("Saved bank preparation changed; no operation was submitted")
        if self.exchange_record is not None:
            if load_journal(self.exchange_path)[-1]["record"] != self.exchange_record:
                raise ValueError("Retained bank exchange receipt changed; review the exchange again")
        self.verify_unchanged(identity)
        return identity

    def _file_identity(self):
        paths = [self.store_path]
        if self.exchange_path is not None:
            paths.append(self.exchange_path)
        try:
            return tuple(
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                for stat in (path.stat() for path in paths)
            )
        except OSError as failure:
            raise ValueError("Saved bank preparation or exchange receipt is unavailable") from failure

    def verify_unchanged(self, identity):
        """Cheap final preflight guard for edits during the worker/UI handoff."""
        if self._file_identity() != identity:
            raise ValueError("Saved bank preparation or exchange receipt changed; no operation was submitted")

    def _require_exchange(self):
        panel, record = self.exchange_panel, self.exchange_record
        if (
            panel is None
            or record is None
            or panel.busy
            or panel.latest_record != record
            or panel.journal_path != self.exchange_path
            or record.get("phase") != "target_tool_reported"
            or record.get("result_durability") != "retained"
            or panel._context() != record.get("context")
        ):
            raise ValueError("A retained later Idle/tool exchange receipt is required before measurement")
        backend = panel.workspace.backend_panel
        client = backend.client
        if panel.closed or backend.closed or backend.stopping or client is None:
            raise ValueError("The bank exchange's backend is unavailable")
        state = client.snapshot()
        if not panel.workspace.control_owner.matches(client.session_id, state):
            raise ValueError("The bank exchange's backend owner changed")
        connection = state["last_machine_snapshot"]["connection_id"]
        if (client.session_id, connection) != (record["session_id"], record["connection_id"]):
            raise ValueError("The bank exchange belongs to a different backend connection")
        review = ToolExchangeReview(**record["review"])
        if not review.target_reported(state, time.monotonic(), record["response"]["received_at_s"]):
            raise ValueError("A fresh Idle report with the exchanged controller tool is required")

    def after_exchange(self, panel):
        context = self.resolve()
        record = panel.latest_record
        if record is None or record.get("context", {}).get("bank_handoff") != context:
            raise ValueError("The retained exchange does not match this bank preparation")
        following = copy.copy(self)
        following.exchange_panel = panel
        following.exchange_record = copy.deepcopy(record)
        following.exchange_path = panel.journal_path
        following.resolve()
        return following
