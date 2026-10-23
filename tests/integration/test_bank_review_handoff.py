import copy
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.desktop_components import Action
from carveracontroller.desktop_tool_banks import ToolBankPanel
from carveracontroller.desktop_tool_exchange import ToolExchangePanel
from carveracontroller.machine.probe_settings_workflow import append_journal, load_journal
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank
from carveracontroller.machine.tool_custody import ToolCustodyStore
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401
from tests.integration.test_backend_tool_measurement import measurement_workbench  # noqa: F401
from tests.integration.touch_input import WindowTouch


@pytest.fixture
def bank_workbench(measurement_workbench, tmp_path):  # noqa: F811
    measurement, backend, ws, state, requests = measurement_workbench
    program = ProgramOperations.from_text("G21 G90\n" + "\n".join(f"T{t} M6" for t in range(1, 13)))
    profile = {"id": "bank-two-cutter", "name": "Fine cutter", "number": 7, "diameter": 3.175, "shank_diameter": 6.35}
    ws.profile_store = SimpleNamespace(data={"tools": [profile]})
    assembly = ws.machine.tool_custody.create_assembly("Assembly seven", "Collet", 28, profile["id"])
    ws.machine.gcode_viewer.library_tool_table_mm[7] = ToolDefinition(7, diameter=3.175, description="Logical seven")
    bank = ToolBankPanel(SimpleNamespace(program=program, workspace=ws), BankReviewStore(tmp_path / "banks.json"))
    bank.load(program)
    bank.selector.text = next(label for label, item in bank.options.items() if item.index == 2)
    bank.choose(1, assembly["id"])
    bank.save()
    assert bank.record == bank.store.get(program.file_hash, ws.selected_machine_profile["id"], 2)
    exchange = ToolExchangePanel(ws, storage_root=tmp_path / "bank-exchanges", size_hint=(None, None), width=dp(650))
    ws.tool_exchange_panel = exchange
    Window.add_widget(exchange)
    ws.open_tool_exchange = exchange.use_bank
    ws.open_tool_measurement = measurement.use_bank
    original_handler = state.command_handler
    state.exchanges, state.report_exchange = [], True

    def handler(sock, command):
        if command == b"M6 T1\n":
            state.exchanges.append(command)
            if state.report_exchange:
                state.status = state.status.replace(b"T:2,12", b"T:1,12")
            sock.sendall(b"ok\n")
            return True
        return original_handler(sock, command)

    state.command_handler = handler
    timer = Clock.schedule_interval(lambda _dt: exchange.refresh(), 0.1)
    try:
        yield bank, exchange, measurement, backend, ws, state, requests, profile
    finally:
        timer.cancel()
        exchange.dispose()
        Window.remove_widget(exchange)


def prepare_exchange(parts):
    bank, exchange, _measurement, backend, _ws, state, _requests, _profile = parts
    state.status = state.status.replace(b"T:1,12", b"T:2,12")
    pump_frames(12, sleep=0.04)
    backend.request("snapshot")
    wait_for(lambda: not backend.busy)
    bank.review_exchange(1)
    exchange.read_identity()
    wait_for(lambda: not exchange.busy)
    exchange.review_exchange()
    wait_for(lambda: not exchange.busy)
    assert exchange.review is not None, exchange.note.text
    return exchange.review


def non_snapshot(requests):
    return [(method, params) for method, params in requests if method != "snapshot"]


