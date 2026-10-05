import threading
import time
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_surface_measurement import SurfaceMeasurementReview
from carveracontroller.machine.scene_interaction import SurfaceHit
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, summary
from tests.integration import test_setup_editor
from tests.integration.conftest import pump_frames


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    yield from test_setup_editor.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch)


def settle(workspace):
    deadline = time.monotonic() + 5
    while getattr(workspace, "inspection_busy", False) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not getattr(workspace, "inspection_busy", False)


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert predicate()


@pytest.mark.usefixtures("setup_workspace")
def test_nominal_feature_save_receipts_reload_and_no_machine_commands(setup_workspace, tmp_path, monkeypatch):
    ws, send = setup_workspace
    store = SurfaceInspectionStore(tmp_path / "inspections.json")
    monkeypatch.setattr(ws, "surface_inspection_store", store, raising=False)
    ref = SurfaceHit("stock", "stock", 0, 10, (1, 2, 3), (1, 2, 3), (0, 0, 1), ((0, 0, 3), (10, 0, 3), (0, 10, 3)))
    monkeypatch.setattr(ws.scene_interaction, "selected_surface", Mock(return_value=ref))
    plan = SurfaceMeasurementReview(ws.scene_interaction)
    plan.save_feature()
    settle(ws)
    assert not store.features
    assert "part" in plan.save_note.text
    plan.part.text = "part-A"
    plan.lower.text = "-0.002 in"
    plan.upper.text = "0.002 in"
    plan.save_feature()
    plan.save_feature()  # A second gesture cannot duplicate an in-flight feature.
    settle(ws)
    assert len(store.features) == 1
    review = ws.surface_inspection_review
    identity = store.features[0]["id"]
    assert store.get(identity)["limits_mm"] == pytest.approx((-0.0508, 0.0508))
    for field, value in zip(review.positions, (1, 2, 4.02)):
        field.text = f"{value} mm"
    review.references["source_ref"].text = "receipt-1"
    review.record()
    review.record()
    settle(ws)
    assert "1 unevaluated" in review.report.text
    review.references["registration_ref"].text = "registration-A"
    review.references["calibration_ref"].text = "calibration-A"
    review.references["source_ref"].text = "receipt-2"
    review.record()
    settle(ws)
    assert "1 evaluated" in review.report.text
    assert "within declared limits" in review.report.text
    for field, value in zip(review.positions, (1, 2, 4.1)):
        field.text = f"{value} mm"
    review.references["source_ref"].text = "receipt-3"
    review.record()
    settle(ws)
    assert "1 outside declared limits" in review.report.text
    restored = SurfaceInspectionStore(store.path)
    assert summary(restored.get(identity))["recorded"] == 3
    assert summary(restored.get(identity))["unevaluated"] == 1
    other = store.create(plan.plan, part="part-B", name="Other feature", context={})
    review.choices["part-B · Other feature"] = other
    review.selector.values = tuple(review.choices)
    original_choice = review.selector.text
    review.selector.text = "part-B · Other feature"
    assert all(field.text == "" for field in (*review.positions, *review.references.values()))
    assert "0 receipts" in review.report.text
    review.selector.text = original_choice
    assert "3 receipts" in review.report.text
    review.reload()
    settle(ws)
    assert "Reloaded retained" in review.note.text
    assert review.store is not store
    assert "3 receipts" in review.report.text
    from kivy.core.window import Window

    pump_frames(5)
    Window.screenshot(name="/tmp/carvera-surface-inspection-wide.png")
    original_size = Window.system_size
    try:
        Window.size = (560, 700)
        pump_frames(5)
        assert all(p.width <= review.popup.width for p in review.positions)
        assert review.report.width <= review.popup.width
        pump_frames(10, sleep=0.02)
        Window.screenshot(name="/tmp/carvera-surface-inspection-narrow.png")
    finally:
        Window.size = original_size
        pump_frames(3)
    review.popup_close()
    send.assert_not_called()


def test_first_load_runs_off_ui_thread_and_closed_loader_does_not_reopen(setup_workspace, tmp_path, monkeypatch):
    from kivy.core.window import Window

    from carveracontroller import desktop_surface_inspection as module

    ws, send = setup_workspace
    monkeypatch.delattr(ws, "surface_inspection_store", raising=False)
    previous = getattr(ws, "surface_inspection_review", None)
    started, release = threading.Event(), threading.Event()
    threads = []
    loaded = SurfaceInspectionStore(tmp_path / "load.json")

    def load():
        threads.append(threading.get_ident())
        started.set()
        assert release.wait(5)
        return loaded

    monkeypatch.setattr(module, "SurfaceInspectionStore", load)
    assert module.open_surface_inspections(ws) is None
    wait_for(started.is_set)
    assert threads == [threads[0]] and threads[0] != threading.get_ident()
    loading = Window.children[0]
    assert "Loading retained" in loading.content.text
    loading.dismiss()
    release.set()
    settle(ws)
    assert ws.surface_inspection_store is loaded
    assert getattr(ws, "surface_inspection_review", None) is previous
    send.assert_not_called()


