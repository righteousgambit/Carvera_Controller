"""Actual shaped stock survives desktop import, restore and portable job paths."""

import copy
import threading
import time
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.popup import Popup

from carveracontroller.addons.machine_simulation.stock_model import StockModel, initial_stock
from carveracontroller.desktop_components import Action, Choice
from carveracontroller.desktop_job_packages import capture_job, prepare_job_preview
from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup, restore_scene_geometry
from carveracontroller.machine.geometry_changes import asset_problems, capture_context, verify_context_assets
from carveracontroller.machine.job_packages import load_package, resolve_setup_assets, save_package
from tests.integration.conftest import pump_frames
from tests.integration.test_async_scene_components import component_case as _component_case
from tests.unit.test_stock_solid import l_stock, mesh


@pytest.fixture
def stock_case(kivy_app, monkeypatch):
    from carveracontroller.desktop_view_state import capture_view, restore_view

    generator = _component_case.__wrapped__(kivy_app, monkeypatch)
    case = next(generator)
    visible, view = case[1].machine_visible, capture_view(case[1])
    yield case
    settle(case[0])
    case[1].set_machine_visible(visible)
    try:
        next(generator)
    except StopIteration:
        pass
    restore_view(case[1], view)


def settle(ws):
    deadline = time.monotonic() + 30
    while any(lane["active"] for lane in ws.scene_component_loads.lanes.values()) and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not any(lane["active"] for lane in ws.scene_component_loads.lanes.values()), ws.scene_component_note.text


def stock_record(tmp_path):
    source = mesh(tmp_path, l_stock())
    return {"name": "Shaped L stock", "source_path": source.source_path, "source_units": "mm"}


@pytest.mark.parametrize("change", ["complete", "cancel", "placement", "bytes"])
def test_stock_preparation_keeps_ui_live_and_rejects_late_or_changed_input(stock_case, tmp_path, monkeypatch, change):
    ws, viewer, _cad, send = stock_case
    record = stock_record(tmp_path)
    previous = viewer.machine_setup
    registered = []
    monkeypatch.setattr(ws.scene_library, "save", lambda kind, value: registered.append((kind, value)))
    entered, release = threading.Event(), threading.Event()
    original = StockModel.load
    ui = threading.get_ident()

    def load(cls, *args, **kwargs):
        assert threading.get_ident() != ui
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(30)
        return result

    monkeypatch.setattr(StockModel, "load", classmethod(load))
    try:
        ws.prepare_stock_model(record)
        assert entered.wait(20)
        tick = []
        Clock.schedule_once(lambda dt: tick.append(dt), 0)
        pump_frames(3)
        assert tick and viewer.machine_setup is previous and not registered
        assert not ws.stock_import_cancel.disabled
        if change == "cancel":
            ws.stock_import_cancel.dispatch("on_release")
        elif change == "placement":
            viewer.configure_machine(work_offset_mm=(1, 2, 3), stock_size_mm=previous.stock_size_mm)
        elif change == "bytes":
            from pathlib import Path

            Path(record["source_path"]).write_bytes(b"changed input")
    finally:
        release.set()
    settle(ws)
    if change == "complete":
        assert len(registered) == 1
        assert registered[0][1]["source"]["source_sha256"] == viewer.machine_setup.stock_model.source_sha256
        assert viewer.machine_setup.stock_model.solid.material_volume_mm3 == 10
        assert len(viewer.machine_setup.stock_mesh().indices) == len(l_stock()) * 3
        assert "Stock mesh loaded" in ws.scene_component_note.text
    else:
        assert not registered
        assert viewer.machine_setup.stock_model is previous.stock_model
        if change == "bytes":
            assert "changed" in ws.scene_component_note.text
        elif change == "placement":
            assert "Setup changed" in ws.scene_component_note.text
    assert ws.stock_import_cancel.disabled
    send.assert_not_called()


