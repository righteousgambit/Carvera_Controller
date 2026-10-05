"""Default CAD never blocks viewer construction or overrides a newer owner."""

import threading
import time
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.GcodeViewer import GCodeViewer
from tests.integration.conftest import pump_frames
from tests.unit.test_machine_profile import profile_data


def settle_default():
    deadline = time.monotonic() + 4
    while any(t.name == "default-machine-profile-prepare" for t in threading.enumerate()):
        assert time.monotonic() < deadline
        pump_frames(2, sleep=0.01)
    pump_frames(3)


@pytest.fixture
def default_viewer(kivy_app):
    viewer = GCodeViewer()
    yield viewer
    viewer.cancel_default_machine_profile()
    settle_default()
    Clock.unschedule(viewer._on_frame_tick)


def test_constructor_performs_no_default_asset_io(kivy_app, monkeypatch):
    loader = Mock(side_effect=AssertionError("Default CAD read during construction"))
    monkeypatch.setattr(MachineProfile, "load", loader)
    viewer = GCodeViewer()
    try:
        assert viewer.machine_profile is None
        assert viewer._default_profile_event is not None
        loader.assert_not_called()
        viewer.cancel_default_machine_profile()
        pump_frames(3)
        loader.assert_not_called()
    finally:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)


@pytest.mark.parametrize("changed", [None, "owner", "profile", "setup"])
def test_default_worker_keeps_clock_alive_and_respects_latest_owner(default_viewer, monkeypatch, changed):
    viewer = default_viewer
    entered, release = threading.Event(), threading.Event()
    prepared = MachineProfile(profile_data())
    ui_thread = threading.get_ident()
    worker_threads = []

    def load(path):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return prepared

    monkeypatch.setattr(MachineProfile, "load", load)
    build = Mock()
    monkeypatch.setattr(viewer, "_build_machine_scene", build)
    monkeypatch.setattr(viewer, "_fit_machine_view", Mock())
    viewer.machine_visible = True
    pump_frames(2)
    assert entered.wait(1)
    try:
        clock = Mock()
        Clock.schedule_once(lambda dt: clock(), 0)
        pump_frames(3)
        clock.assert_called_once()
        assert viewer.machine_profile is None
        assert viewer._default_profile_loading
        build.assert_not_called()
        if changed == "owner":
            viewer.cancel_default_machine_profile()
        elif changed == "profile":
            viewer.machine_profile = object()
        elif changed == "setup":
            from carveracontroller.addons.machine_simulation.model import MachineSetup

            viewer.machine_setup = MachineSetup(stock_size_mm=(10, 10, 10))
    finally:
        release.set()
    settle_default()
    assert worker_threads and worker_threads[0] != ui_thread
    assert not viewer._default_profile_loading
    if changed is None:
        assert viewer.machine_profile is prepared
        build.assert_called_once()
    else:
        assert viewer.machine_profile is not prepared
        build.assert_not_called()


@pytest.mark.parametrize("error", [FileNotFoundError("missing default"), ValueError("invalid default")])
def test_default_absence_or_invalid_asset_keeps_schematic(default_viewer, monkeypatch, error):
    viewer = default_viewer
    monkeypatch.setattr(MachineProfile, "load", Mock(side_effect=error))
    pump_frames(2)
    settle_default()
    assert viewer.machine_profile is None
    assert not viewer._default_profile_loading
    assert viewer.machine_profile_error == (None if isinstance(error, FileNotFoundError) else "invalid default")


def test_empty_selected_profile_prepares_default_without_overriding_previous(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    loader = Mock(return_value=object())
    monkeypatch.setattr(MachineProfile, "load", loader)
    record = {"cad_path": ""}
    prepared = ws._prepare_selected_profile_cad(record, None)
    assert prepared is loader.return_value
    loader.assert_called_once()
    assert ws._prepare_selected_profile_cad(record, object()) is None
    loader.assert_called_once()
    loader.side_effect = FileNotFoundError("missing")
    assert ws._prepare_selected_profile_cad(record, None) is None
