"""Read-only M499 receipt actions shared with the installed-tool measurement pane."""

import copy
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from kivy.clock import Clock

from carveracontroller.headless.atc_offset import AtcOffsetObservation, AtcOffsetRead
from carveracontroller.headless.probe_settings_receipts import ipc_record
from carveracontroller.machine.backend_live_report import integer
from carveracontroller.machine.probe_settings_workflow import append_journal, canonical


def read_offset(panel, *, warmed=False):
    if panel.closed or panel.busy or panel.observation_review is not None:
        return
    try:
        client, state, connection = panel._binding()
        if not warmed:
            panel._warm_state(client, lambda: read_offset(panel, warmed=True))
            return
        context, identity = panel._context(), copy.deepcopy(panel.identity)
        ticket = AtcOffsetRead.create(client.session_id, connection, context, identity or {}, state, time.monotonic())
    except ValueError as failure:
        panel.note.text = str(failure)
        return
    path = panel.root_path / (uuid4().hex + ".jsonl")
    if not panel._start("Retaining read intent, then reading the current ATC offset…"):
        return
    panel.atc_offset_observation = None

    def dispatch():
        record = panel._record("atc_offset_read_pending", client, connection, context)
        record.update(read=asdict(ticket), identity=identity, readonly=True)
        saved = submitted = False
        try:
            append_journal(path, record, new=True)
            saved = True
            if client.submit("snapshot").result().envelope.get("ok") is not True:
                raise ValueError("Current private state unavailable")
            ready, abandoned, lock, admitted = threading.Event(), threading.Event(), threading.Lock(), []

            def preflight(_dt):
                with lock:
                    try:
                        if abandoned.is_set():
                            return
                        current, snapshot, current_connection = panel._binding()
                        if current is not client or panel.identity != identity:
                            raise ValueError("Offset owner or reported identity changed")
                        params = ticket.authorize(
                            client.session_id, current_connection, panel._context(), snapshot, time.monotonic()
                        )
                        admitted.append(client.submit("operation", params))
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
                raise ValueError("Offset read admission expired")
            if isinstance(admitted[0], Exception):
                raise admitted[0]
            submitted = True
            response = admitted[0].result()
            record["response"] = ipc_record(response)
            observation = AtcOffsetObservation.retained(ticket, response, context["profile"])
            record["qualified_report"] = observation.receipt
            record["phase"] = "atc_offset_report_retained"
        except Exception as failure:
            record["phase"] = "atc_offset_read_unresolved" if submitted else "atc_offset_not_submitted"
            record["error"] = str(failure)
            observation = None
        record["submitted"] = submitted
        try:
            if not saved:
                raise ValueError("Read intent durability unavailable")
            record["result_durability"] = "retained"
            append_journal(path, record)
        except Exception:
            record["result_durability"] = "unconfirmed"
            raise
        finally:
            panel.atc_offset_record, panel.atc_offset_path = record, path
        return record, observation

    def finish(result, error):
        if error:
            panel.note.text = error + ". No automatic query retry."
            return
        record, observation = result
        if observation is None:
            panel.note.text = record.get("error", "Offset report unresolved") + ". Original attempt retained; no retry."
            return
        try:
            current, snapshot, current_connection = panel._binding()
            if current is not client or panel.identity != identity:
                raise ValueError("Offset read owner or identity retired")
            ticket.authorize(client.session_id, current_connection, panel._context(), snapshot, time.monotonic())
            panel.atc_offset_observation = observation
            panel.note.text = "Original M499 ATC offset retained. Robot compensation, physical tool identity and accuracy remain unverified."
        except ValueError as failure:
            panel.note.text = str(failure) + ". Report remains historical on its original connection."

    panel._background(dispatch, finish)


def refresh_offset(panel, available, awaiting):
    panel.atc_offset_action.disabled = panel.busy or awaiting or not available or panel.identity is None
    panel.atc_offset_export.disabled = panel.busy or panel.atc_offset_record is None
    record = panel.atc_offset_record
    if not record:
        panel.atc_offset_summary.text = (
            "ATC offset readback · no retained M499 report. Raw status offsets keep their unknown reference."
        )
        return
    value = record.get("qualified_report")
    if not value:
        panel.atc_offset_summary.text = "ATC offset readback · " + record.get("error", "Unresolved attempt")
        return
    observation = panel.atc_offset_observation
    binding = panel.workspace.control_owner.binding
    current = False
    if observation is not None and binding is not None:
        report = panel.workspace.backend_report()
        tool = integer(report.status.get("tool"), 1, 6) if report.status is not None else None
        current = report.current and observation.fresh_for(
            (binding.session_id, binding.connection_id), panel._profile(), tool, time.monotonic()
        )
    panel.atc_offset_summary.text = (
        f"{'Fresh read' if current else 'Recorded read · historical'} · T{value['tool']} ATC offset {value['atc_offset_mm']:g} mm\n"
        f"Reference MZ {value['reference_mz_mm']:g} mm · current MZ {value['current_mz_mm']:g} mm · 0.001 mm printed resolution\n"
        "Pinned source units; unauthenticated firmware. Robot compensation and physical accuracy remain unverified."
    )


def export_offset(panel):
    if panel.closed or panel.busy or panel.atc_offset_record is None:
        return
    record = copy.deepcopy(panel.atc_offset_record)

    def selected(path):
        if not path or not panel._start("Saving the original ATC offset receipt…"):
            return

        def save():
            raw = canonical(record).encode() + b"\n"
            with Path(path).open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if Path(path).read_bytes() != raw:
                raise ValueError("Offset export readback differs")
            return str(path)

        panel._background(
            save,
            lambda result, error: setattr(
                panel.note, "text", error or "ATC offset receipt saved and read back: " + result
            ),
        )

    panel.workspace.choose_profile_file(selected, save=True, extension=".json", title="Export ATC offset receipt")