def test_import_dialog_requires_units_before_any_worker(stock_case, tmp_path, monkeypatch):
    ws, viewer, _cad, send = stock_case
    record = stock_record(tmp_path)
    callbacks = []
    monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **kw: callbacks.append((callback, kw)))
    load = Mock()
    monkeypatch.setattr(ws, "prepare_stock_model", load)
    # The dialog captures the local preparation function, so observe its lane too.
    ws.component_choices["stock"].text = "Import stock STL…"
    callbacks[0][0](record["source_path"])
    pump_frames(3)
    popup = next(child for child in Window.children if isinstance(child, Popup) and child.title == "Import stock STL")
    generation = ws.scene_component_loads.lanes["stock"]["generation"]
    try:
        widgets = list(popup.content.walk())
        units = next(w for w in widgets if isinstance(w, Choice) and w.text == "Choose source units")
        apply = next(w for w in widgets if isinstance(w, Action) and w.text == "Load stock model")
        assert units.values == ["Millimetres (mm)", "Inches (inch)"] or tuple(units.values) == (
            "Millimetres (mm)",
            "Inches (inch)",
        )
        apply.dispatch("on_release")
        assert ws.scene_component_loads.lanes["stock"]["generation"] == generation
        assert popup.parent is not None
        assert any("explicitly choose" in getattr(w, "text", "") for w in widgets)
    finally:
        popup.dismiss()
    send.assert_not_called()


def test_scene_store_roundtrip_restores_shape_without_a_placeholder_block(stock_case, tmp_path, monkeypatch):
    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    saved = capture_scene_setup(ws)
    store = SceneSetupStore(tmp_path / "scene.json")
    store.save("shaped", saved)
    loaded = SceneSetupStore(store.path).get("shaped")
    assert loaded["stock_source"] == saved["stock_source"]
    viewer.configure_machine(stock_size_mm=(9, 9, 9), stock_model=None)
    restore_scene_geometry(ws, loaded)
    assert viewer.machine_setup.stock_size_mm is None
    assert viewer.machine_setup.stock_model is None
    pump_frames(2)
    settle(ws)
    assert viewer.machine_setup.stock_model.source_sha256 == saved["stock_source"]["source_sha256"]
    assert initial_stock(viewer.machine_setup, 0.5).remaining_volume_mm3 == 10
    send.assert_not_called()


def test_portable_job_retains_source_shape_after_original_is_removed(stock_case, tmp_path, monkeypatch):
    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    program = tmp_path / "shape.cnc"
    program.write_bytes(b"G21 G90 G17 G94\nT1 M6\nG1 X1 F100\n")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(program))
    monkeypatch.setattr(ws, "selected_machine_profile", None)
    monkeypatch.setattr(ws, "loaded_toolset", None)
    monkeypatch.setattr(ws, "profile_store", None)
    monkeypatch.setattr(ws, "restored_job", None, raising=False)
    monkeypatch.setattr(ws, "simulation_panel", None)
    monkeypatch.setattr(ws, "camera_registration_panel", None)
    monkeypatch.setattr(viewer, "machine_component_profiles", {})
    job = capture_job(ws)
    reference = copy.deepcopy(job.stock["stock_source"])
    archive = save_package(job, tmp_path / "shape.cvjob")
    from pathlib import Path

    Path(reference["source_path"]).unlink()
    loaded = load_package(archive, tmp_path / "restored")
    setup = resolve_setup_assets(loaded)
    placement, *_ = prepare_job_preview(loaded, setup, tmp_path / "restored")
    assert placement.stock_model.source_sha256 == reference["source_sha256"]
    assert placement.stock_model.source_path != reference["source_path"]
    assert initial_stock(placement, 0.5).remaining_volume_mm3 == 10
    assert len(placement.stock_mesh().indices) == len(l_stock()) * 3
    send.assert_not_called()


def test_context_tracks_changed_imported_stock_source(stock_case, tmp_path):
    ws, viewer, _cad, send = stock_case
    record = stock_record(tmp_path)
    ws.prepare_stock_model(record)
    settle(ws)
    context = capture_context(viewer, None)
    assert not asset_problems(context)
    from pathlib import Path

    Path(record["source_path"]).write_bytes(b"changed source")
    assert any("Stock source" in problem for problem in asset_problems(verify_context_assets(context)))
    send.assert_not_called()