def test_closing_during_save_retains_feature_without_reopening_review(setup_workspace, tmp_path, monkeypatch):
    ws, send = setup_workspace
    store = SurfaceInspectionStore(tmp_path / "close.json")
    monkeypatch.setattr(ws, "surface_inspection_store", store, raising=False)
    previous = getattr(ws, "surface_inspection_review", None)
    ref = SurfaceHit("stock", "stock", 0, 10, (1, 2, 3), (1, 2, 3), (0, 0, 1), ((0, 0, 3), (10, 0, 3), (0, 10, 3)))
    monkeypatch.setattr(ws.scene_interaction, "selected_surface", Mock(return_value=ref))
    started, release = threading.Event(), threading.Event()
    create = store.create

    def slow_create(*args, **kwargs):
        assert threading.current_thread() is not threading.main_thread()
        started.set()
        assert release.wait(5)
        return create(*args, **kwargs)

    monkeypatch.setattr(store, "create", slow_create)
    plan = SurfaceMeasurementReview(ws.scene_interaction)
    plan.part.text = "retained-after-close"
    plan.open()
    plan.save_feature()
    wait_for(started.is_set)
    assert plan.save_button.disabled
    plan.close()
    release.set()
    settle(ws)
    assert len(SurfaceInspectionStore(store.path).features) == 1
    assert getattr(ws, "surface_inspection_review", None) is previous
    assert not plan.save_button.disabled
    send.assert_not_called()


def test_export_picker_readback_and_reviewed_import(setup_workspace, tmp_path, monkeypatch):
    from carveracontroller.desktop_surface_inspection import open_surface_inspections
    from carveracontroller.machine.surface_inspection_exchange import read_bundle
    from tests.unit.test_surface_inspection import feature, receipt

    ws, send = setup_workspace
    store = SurfaceInspectionStore(tmp_path / "source.json")
    identity = feature(store)
    receipt(store, identity, 4.01)
    monkeypatch.setattr(ws, "surface_inspection_store", store, raising=False)
    selections = []
    monkeypatch.setattr(ws, "choose_profile_file", lambda callback, **options: selections.append((callback, options)))
    review = open_surface_inspections(ws, identity)
    review.export()
    callback, options = selections.pop()
    assert options["extension"] == ".cvinspect" and options["save"]
    portable = tmp_path / "portable.cvinspect"
    callback(portable)
    settle(ws)
    exported = ws.last_inspection_export
    assert exported["features"] == exported["receipts"] == 1
    assert read_bundle(portable.read_bytes())[0]["id"] == identity
    assert "read back" in review.note.text
    for format_name, extension in (("HTML report", ".html"), ("CSV", ".csv")):
        review.export_format.text = format_name
        review.export()
        callback, options = selections.pop()
        assert options["extension"] == extension
        callback(tmp_path / ("report" + extension))
        settle(ws)
        assert ws.last_inspection_export["format"] == format_name
    second = feature(store)
    review.export_format.text = "Portable JSON"
    review.export_scope.text = "All features"
    review.export()
    callback, _ = selections.pop()
    all_features = tmp_path / "all.cvinspect"
    callback(all_features)
    settle(ws)
    assert ws.last_inspection_export["features"] == 2
    assert {f["id"] for f in read_bundle(all_features.read_bytes())} == {identity, second}
    review.popup_close()
    dest = SurfaceInspectionStore(tmp_path / "destination.json")
    monkeypatch.setattr(ws, "surface_inspection_store", dest)
    review = open_surface_inspections(ws)
    review.import_bundle()
    callback, options = selections.pop()
    assert options["extension"] == ".cvinspect"
    callback(portable)
    settle(ws)
    assert not dest.path.exists()
    assert review.import_review_popup._is_open
    review.apply_import()
    review.apply_import()
    settle(ws)
    assert len(dest.features) == 1
    assert dest.get(identity)["samples"] == store.get(identity)["samples"]
    assert ws.last_inspection_import["features_added"] == 1
    assert "1 receipts" in review.report.text
    review.popup_close()
    send.assert_not_called()


def test_closed_records_do_not_open_completed_import_review(setup_workspace, tmp_path, monkeypatch):
    from carveracontroller import desktop_surface_inspection as ui
    from carveracontroller.machine import surface_inspection_exchange as exchange

    ws, send = setup_workspace
    store = SurfaceInspectionStore(tmp_path / "empty.json")
    monkeypatch.setattr(ws, "surface_inspection_store", store, raising=False)
    selections = []
    monkeypatch.setattr(ws, "choose_profile_file", lambda cb, **kwargs: selections.append(cb))
    target = tmp_path / "empty.cvinspect"
    target.write_text(exchange.bundle([]))
    original = exchange.preview_import
    started, release = threading.Event(), threading.Event()

    def slow_review(*args):
        started.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(exchange, "preview_import", slow_review)
    review = ui.open_surface_inspections(ws)
    review.import_bundle()
    selections.pop()(target)
    wait_for(started.is_set)
    review.popup_close()
    release.set()
    settle(ws)
    assert getattr(review, "import_review_popup", None) is None
    assert not store.path.exists()
    send.assert_not_called()
