import threading
import time
from unittest.mock import Mock

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from tests.integration.conftest import pump_frames


def tool(number):
    return ToolDefinition(number, ToolType.FLAT_END_MILL, diameter=6, shank_diameter=6, length=40, flute_length=12)


def wait(loads):
    deadline = time.monotonic() + 10
    while loads.active and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not loads.active


def test_tool_assets_prepare_off_ui_latest_only_and_publish_without_commands(kivy_app, monkeypatch):
    from carveracontroller import desktop_tool_profile_loading as loading

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    ws.select("Profiles")
    viewer.load_tool_profiles({})
    entered, release = threading.Event(), threading.Event()
    real = loading.prepare_tool_profiles
    thread_ids, prepared_numbers = [], []
    main = threading.get_ident()

    def slow(definitions, *args):
        thread_ids.append(threading.get_ident())
        prepared_numbers.append(tuple(definitions))
        if len(prepared_numbers) == 1:
            entered.set()
            assert release.wait(10)
        return real(definitions, *args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", slow)
    send, write = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    from kivy.config import Config

    monkeypatch.setattr(Config, "write", write)
    callbacks = [Mock(), Mock(), Mock()]
    try:
        assert ws.request_toolset_profile({"id": "one", "name": "One"}, {1: tool(1)}, callbacks[0])
        assert entered.wait(2)
        assert ws.request_toolset_profile({"id": "two", "name": "Two"}, {2: tool(2)}, callbacks[1])
        assert ws.request_toolset_profile({"id": "three", "name": "Three"}, {3: tool(3)}, callbacks[2])
        pump_frames(4)
        assert not viewer.library_tool_table_mm and not write.called
        ws.select("Position")  # Navigation/frames remain available while CAD is blocked.
        pump_frames(4)
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert prepared_numbers == [(1,), (3,)]
    assert all(identity != main for identity in thread_ids)
    assert set(viewer.library_tool_table_mm) == {3}
    assert ws.loaded_toolset["name"] == "Three"
    callbacks[0].assert_not_called()
    callbacks[1].assert_not_called()
    callbacks[2].assert_called_once_with(True, None)
    write.assert_called_once()
    send.assert_not_called()
    viewer.load_tool_profiles({})


def test_tool_preparation_rejects_changed_scene_and_missing_assets(kivy_app, monkeypatch, tmp_path):
    from carveracontroller import desktop_tool_profile_loading as loading

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    viewer.load_tool_profiles({1: tool(1)})
    before = viewer._tool_meshes
    entered, release = threading.Event(), threading.Event()
    real = loading.prepare_tool_profiles

    def slow(*args):
        entered.set()
        assert release.wait(10)
        return real(*args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", slow)
    result = Mock()
    ws.request_toolset_profile({"id": "two", "name": "Two"}, {2: tool(2)}, result)
    assert entered.wait(2)
    try:
        monkeypatch.setattr(ws.app, "selected_local_filename", str(tmp_path / "changed.nc"))
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert viewer._tool_meshes is before and set(viewer.library_tool_table_mm) == {1}
    assert result.call_args.args[0] is False
    assert "changed during preparation" in result.call_args.args[1]
    monkeypatch.setattr(loading, "prepare_tool_profiles", real)
    broken = tool(2)
    broken.geometry_path = str(tmp_path / "missing.json")
    result.reset_mock()
    ws.request_toolset_profile({"id": "broken", "name": "Broken"}, {2: broken}, result)
    wait(ws.tool_profile_loads)
    assert viewer._tool_meshes is before and set(viewer.library_tool_table_mm) == {1}
    assert result.call_args.args[0] is False
    viewer.load_tool_profiles({})


def test_profile_editor_waits_for_prepared_geometry_and_closed_workspace_drops_result(kivy_app, monkeypatch, tmp_path):
    from kivy.config import Config

    from carveracontroller import desktop_tool_profile_loading as loading
    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    viewer.load_tool_profiles({})
    store = ProfileStore(tmp_path / "profiles.json")
    library = ProfileLibrary(ws, store=store)
    library.select_kind("tools")
    library._edit(store.data["tools"][0])
    real = loading.prepare_tool_profiles
    entered, release = threading.Event(), threading.Event()

    def slow(*args):
        entered.set()
        assert release.wait(10)
        return real(*args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", slow)
    write = Mock()
    monkeypatch.setattr(Config, "write", write)
    library.apply()
    assert entered.wait(2)
    assert "Preparing" in library.status.text and not viewer.library_tool_table_mm
    release.set()
    wait(ws.tool_profile_loads)
    assert "Loaded" in library.status.text and viewer.library_tool_table_mm
    before = viewer._tool_meshes
    entered.clear()
    release.clear()
    result = Mock()
    ws.request_toolset_profile({"id": "closed", "name": "Closed"}, {2: tool(2)}, result)
    assert entered.wait(2)
    with monkeypatch.context() as patch:
        patch.setattr(ws, "_profile_load_closed", True)
        release.set()
        wait(ws.tool_profile_loads)
        assert viewer._tool_meshes is before
        result.assert_not_called()
    assert write.call_count == 1
    viewer.load_tool_profiles({})