def test_actual_compact_row_buttons_reveal_production_panes_without_dispatch(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    prior_section, prior_task = ws.active_section, ws.setup_tasks.active
    program = ProgramOperations.from_text("G21 G90\n" + "\n".join(f"T{t} M6" for t in range(1, 13)))
    profile = {"id": "navigation-design", "name": "Fine cutter", "number": 7, "diameter": 3.175, "shank_diameter": 6.35}
    custody = ToolCustodyStore(tmp_path / "navigation-custody.json")
    assembly = custody.create_assembly("Bank two assembly", "Collet", 28, profile["id"])
    monkeypatch.setitem(ws.machine.__dict__, "_tool_custody", custody)
    monkeypatch.setattr(ws.profile_store, "_data", dict(ws.profile_store.data, tools=[profile]))
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "navigation-machine", "name": "Test", "model": "C1"})
    monkeypatch.setattr(ws, "tool_exchange_panel", None)
    monkeypatch.setattr(ws, "tool_measurement_panel", None)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    requests = Mock()
    monkeypatch.setattr(ws.backend_panel, "request", requests)
    bank = ToolBankPanel(
        SimpleNamespace(program=program, workspace=ws), BankReviewStore(tmp_path / "navigation-banks.json")
    )
    bank.size_hint = (None, None)
    bank.width = dp(340)
    bank.load(program)
    bank.selector.text = next(label for label, item in bank.options.items() if item.index == 2)
    bank.choose(1, assembly["id"])
    assert bank.choices == {1: assembly["id"]}, bank.result.text
    bank.save()
    assert bank.record == bank.store.get(program.file_hash, ws.selected_machine_profile["id"], 2)
    bank.filter_choice.text = "Selected assemblies"
    try:
        for label, attribute in (
            ("Review exchange", "tool_exchange_panel"),
            ("Review measurement", "tool_measurement_panel"),
        ):
            Window.add_widget(bank)
            pump_frames(12)
            card = bank.grid.children[0]
            buttons = [widget for widget in card.walk(restrict=True) if isinstance(widget, Action)]
            for button in buttons:
                assert button.texture_size[0] <= button.width
                assert card.x <= button.x and button.right <= card.right
                assert card.y <= button.y and button.top <= card.top
                assert not any(
                    button is not other
                    and min(button.right, other.right) > max(button.x, other.x)
                    and min(button.top, other.top) > max(button.y, other.y)
                    for other in buttons
                )
            action = next(widget for widget in buttons if widget.text == label)
            x, y = action.to_window(*action.center)
            touch = WindowTouch(x, y)
            touch.touch_down()
            pump_frames(2)
            touch.touch_up()
            pump_frames(2)
            Window.remove_widget(bank)
            pump_frames(12)
            panel = getattr(ws, attribute)
            assert panel is not None, bank.result.text
            assert panel.parent is not None and panel.bank_handoff is not None
            assert ws.active_section == "Setup" and ws.setup_tasks.active == "Tools"
            assert "Program T7 · Controller T1" in panel.summary.text
        send.assert_not_called()
        requests.assert_not_called()
    finally:
        if bank.parent:
            Window.remove_widget(bank)
        for panel in (ws.tool_exchange_panel, ws.tool_measurement_panel):
            if panel:
                panel.dispose()
                if panel.parent:
                    panel.parent.remove_widget(panel)
        ws.setup_tasks.show(prior_task)
        ws.select(prior_section)
        pump_frames(2)


