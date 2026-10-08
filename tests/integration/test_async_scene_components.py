"""Component file preparation is asynchronous and guarded by its scene context."""

import copy
import threading
import time
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.desktop_scene import capture_scene_setup, restore_scene_geometry
from tests.integration.conftest import pump_frames
from tests.unit.test_machine_profile import profile_data


def settle(ws):
    deadline = time.monotonic() + 4
    while any(lane["active"] for lane in ws.scene_component_loads.lanes.values()) and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not any(lane["active"] for lane in ws.scene_component_loads.lanes.values())


@pytest.fixture
def component_case(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    old_library = copy.deepcopy(ws.scene_library.data)
    old_components = dict(viewer.machine_component_profiles)
    old_setup = capture_scene_setup(ws)
    monkeypatch.setattr(ws, "save_scene_setup", Mock(return_value=True))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    data = profile_data()
    for kind in ("fixture", "workholding"):
        data["components"].append({"group": kind, "vertices": list(data["components"][0]["vertices"])})
    cad = MachineProfile(data)
    ws.scene_library.data["fixtures"].append({"name": "Async plate", "path": "/tmp/async-plate.json.gz"})
    ws.scene_library.data["vises"].append({"name": "Async vise", "path": "/tmp/async-vise.json.gz"})
    yield ws, viewer, cad, send
    for kind in ws.scene_component_loads.lanes:
        ws.scene_component_loads.invalidate(kind)
    settle(ws)
    ws.scene_library.data = old_library
    ws.seed_scene_choices(ws.selected_machine_profile)
    restore_scene_geometry(ws, old_setup)
    viewer.machine_component_profiles = old_components
    viewer._build_machine_scene()
    settle(ws)


def test_blocked_selection_keeps_clock_and_previous_geometry_then_publishes_on_ui(component_case, monkeypatch):
    ws, viewer, cad, send = component_case
    entered, release = threading.Event(), threading.Event()
    previous = dict(viewer.machine_component_profiles)
    ui = threading.get_ident()

    def load(*args):
        assert threading.get_ident() != ui
        entered.set()
        assert release.wait(3)
        return cad

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    publish = Mock(wraps=viewer.select_machine_component)
    monkeypatch.setattr(viewer, "select_machine_component", publish)
    try:
        ws.component_choices["fixture"].text = "Async plate"
        assert entered.wait(1)
        assert viewer.machine_component_profiles == previous
        ticks = []
        Clock.schedule_once(lambda dt: ticks.append(dt), 0)
        pump_frames(3)
        assert ticks and "Preparing" in ws.scene_component_note.text
        publish.assert_not_called()
    finally:
        release.set()
    settle(ws)
    publish.assert_called_once_with("fixture", cad)
    assert viewer.machine_component_profiles["fixture"] is cad
    assert "CAD loaded" in ws.scene_component_note.text
    send.assert_not_called()


@pytest.mark.parametrize("change", ["setup", "selection"])
def test_stale_or_superseded_component_does_not_publish(component_case, monkeypatch, change):
    ws, viewer, cad, send = component_case
    entered, release = threading.Event(), threading.Event()

    def load(*args):
        entered.set()
        assert release.wait(3)
        return cad

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    publish = Mock(wraps=viewer.select_machine_component)
    monkeypatch.setattr(viewer, "select_machine_component", publish)
    try:
        ws.component_choices["fixture"].text = "Async plate"
        assert entered.wait(1)
        if change == "setup":
            viewer.configure_workholding((1, 2, 3))
        else:
            ws.component_choices["fixture"].text = "Current model"
    finally:
        release.set()
    settle(ws)
    publish.assert_not_called()
    if change == "setup":
        assert "Setup changed" in ws.scene_component_note.text
    send.assert_not_called()


def test_import_registers_only_after_worker_success(component_case, monkeypatch):
    ws, viewer, cad, send = component_case
    callbacks = []
    monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **kwargs: callbacks.append(callback))
    monkeypatch.setattr(MachineProfile, "reuse_or_load", lambda *args: cad)
    registered = []
    monkeypatch.setattr(ws.scene_library, "save", lambda kind, record: registered.append((kind, record)))
    ws.component_choices["fixture"].text = "Import registered CAD…"
    assert len(callbacks) == 1 and not registered
    callbacks[0]("/tmp/imported-plate.json.gz")
    settle(ws)
    assert registered == [("fixtures", {"name": "imported-plate", "path": "/tmp/imported-plate.json.gz"})]
    assert ws.component_choices["fixture"].text == "imported-plate"
    assert viewer.machine_component_profiles["fixture"] is cad
    send.assert_not_called()


@pytest.mark.parametrize("fixture_fails", [False, True])
def test_independent_component_feedback_retains_pending_and_errors(component_case, monkeypatch, fixture_fails):
    ws, viewer, cad, send = component_case
    entered, release = threading.Event(), threading.Event()

    def load(path, *_args):
        if "vise" in path:
            entered.set()
            assert release.wait(3)
        elif fixture_fails:
            raise ValueError("plate checksum rejected")
        return cad

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    try:
        ws.component_choices["workholding"].text = "Async vise"
        assert entered.wait(1)
        ws.component_choices["fixture"].text = "Async plate"
        deadline = time.monotonic() + 2
        while ws.scene_component_loads.lanes["fixture"]["active"] and time.monotonic() < deadline:
            pump_frames(2, sleep=0.01)
        assert not ws.scene_component_loads.lanes["fixture"]["active"]
        assert "Preparing Async vise" in ws.scene_component_note.text
        if fixture_fails:
            assert "plate checksum rejected" in ws.scene_component_note.text
        else:
            assert viewer.machine_component_profiles["fixture"] is cad
    finally:
        release.set()
    settle(ws)
    assert "Preparing" not in ws.scene_component_note.text
    assert viewer.machine_component_profiles["workholding"] is cad
    if fixture_fails:
        assert "plate checksum rejected" in ws.scene_component_note.text
    send.assert_not_called()


def test_custom_saved_component_prepares_after_numeric_setup_restoration(component_case, monkeypatch):
    ws, viewer, cad, send = component_case
    saved = capture_scene_setup(ws)
    saved["choices"]["fixture"] = "Async plate"
    saved["work_offset_mm"] = [11, 12, 13]
    saved["workholding_offset_mm"] = [4, 5, 6]
    saved["workholding_rotation_deg"] = 27
    saved["jaw_offset_mm"] = 8
    monkeypatch.setattr(ws.scene_setup_store, "get", lambda _id: copy.deepcopy(saved))
    monkeypatch.setattr(MachineProfile, "reuse_or_load", lambda *_args: cad)
    prepared = Mock(wraps=cad.prepare_render_buffers)
    monkeypatch.setattr(cad, "prepare_render_buffers", prepared)
    ws.seed_scene_choices({"id": "restored-test", "cad_path": ""})
    assert not prepared.called
    pump_frames(2)
    settle(ws)
    assert viewer.machine_component_profiles["fixture"] is cad
    frame, _scale, placement = prepared.call_args[0]
    assert tuple(frame) == (11, 12, 13)
    assert tuple(placement[0]) == (4, 5, 6)
    assert placement[1:] == (27, 8)
    send.assert_not_called()
