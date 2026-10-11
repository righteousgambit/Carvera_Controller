"""Actual production widgets/callbacks using local journals and no machine IO."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.adaptive_popup import AdaptiveMonitorPopup
from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.probe_evidence import ProbeEvidenceStore
from carveracontroller.sensor_measurements_popup import EvidenceForm, SensorMeasurementsPopup


def setup():
    return {
        "probe_identity": "TP06-test",
        "seat_revision": "seat-1",
        "configuration_id": "config-1",
        "reference_id": "ring-1",
        "orientation_deg": 0.0,
        "approach_direction": 0.0,
        "approach_feed_mm_min": 60.0,
        "configured_tip_diameter_mm": 1.6,
        "inspected_dimension": "x_diameter",
    }


@pytest.fixture
def measurement_popup(tmp_path):
    machine = SimpleNamespace(
        probe_evidence=ProbeEvidenceStore(tmp_path / "measurement.jsonl"), measurement_declarations={}
    )
    popup = SensorMeasurementsPopup(machine)
    yield popup
    popup.dismiss()


@pytest.fixture
def adaptive_popup(tmp_path, monkeypatch):
    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    program = tmp_path / "part.nc"
    program.write_text("G21\n(Pocket operation)\n")
    controller.set_program_source(program)
    popup = AdaptiveMonitorPopup(controller)
    yield popup
    popup.stop_refresh()
    popup.dismiss()
    controller.stream.send.assert_not_called()
    controller.stream = None


def fill(form, data):
    for key, value in data.items():
        form.fields[key].text = str(value)


def test_setup_fields_save_actual_persistent_receipt_without_json(measurement_popup):
    popup = measurement_popup
    fill(popup.setup, {k: v for k, v in setup().items() if k in popup.setup.fields})
    popup.setup_dimension.text = "X diameter"
    popup.phase.text = "before_cut"
    popup.save_context()
    saved = ProbeEvidenceStore(popup.machine.probe_evidence.path).events()[0]
    assert saved["kind"] == "measurement_setup"
    assert saved["context"]["orientation_deg"] == 0
    assert saved["context"]["phase"] == "before_cut"
    assert saved["context"]["inspected_dimension"] == "x_diameter"
    assert popup.machine.measurement_declarations["probe_identity"] == "TP06-test"
    assert "Setup saved" in popup.status.text


def test_persistence_failure_preserves_active_setup_and_invalid_numbers(measurement_popup, monkeypatch):
    popup = measurement_popup
    popup.machine.measurement_declarations = {"probe_identity": "original"}
    popup.setup.fields["probe_identity"].text = "replacement"
    popup.setup.fields["approach_feed_mm_min"].text = "nan"
    popup.save_context()
    assert "finite" in popup.status.text
    assert popup.machine.measurement_declarations["probe_identity"] == "original"
    popup.setup.fields["approach_feed_mm_min"].text = ""
    monkeypatch.setattr(popup.machine.probe_evidence, "append", Mock(side_effect=OSError("Read-only folder")))
    popup.save_context()
    assert "Not saved" in popup.status.text and "Read-only folder" in popup.status.text
    assert popup.machine.measurement_declarations["probe_identity"] == "original"


def reference(form, samples, session):
    fill(
        form,
        {
            "reference_id": "ring-1",
            "source_session_id": session,
            "known_diameter": 25,
            "reference_uncertainty_mm": 0.0005,
        },
    )
    for (angle, diameter), (a, d) in zip(samples.rows, ((0, 23.38), (120, 23.4), (240, 23.42))):
        angle.text, diameter.text = str(a), str(d)


def test_map_forms_qualification_and_explicit_corrected_axis_preserve_original(measurement_popup):
    popup = measurement_popup
    popup.machine.measurement_declarations = setup()
    popup.update_actions()
    assert popup.save_map_button.disabled
    popup.feature.text = "Bore"
    reference(popup.fit_reference, popup.fit_samples, "fit-session")
    assert not popup.save_map_button.disabled
    popup.save_map_button.dispatch("on_release")
    assert "UNQUALIFIED" in popup.map_summary.text
    reference(popup.validation_reference, popup.validation_samples, "fit-session")
    popup.validation_reference.fields["max_residual_mm"].text = "0.001"
    assert popup.qualify_button.disabled
    popup.validation_reference.fields["source_session_id"].text = "held-out-session"
    assert not popup.qualify_button.disabled
    popup.qualify_button.dispatch("on_release")
    assert "PASSED" in popup.map_summary.text
    store = popup.machine.probe_evidence
    store.begin(setup())
    original = store.capture("probe", {"kind": "bore", "x_diameter": 25.0, "y_diameter": 25.1})
    popup.refresh()
    popup.measurement_choice.text = next(k for k, v in popup.measurement_options.items() if v == original["id"])
    popup.dimension.text = "Y diameter"
    popup.angle.text = "0"
    assert popup.correct_button.disabled
    popup.dimension.text = "X diameter"
    assert not popup.correct_button.disabled
    popup.correct_button.dispatch("on_release")
    correction = store.events()[-1]
    assert correction["kind"] == "inspected_correction"
    assert correction["corrected"]["x_diameter"] == pytest.approx(25.02)
    assert store._event(original["id"], "measurement")["result"]["x_diameter"] == 25
    assert "original measurement retained" in popup.status.text


def test_recipe_form_defaults_unknown_and_saves_reviewed_values(adaptive_popup):
    popup = adaptive_popup
    assert popup.recipe_save.disabled
    assert all(not field.text for field in popup.recipe_form.fields.values())
    fill(
        popup.recipe_form,
        {
            "cutter": "cutter-a",
            "material": "6061",
            "operation": "pocket",
            "rpm": 12000,
            "flutes": 1,
            "programmed_feed_mm_min": 600,
            "chipload_min_mm": 0.025,
            "chipload_max_mm": 0.05,
        },
    )
    assert not popup.recipe_save.disabled
    assert "50.0–100.0%" in popup.recipe_status.text
    popup.recipe_save.dispatch("on_release")
    assert popup.controller.adaptive_monitor.recipe.cutter == "cutter-a"
    assert popup.controller.sensor_log_path.exists()
    assert "evidence saved" in popup.message.text


def test_outcome_requires_observation_and_current_exact_program(adaptive_popup):
    popup = adaptive_popup
    popup.outcome_form.fields["operation"].text = "pocket"
    popup.outcome_form.fields["notes"].text = "notes alone"
    assert popup.outcome_save.disabled
    popup.outcome_form.fields["dimensional_error_mm"].text = "0"
    assert not popup.outcome_save.disabled
    popup.outcome_save.dispatch("on_release")
    assert popup.controller.adaptive_monitor.outcomes[-1]["dimensional_error_mm"] == 0
    assert popup.controller.adaptive_monitor.outcomes[-1]["temperature_c"] is None
    popup.controller.run_evidence.program["sha256"] = "changed"
    popup.refresh(0)
    assert popup.outcome_save.disabled
    popup.new_outcome()
    assert popup.outcome_form.fields["program_hash"].text == "changed"
    assert not popup.outcome_form.fields["dimensional_error_mm"].text


def test_adaptive_persistence_failure_visible_and_refresh_timer_cancelled(adaptive_popup, monkeypatch):
    popup = adaptive_popup
    monkeypatch.setattr(popup.controller, "adaptiveCommand", Mock(return_value=False))
    assert not popup.command("shadow")
    assert "Not saved" in popup.message.text
    popup.controller._adaptive_log_failed = True
    popup.refresh(0)
    assert popup.commands["shadow"].disabled
    assert "Recording write failed" in popup.path.text
    popup.stop_refresh()
    assert popup.event is None


def test_form_requires_finite_whole_flutes_and_bounds():
    form = EvidenceForm([("flutes", "Flutes", "integer", True)])
    form.fields["flutes"].text = "1.5"
    with pytest.raises(ValueError, match="whole number"):
        form.values()
    form.fields["flutes"].text = "inf"
    with pytest.raises(ValueError, match="finite"):
        form.values()


def test_saved_source_session_chooser_uses_session_identity_and_read_error_disables_actions(
    measurement_popup, monkeypatch
):
    popup = measurement_popup
    store = popup.machine.probe_evidence
    session_id = store.begin(setup())
    receipt = store.capture("probe", {"kind": "bore", "x_diameter": 25.0})
    popup.refresh()
    label = next(k for k, v in popup.session_options.items() if v == receipt["id"])
    popup.fit_session_choice.text = label
    assert popup.fit_reference.fields["source_session_id"].text == session_id
    assert popup.fit_reference.fields["source_session_id"].text != receipt["id"]
    monkeypatch.setattr(store, "events", Mock(side_effect=ValueError("Corrupt journal")))
    popup.refresh()
    assert popup.correct_button.disabled
    assert popup.save_map_button.disabled
    assert popup.qualify_button.disabled
    assert "Corrupt journal" in popup.receipts.text


def test_recorded_approach_direction_is_axis_specific():
    event = {"context": {"approach_direction": 0.0}}
    assert SensorMeasurementsPopup.recorded_direction(event, "x_diameter") == 0
    assert SensorMeasurementsPopup.recorded_direction(event, "y_diameter") is None
    event["context"]["approach_directions"] = {"x_diameter": 0, "y_diameter": 90}
    assert SensorMeasurementsPopup.recorded_direction(event, "y_diameter") == 90


def test_monitor_disabled_recording_cannot_save_or_capture(adaptive_popup):
    popup = adaptive_popup
    popup.controller._evidence_writes_enabled = False
    popup.refresh(0)
    assert all(button.disabled for button in popup.commands.values())
    assert popup.recipe_save.disabled and popup.outcome_save.disabled
    assert not popup.save_payload("recipe", {"untrusted": "value"})
    assert "disabled" in popup.message.text


def test_monitor_read_failure_disables_stale_actions_and_preserves_unsaved_outcome(adaptive_popup, monkeypatch):
    popup = adaptive_popup
    popup.outcome_form.fields["operation"].text = "pocket"
    popup.outcome_form.fields["dimensional_error_mm"].text = "0.02"
    assert not popup.outcome_save.disabled
    original_snapshot = popup.controller.sensor_context_snapshot
    monkeypatch.setattr(popup.controller, "sensor_context_snapshot", Mock(side_effect=OSError("source unavailable")))
    popup.refresh(0)
    assert popup.outcome_save.disabled and popup.recipe_save.disabled and popup.outcome_new.disabled
    assert "source unavailable" in popup.outcome_status.text
    popup.new_outcome()
    assert popup.outcome_form.fields["dimensional_error_mm"].text == "0.02"
    assert not popup.command("shadow")
    monkeypatch.setattr(popup.controller, "sensor_context_snapshot", original_snapshot)
    popup.refresh(0)
    assert not popup.outcome_save.disabled and not popup.outcome_new.disabled


def test_local_recorder_restart_establishes_distinct_journal_preserving_prior_evidence(adaptive_popup):
    popup = adaptive_popup
    assert popup.command("shadow")
    old_path = popup.controller.sensor_log_path
    old_content = old_path.read_bytes()
    popup.controller._adaptive_log_failed = True
    popup.refresh(0)
    assert not popup.restart_button.disabled
    assert popup.restart_recorder()
    assert popup.controller.sensor_log_path != old_path
    assert old_path.read_bytes() == old_content
    assert "recording_restart" in popup.controller.sensor_log_path.read_text()
    assert "Prior evidence is preserved" in popup.message.text


def test_recorder_worker_error_is_visible_and_failed_restart_remains_actionable(adaptive_popup, monkeypatch):
    popup = adaptive_popup
    context = popup.controller.sensor_context_snapshot()
    context["recording"].update(
        write_failed=False,
        journal={"pending_records": 2, "durable": 3, "dropped": 1, "error": "disk write failed"},
    )
    monkeypatch.setattr(popup.controller, "sensor_context_snapshot", Mock(return_value=context))
    popup.refresh(0)
    assert popup.recipe_save.disabled
    assert "Queued 2; durable 3; dropped 1" in popup.path.text
    assert "disk write failed" in popup.path.text
    monkeypatch.setattr(popup.controller, "evidenceCommand", Mock(return_value=False))
    assert not popup.restart_recorder()
    assert "Recorder not restarted" in popup.message.text
    assert "pending writes" in popup.message.text
    assert not popup.restart_button.disabled
    popup.controller._evidence_writes_enabled = False
    popup.refresh(0)
    assert popup.restart_button.disabled
    assert not popup.restart_recorder()


@pytest.fixture
def boundary_popup(measurement_popup, monkeypatch):
    popup = measurement_popup
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    context = {"state": "Idle", "arrival_age_s": 0.0}
    monkeypatch.setattr(controller, "sensor_context_snapshot", lambda: dict(context))
    popup.machine.controller = controller
    yield popup, context
    popup.release_focus()
    controller.stream.send.assert_not_called()
    controller.stream = None


def declare_boundary_inputs(popup):
    popup.boundary_form.fields["reason"].text = "Checked completed probes and command queue"
    popup.boundary_check.dispatch("on_release")


def test_boundary_requires_explicit_declaration_and_fresh_connected_idle(boundary_popup):
    popup, context = boundary_popup
    popup.refresh_boundary()
    assert popup.boundary_button.disabled
    assert not popup.boundary_no_pending
    declare_boundary_inputs(popup)
    assert not popup.boundary_button.disabled
    for update in ({"state": "Run"}, {"state": "Idle", "arrival_age_s": 0.81}, {"arrival_age_s": None}):
        context.update(update)
        popup.confirm_boundary()
        assert "Not saved" in popup.status.text
        assert not popup.machine.probe_evidence.events()
    context.update(state="Idle", arrival_age_s=0)
    popup.machine.controller.sendNUM = 1
    popup.confirm_boundary()
    assert "pending program" in popup.status.text
    popup.machine.controller.sendNUM = 0
    popup.machine.controller._status_reacquire_started_at = 0.0
    popup.confirm_boundary()
    assert "Fresh Idle" in popup.status.text


def test_boundary_preserves_active_ambiguous_buffer_then_saves_durable_declaration(boundary_popup):
    popup, _context = boundary_popup
    store = popup.machine.probe_evidence
    store.begin(setup(), command="M46 first")
    store.begin(setup(), command="M46 overlapping")
    store.feed("END")
    declare_boundary_inputs(popup)
    assert popup.boundary_button.disabled
    assert not popup.close_session_button.disabled
    popup.confirm_boundary()
    assert "Preserve the active" in popup.status.text
    popup.close_session_button.dispatch("on_release")
    incomplete = store.events()[-1]
    assert incomplete["kind"] == "measurement" and incomplete["result_kind"] == "incomplete"
    assert incomplete["attribution_ambiguous"] is True
    assert not store.attribution_status()["active_session"]
    assert store.attribution_status()["attribution_ambiguous"]
    assert not popup.boundary_button.disabled
    popup.boundary_button.dispatch("on_release")
    receipt = store.events()[-1]
    assert receipt["kind"] == "attribution_boundary"
    assert receipt["machine_idle"] is True and receipt["pending_commands"] == 0
    assert "operator declaration" in receipt["evidence_class"]
    assert not store.attribution_status()["attribution_ambiguous"]
    assert not ProbeEvidenceStore(store.path).attribution_status()["attribution_ambiguous"]
    assert store._event(incomplete["id"], "measurement")["attribution_ambiguous"] is True
    assert not popup.boundary_no_pending
    assert popup.boundary_button.disabled


def test_failed_boundary_append_retains_ambiguity_and_reports_failure(boundary_popup, monkeypatch):
    popup, _context = boundary_popup
    store = popup.machine.probe_evidence
    store.begin(setup(), command="M46 first")
    store.begin(setup(), command="M46 overlapping")
    store.capture("incomplete", {"reason": "Explicit test close"})
    declare_boundary_inputs(popup)
    monkeypatch.setattr(store, "append", Mock(side_effect=OSError("disk unavailable")))
    popup.confirm_boundary()
    assert "Not saved" in popup.status.text and "disk unavailable" in popup.status.text
    assert store.attribution_status()["attribution_ambiguous"]
    assert popup.boundary_no_pending


def test_recording_caption_is_concise_and_full_location_can_be_copied(adaptive_popup, monkeypatch):
    from kivy.core.clipboard import Clipboard

    popup = adaptive_popup
    assert popup.command("shadow")
    path = popup.controller.sensor_log_path
    assert path.name in popup.path.text
    assert str(path.parent) not in popup.path.text
    copy = Mock()
    monkeypatch.setattr(Clipboard, "copy", copy)
    popup.copy_path_button.dispatch("on_release")
    copy.assert_called_once_with(str(path))
    assert "location copied" in popup.message.text


@pytest.mark.parametrize(
    "action,receipt_kind", [("confirm_boundary", "attribution_boundary"), ("close_unfinished_session", "measurement")]
)
def test_boundary_append_finishes_before_concurrent_controller_query_can_send(
    boundary_popup, monkeypatch, action, receipt_kind
):
    import threading

    popup, _context = boundary_popup
    controller = popup.machine.controller
    store = popup.machine.probe_evidence
    if action == "close_unfinished_session":
        store.begin(setup(), command="M46 test session")
    declare_boundary_inputs(popup)
    attempted = threading.Event()
    appended = threading.Event()
    original_lock = controller._adaptive_lock
    original_append = store.append
    results = []
    worker = None

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "competing-controller-query":
                attempted.set()
            original_lock.acquire()
            return self

        def __exit__(self, *_args):
            original_lock.release()

    monkeypatch.setattr(controller, "_adaptive_lock", ObservedLock())

    def on_send(_payload):
        assert appended.is_set(), "Controller sent while the boundary receipt was still pending"

    controller.stream.send.side_effect = on_send

    def competing_query():
        results.append(controller.executeCommand("version"))

    def instrumented_append(kind, **fields):
        nonlocal worker
        if kind == receipt_kind:
            worker = threading.Thread(target=competing_query, name="competing-controller-query")
            worker.start()
            assert attempted.wait(1), "Competing command did not reach the actual Controller lock"
            controller.stream.send.assert_not_called()
            receipt = original_append(kind, **fields)
            appended.set()
            return receipt
        return original_append(kind, **fields)

    monkeypatch.setattr(store, "append", instrumented_append)
    getattr(popup, action)()
    assert worker is not None
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert results == [True]
    controller.stream.send.assert_called_once()
    assert appended.is_set()
    # This one deliberate competing query used Mock transport only. The
    # fixture continues asserting that no other UI action sends a command.
    controller.stream.send.reset_mock()