def test_bank_navigation_and_actual_exchange_measurement_keep_t7_t1_distinct(bank_workbench, monkeypatch):
    bank, exchange, measurement, _backend, ws, state, requests, _profile = bank_workbench
    originals = copy.deepcopy(ws.machine.gcode_viewer.library_tool_table_mm)
    before = copy.deepcopy(non_snapshot(requests))
    bank.review_exchange(1)
    assert exchange.bank_handoff is not None
    assert exchange._context()["target"] == 1
    assert exchange._context()["declared_tool_mm"]["diameter"] == 3.175
    bank.review_exchange(1, measurement=True)
    assert measurement._context()["bank_handoff"]["entry"] == "saved_preparation"
    assert measurement._context()["assembly"]["name"] == "Assembly seven"
    assert measurement.kind.text == "Confirm installed tool kind"
    assert non_snapshot(requests) == before and state.exchanges == state.measurements == []

    # Refreshes must not repeatedly scan all parsed program lines.
    with monkeypatch.context() as refresh_patch:
        refresh_patch.setattr(bank.program, "plan_tool_banks", lambda: pytest.fail("refresh rescanned program"))
        for _ in range(5):
            exchange.refresh()
            measurement.refresh()

    ticket = prepare_exchange(bank_workbench)
    assert ticket.target == 1 and ticket.plan["commands"] == ["M6 T1"]
    exchange.exchange_action.dispatch("on_release")
    wait_for(lambda: not exchange.busy and exchange.latest_record["phase"] == "target_tool_reported")
    exchange.refresh()
    assert not exchange.next_measurement_action.disabled
    before = copy.deepcopy(non_snapshot(requests))
    exchange.next_measurement_action.dispatch("on_release")
    assert non_snapshot(requests) == before
    context = measurement._context()
    assert context["target"] == 1 and context["bank_handoff"]["logical_tool"] == 7
    assert context["bank_handoff"]["entry"] == "retained_exchange"
    assert context["bank_handoff"]["exchange_receipt_file"] == str(exchange.journal_path)
    assert context["declared_tool_mm"]["diameter"] == 3.175
    measurement.read_identity()
    wait_for(lambda: not measurement.busy)
    measurement.kind.text = "Installed cutter"
    measurement.review_measurement()
    wait_for(lambda: not measurement.busy)
    assert measurement.review is not None, measurement.note.text
    measurement.measurement_action.dispatch("on_release")
    wait_for(lambda: not measurement.busy and measurement.latest_record["phase"] == "later_idle_reported")
    measurement.capture_samples()
    wait_for(lambda: not measurement.busy)
    reports = [event for event in ws.machine.tool_custody.events if event["kind"] == "report"]
    assert len(reports) == 1 and reports[0]["tool_number"] is None and reports[0]["report"]["applied"] is None
    assert not any(event["kind"] == "link" for event in ws.machine.tool_custody.events)
    assert state.exchanges == [b"M6 T1\n"] and state.measurements == [b"M491 R3\n"]
    assert ws.machine.gcode_viewer.library_tool_table_mm == originals
    assert bank.program.file_hash == context["bank_handoff"]["program_hash"]
    ws.machine.controller.executeCommand.assert_not_called()


def test_direct_current_tool_measurement_needs_no_exchange(bank_workbench):
    bank, _exchange, measurement, _backend, _ws, state, requests, _profile = bank_workbench
    before = copy.deepcopy(non_snapshot(requests))
    bank.review_exchange(1, measurement=True)
    assert non_snapshot(requests) == before
    measurement.read_identity()
    wait_for(lambda: not measurement.busy)
    measurement.review_measurement()
    wait_for(lambda: not measurement.busy)
    assert measurement.review is None  # Opening a bank does not assert installed cutter kind.
    measurement.kind.text = "Installed cutter"
    measurement.review_measurement()
    wait_for(lambda: not measurement.busy)
    assert measurement.review is not None, measurement.note.text
    measurement.measurement_action.dispatch("on_release")
    wait_for(lambda: not measurement.busy and measurement.latest_record["phase"] == "later_idle_reported")
    assert state.exchanges == [] and state.measurements == [b"M491 R3\n"]
    context = load_journal(measurement.journal_path)[-1]["record"]["context"]["bank_handoff"]
    assert context["entry"] == "saved_preparation" and "exchange_receipt_file" not in context


@pytest.mark.parametrize("already_open", [False, True])
@pytest.mark.parametrize(
    "change", ["ack_only", "durability", "owner", "connection", "stale", "tool", "record", "bank", "setup"]
)
def test_exchange_followup_requires_matching_retained_current_result(bank_workbench, change, already_open, monkeypatch):
    bank, exchange, measurement, backend, ws, state, requests, _profile = bank_workbench
    prepare_exchange(bank_workbench)
    exchange.exchange_action.dispatch("on_release")
    wait_for(lambda: not exchange.busy and exchange.latest_record["phase"] == "target_tool_reported")
    if already_open:
        exchange.open_measurement()
        assert measurement.bank_handoff is not None
    if change == "ack_only":
        exchange.latest_record["phase"] = "exchange_acknowledged"
    elif change == "durability":
        exchange.latest_record["result_durability"] = "unconfirmed"
    elif change == "owner":
        ws.control_owner.binding = None
    elif change == "record":
        exchange.latest_record["context"]["bank_handoff"]["preparation_revision"] = "other"
    elif change == "bank":
        bank.selector.text = next(label for label, item in bank.options.items() if item.index == 1)
    elif change == "setup":
        ws.loaded_toolset = {"id": "different-setup"}
    else:
        snapshot = backend.client.snapshot()
        if change == "connection":
            snapshot["last_machine_snapshot"]["connection_id"] = "replacement"
        elif change == "stale":
            snapshot["last_machine_snapshot_age_s"] = 10
        else:
            snapshot["last_machine_snapshot"]["status"]["tool"] = 2
        monkeypatch.setattr(backend.client, "snapshot", lambda: snapshot)
    before = copy.deepcopy(non_snapshot(requests))
    if already_open:
        with pytest.raises(ValueError):
            measurement._context()
        measurement.refresh()
        assert measurement.review_action.disabled
    else:
        exchange.open_measurement()
        assert measurement.bank_handoff is None
    assert non_snapshot(requests) == before and state.measurements == []