def test_imported_stock_placement_editor_preserves_source_and_locks_dimensions(stock_case, tmp_path, monkeypatch):
    from carveracontroller.desktop_setup_editor import SetupEditor

    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    source = viewer.machine_setup.stock_model
    monkeypatch.setattr(ws, "selected_machine_profile", None)
    editor = SetupEditor(ws, "stock")
    editor.popup.open()
    try:
        pump_frames(3)
        assert all(editor.fields["stock_size_mm", axis].input.readonly for axis in range(3))
        assert all(button.disabled for axis in range(3) for button in editor.fields["stock_size_mm", axis].step_buttons)
        assert "bounding envelope" in editor.intro.text
        editor.fields["stock_origin_mm", 0].text = "4"
        assert editor.apply()
        deadline = time.monotonic() + 30
        while editor.preparing and time.monotonic() < deadline:
            pump_frames(2, sleep=0.01)
        assert not editor.preparing and editor.last_apply_result is True, editor.note.text
        assert viewer.machine_setup.stock_model is source
        assert viewer.machine_setup.stock_origin_mm == (4, 0, 0)
        assert initial_stock(viewer.machine_setup, 0.5).remaining_volume_mm3 == 10
    finally:
        editor.cancel()
    send.assert_not_called()


def test_simulation_worker_allocates_actual_initial_shape(stock_case, tmp_path, monkeypatch):
    from carveracontroller.addons.machine_simulation import stock_model
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
    from carveracontroller.machine.program_operations import ProgramOperations

    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    panel = ws.simulation_panel
    monkeypatch.setattr(viewer, "machine_profile", None)
    monkeypatch.setattr(viewer, "machine_component_profiles", {})
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=0.5, shank_diameter=0.5, flute_length=2, stickout=5)},
    )
    monkeypatch.setattr(
        ws.operation_panel, "program", ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z5\nG1 X3 F100\n")
    )
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", ".5")
    monkeypatch.setattr(panel, "rest_stock", None)
    original = stock_model.initial_stock
    observed = []
    ui = threading.get_ident()

    def allocate(*args, **kwargs):
        result = original(*args, **kwargs)
        observed.append((threading.get_ident(), result.remaining_volume_mm3))
        return result

    monkeypatch.setattr(stock_model, "initial_stock", allocate)
    panel.start(False)
    deadline = time.monotonic() + 30
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running, panel.note.text
    assert observed and observed[0] == (observed[0][0], 10) and observed[0][0] != ui
    assert panel.rest_stock is not None, panel.note.text
    assert panel.rest_stock.remaining_volume_mm3 + panel.rest_stock.removed_volume_mm3 == 10
    assert panel.rest_context["stock"]["source"]["source_sha256"] == viewer.machine_setup.stock_model.source_sha256
    send.assert_not_called()


def test_actual_mesh_render_reuses_stock_context_and_frames_selected_shape(stock_case, kivy_app, tmp_path):
    from kivy.graphics import Mesh

    from tests.integration.conftest import capture_screenshot

    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    ws.select("Scene")
    ws.scene_tasks.show("Components")
    viewer.set_machine_visible(True)
    viewer._build_machine_scene()
    expected = viewer.machine_setup.stock_mesh()
    assert viewer._machine_render_keys["stock"][0] is expected
    context = viewer._machine_contexts["stock"]
    meshes = [item for item in context.children if isinstance(item, Mesh)]
    assert sum(len(item.indices) for item in meshes if item.mode == "triangles") == len(l_stock()) * 3
    assert any(item.mode == "lines" for item in meshes)
    previous = tuple(context.children)
    viewer._build_machine_scene()
    assert tuple(context.children) == previous
    ws.object_inspector.select("stock", record=False, reveal=False)
    ws.scene_interaction.frame_selected()
    pump_frames(8)
    capture_screenshot(kivy_app, "imported-stock-source-preview")
    send.assert_not_called()
