"""Profile preparation remains responsive and rejects superseded scene publications."""

import threading
import time
from unittest.mock import Mock

import pytest

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from tests.integration.conftest import pump_frames


def settle(ws):
    deadline = time.monotonic() + 4
    while ws._profile_load_active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not ws._profile_load_active


@pytest.fixture
def selection(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    publish = Mock()
    monkeypatch.setattr(ws, "_publish_machine_profile", publish)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    status = ws.profile_status.text
    yield ws, publish, send
    settle(ws)
    ws.profile_status.text = status
    ws._profile_load_closed = False
    ws.machine_profile_loading = False


def test_blocked_preparation_keeps_clock_and_previous_scene(selection, monkeypatch):
    ws, publish, send = selection
    entered, release = threading.Event(), threading.Event()
    prepared = object()
    previous = ws.machine.gcode_viewer.machine_profile
    active = ws.selected_machine_profile

    def load(*args):
        entered.set()
        assert release.wait(3)
        return prepared

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    done = Mock()
    try:
        assert ws.request_machine_profile(
            {"id": "profile-test", "name": "Slow CAD", "cad_path": "/tmp/slow-cad.gz"}, done
        )
        assert entered.wait(1)
        assert ws.machine_profile_loading
        assert "Preparing Slow CAD" in ws.profile_status.text
        clock = Mock()
        from kivy.clock import Clock

        Clock.schedule_once(lambda dt: clock(), 0)
        pump_frames(3)
        clock.assert_called_once()
        assert ws.machine.gcode_viewer.machine_profile is previous
        assert ws.selected_machine_profile is active
        publish.assert_not_called()
    finally:
        release.set()
    settle(ws)
    assert publish.call_args.args[1] is prepared
    done.assert_called_once_with(True, None)
    send.assert_not_called()


def test_only_latest_pending_selection_is_prepared_and_published(selection, monkeypatch):
    ws, publish, send = selection
    entered, release = threading.Event(), threading.Event()
    paths = []

    def load(path, previous):
        paths.append(str(path))
        if len(paths) == 1:
            entered.set()
            assert release.wait(3)
        return str(path)

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    try:
        ws.request_machine_profile({"id": "profile-test", "name": "First", "cad_path": "/tmp/first.gz"})
        assert entered.wait(1)
        ws.request_machine_profile({"id": "profile-test", "name": "Middle", "cad_path": "/tmp/middle.gz"})
        ws.request_machine_profile({"id": "profile-test", "name": "Last", "cad_path": "/tmp/last.gz"})
        assert ws._profile_load_pending[1]["name"] == "Last"
    finally:
        release.set()
    settle(ws)
    assert paths == ["/tmp/first.gz", "/tmp/last.gz"]
    assert publish.call_count == 1
    assert publish.call_args.args[0]["name"] == "Last"
    send.assert_not_called()


def test_invalid_asset_preserves_active_selection_and_reports_failure(selection, monkeypatch):
    ws, publish, send = selection
    active = ws.selected_machine_profile
    cad = ws.machine.gcode_viewer.machine_profile
    monkeypatch.setattr(MachineProfile, "reuse_or_load", Mock(side_effect=ValueError("Invalid CAD triangles")))
    done = Mock()
    ws.request_machine_profile({"id": "profile-test", "name": "Broken", "cad_path": "/tmp/broken.gz"}, done)
    settle(ws)
    assert ws.selected_machine_profile is active
    assert ws.machine.gcode_viewer.machine_profile is cad
    publish.assert_not_called()
    done.assert_called_once_with(False, "Invalid CAD triangles")
    assert "Profile not loaded" in ws.profile_status.text
    send.assert_not_called()


@pytest.mark.parametrize("change", ["scene", "closed"])
def test_changed_scene_or_disposed_owner_rejects_late_result(selection, monkeypatch, change):
    ws, publish, send = selection
    entered, release = threading.Event(), threading.Event()

    def load(*args):
        entered.set()
        assert release.wait(3)
        return object()

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    old_rotation = ws.machine.gcode_viewer.workholding_rotation_deg
    done = Mock()
    try:
        ws.request_machine_profile({"id": "profile-test", "name": "Late", "cad_path": "/tmp/late.gz"}, done)
        assert entered.wait(1)
        if change == "scene":
            ws.machine.gcode_viewer.workholding_rotation_deg = old_rotation + 15
        else:
            ws._profile_load_closed = True
            ws._profile_load_generation += 1
            ws._profile_load_pending = None
            ws.machine_profile_loading = False
    finally:
        release.set()
    settle(ws)
    ws.machine.gcode_viewer.workholding_rotation_deg = old_rotation
    publish.assert_not_called()
    if change == "scene":
        assert "Scene changed" in done.call_args.args[1]
    else:
        done.assert_not_called()
    send.assert_not_called()


def test_startup_restoration_requests_preparation_without_synchronous_publication(selection, monkeypatch):
    from kivy.config import Config

    ws, publish, send = selection
    record = {"id": "startup-profile", "name": "Startup", "cad_path": "/tmp/startup.gz"}
    monkeypatch.setattr(ws, "profile_store", Mock(data={"machines": [record], "toolsets": []}))
    original_get = Config.get

    def selected(section, name, **kwargs):
        if name == "desktop_machine_profile_id":
            return "startup-profile"
        if name == "desktop_toolset_id":
            return ""
        return original_get(section, name, **kwargs)

    monkeypatch.setattr(Config, "get", selected)
    request = Mock()
    monkeypatch.setattr(ws, "request_machine_profile", request)
    ws._restore_profiles()
    request.assert_called_once_with(record)
    publish.assert_not_called()
    send.assert_not_called()


def test_library_does_not_claim_loaded_before_preparation_finishes(selection, tmp_path, monkeypatch):
    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore

    ws, publish, send = selection
    store = ProfileStore(tmp_path / "library.json")
    record = store.save_machine({"name": "Library preparation", "cad_path": "/tmp/library.gz"})
    library = ProfileLibrary(ws, store=store)
    library._edit(record)
    request = Mock()
    monkeypatch.setattr(ws, "request_machine_profile", request)
    library.apply()
    assert "Preparing" in library.status.text and "Loaded" not in library.status.text
    callback = request.call_args.args[1]
    callback(False, "Invalid CAD")
    assert library.status.text == "Profile not loaded: Invalid CAD"
    callback(True, None)
    assert "Loaded Library preparation" in library.status.text
    library.selected_id = "other-profile"
    library.status.text = "Other draft"
    callback(True, None)
    assert library.status.text == "Other draft"
    publish.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("visible", [True, False])
def test_prepared_real_profile_publishes_saved_components_on_ui_clock(selection, tmp_path, monkeypatch, visible):
    import gzip
    import json

    from tests.unit.test_machine_profile import profile_data

    ws, publish, send = selection
    viewer = ws.machine.gcode_viewer
    prior = (
        ws.selected_machine_profile,
        viewer.machine_profile,
        viewer.machine_setup,
        dict(viewer.machine_component_profiles),
    )
    data = profile_data()
    for group in ("fixture", "workholding"):
        data["components"].append({"group": group, "vertices": list(data["components"][0]["vertices"])})
    path = tmp_path / "saunders-async.json.gz"
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    previous_visibility = viewer.machine_visible
    viewer.set_machine_visible(visible)
    build = Mock(wraps=viewer._build_machine_scene)
    monkeypatch.setattr(viewer, "_build_machine_scene", build)
    ui_thread = threading.get_ident()

    def actual(profile, cad):
        assert threading.get_ident() == ui_thread
        type(ws)._publish_machine_profile(ws, profile, cad)

    publish.side_effect = actual
    done = Mock()
    try:
        ws.request_machine_profile({"id": "actual-async", "name": "Async assembly", "cad_path": str(path)}, done)
        settle(ws)
        done.assert_called_once_with(True, None)
        assert ws.selected_machine_profile["name"] == "Async assembly"
        assert viewer.machine_profile.asset_path == str(path.resolve())
        assert viewer.machine_component_profiles["fixture"] is viewer.machine_profile
        assert viewer.machine_component_profiles["workholding"] is viewer.machine_profile
        assert "Async assembly" in ws.profile_status.text
        assert not ws.machine_profile_loading
        assert viewer.machine_visible is visible
        assert build.call_count == (1 if visible else 0)
        send.assert_not_called()
    finally:
        ws.selected_machine_profile, viewer.machine_profile, viewer.machine_setup, viewer.machine_component_profiles = (
            prior
        )
        viewer.set_machine_visible(previous_visibility)
        viewer._build_machine_scene()


def test_synchronous_selection_invalidates_older_preparation(selection, monkeypatch):
    ws, publish, send = selection
    entered, release = threading.Event(), threading.Event()

    def load(*args):
        entered.set()
        assert release.wait(3)
        return object()

    monkeypatch.setattr(MachineProfile, "reuse_or_load", load)
    done = Mock()
    try:
        ws.request_machine_profile({"id": "older", "name": "Older", "cad_path": "/tmp/older.gz"}, done)
        assert entered.wait(1)
        ws.apply_machine_profile({"id": "direct", "name": "Direct"})
        assert not ws.machine_profile_loading
    finally:
        release.set()
    settle(ws)
    assert publish.call_count == 1
    assert publish.call_args.args[0]["name"] == "Direct"
    done.assert_not_called()
    send.assert_not_called()


def test_closed_workspace_does_not_leave_library_showing_preparing(selection, tmp_path, monkeypatch):
    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore

    ws, publish, send = selection
    store = ProfileStore(tmp_path / "closed-library.json")
    record = store.save_machine({"name": "Retained draft"})
    library = ProfileLibrary(ws, store=store)
    library._edit(record)
    monkeypatch.setattr(ws, "_profile_load_closed", True)
    library.apply()
    assert library.status.text == "Workspace closed; profile saved but not loaded."
    assert not ws._profile_load_active
    publish.assert_not_called()
    send.assert_not_called()


def test_publication_failure_restores_visible_scene(selection, monkeypatch):
    ws, publish, send = selection
    viewer = ws.machine.gcode_viewer
    previous = viewer.machine_visible
    viewer.set_machine_visible(True)
    build = Mock(wraps=viewer._build_machine_scene)
    monkeypatch.setattr(viewer, "_build_machine_scene", build)
    monkeypatch.setattr(ws, "_publish_machine_profile_selection", Mock(side_effect=ValueError("Rejected selection")))
    try:
        with pytest.raises(ValueError, match="Rejected selection"):
            type(ws)._publish_machine_profile(ws, {}, None)
        assert viewer.machine_visible
        assert build.call_count == 1
        send.assert_not_called()
    finally:
        viewer.set_machine_visible(previous)