@pytest.mark.parametrize("workflow", ["exchange", "measurement"])
@pytest.mark.parametrize(
    "change", ["design", "saved_file", "snapshot_pending", "expired_proof", "program", "choice", "assembly", "machine"]
)
def test_bank_changes_during_durable_intent_prevent_submission(bank_workbench, monkeypatch, workflow, change):
    bank, exchange, measurement, backend, ws, state, _requests, profile = bank_workbench
    if workflow == "exchange":
        ticket = prepare_exchange(bank_workbench)
        panel, action = exchange, exchange.exchange
    else:
        bank.review_exchange(1, measurement=True)
        measurement.read_identity()
        wait_for(lambda: not measurement.busy)
        measurement.kind.text = "Installed cutter"
        measurement.review_measurement()
        wait_for(lambda: not measurement.busy)
        ticket, panel, action = measurement.review, measurement, measurement.measurement
    assert ticket is not None
    saved, release = threading.Event(), threading.Event()

    def delayed(path, record, **kwargs):
        append_journal(path, record, **kwargs)
        if record["phase"] == workflow + "_pending":
            saved.set()
            assert release.wait(5)

    if change == "expired_proof":
        verify = panel.bank_handoff.verify_saved

        def delayed_readback():
            verified_at = verify()
            saved.set()
            assert release.wait(5)
            return verified_at - 1

        monkeypatch.setattr(panel.bank_handoff, "verify_saved", delayed_readback)
    elif change == "snapshot_pending":
        submit = backend.client.submit

        def delayed_snapshot(method, *args, **kwargs):
            future = submit(method, *args, **kwargs)
            if method == "snapshot" and threading.current_thread().name == "desktop-tool-" + workflow:

                def result():
                    response = future.result()
                    saved.set()
                    assert release.wait(5)
                    return response

                return SimpleNamespace(result=result)
            return future

        monkeypatch.setattr(backend.client, "submit", delayed_snapshot)
    else:
        monkeypatch.setattr(f"carveracontroller.desktop_tool_{workflow}.append_journal", delayed)
    action(ticket)
    try:
        wait_for(saved.is_set)
        if change == "design":
            profile["diameter"] = 5
        elif change == "program":
            bank.operations.program = None
        elif change == "choice":
            bank.choices[1] = "different-assembly"
        elif change == "assembly":
            assembly_id = bank.choices[1]
            ws.machine.tool_custody.revise(
                assembly_id, assembly_id, "Reseated", "Collet", 29, profile["id"], "Reseated"
            )
        elif change == "machine":
            ws.selected_machine_profile["name"] = "Changed machine profile"
        elif change == "expired_proof":
            frames = []
            heartbeat = Clock.schedule_interval(lambda _dt: frames.append(1), 0)
            try:
                pump_frames(5)
            finally:
                heartbeat.cancel()
            assert len(frames) >= 5  # Persisted readback waits do not own the UI thread.
        else:
            external = BankReviewStore(bank.store.path)
            changed = capture_bank(
                bank.program,
                bank.bank,
                ws.selected_machine_profile["id"],
                bank.choices,
                ws.machine.tool_custody,
                [profile],
            )
            external.save(changed, bank.record["revision"])
    finally:
        release.set()
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "not_submitted", panel.note.text
    assert panel.latest_record["submitted"] is False
    if change == "expired_proof":
        assert "verification expired" in panel.latest_record["error"]
    assert state.exchanges == state.measurements == []
