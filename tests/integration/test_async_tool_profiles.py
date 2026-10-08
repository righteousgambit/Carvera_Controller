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


def test_assembly_preview_revision_guard_and_background_restore(kivy_app, monkeypatch, tmp_path):
    from carveracontroller import desktop_tool_profile_loading as loading
    from carveracontroller.machine.desktop_profiles import ProfileStore
    from carveracontroller.machine.tool_custody import ToolCustodyStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    profiles = ProfileStore(tmp_path / "profiles.json")
    profile = profiles.save_tool(
        {
            "name": "Physical cutter",
            "number": 2,
            "shape": "flat_end_mill",
            "diameter": 6,
            "shank_diameter": 6,
            "length": 60,
            "flute_length": 12,
        }
    )
    custody = ToolCustodyStore(tmp_path / "custody.json")
    assembly = custody.create_assembly("Seated cutter", "A", 28, profile["id"])
    monkeypatch.setattr(ws, "profile_store", profiles)
    monkeypatch.setattr(ws.machine, "_tool_custody", custody)
    viewer.load_tool_profiles({2: tool(2)})
    baseline = dict(viewer.library_tool_table_mm)
    before = viewer._tool_meshes
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    entered, release = threading.Event(), threading.Event()
    real = loading.prepare_tool_profiles
    threads = []

    def slow(*args):
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(10)
        return real(*args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", slow)
    result = Mock()
    try:
        ws.request_assembly_preview(assembly["id"], 2, result)
        assert entered.wait(2)
        ws.select("Position")
        pump_frames(4)
        assert viewer._tool_meshes is before and viewer.assembly_preview_binding is None
        custody.revise(assembly["id"], assembly["id"], "Seated cutter", "A", 30, profile["id"], "Reseated")
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert result.call_args.args[0] is False and "revision changed" in result.call_args.args[1]
    assert viewer._tool_meshes is before and viewer.library_tool_table_mm == baseline
    result.reset_mock()
    ws.request_assembly_preview(assembly["id"], 2, result)
    wait(ws.tool_profile_loads)
    result.assert_called_once_with(True, None)
    assert viewer.library_tool_table_mm[2].stickout == 30 and viewer.preview_tool_override == 2
    binding = viewer.assembly_preview_binding
    profile["diameter"] = 5
    profiles.save_tool(profile)
    # Current saved definition is frozen at request time, then checked again before publication.
    entered.clear()
    release.clear()
    result.reset_mock()
    try:
        ws.request_assembly_preview(assembly["id"], 2, result)
        assert entered.wait(2)
        profiles.save_tool(dict(profile, diameter=4))
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert result.call_args.args[0] is False and "Linked cutter changed" in result.call_args.args[1]
    assert viewer.assembly_preview_binding is binding and viewer.library_tool_table_mm[2].diameter == 6
    monkeypatch.setattr(ws, "selected_machine_profile", {"name": "Workshop test"}, raising=False)
    monkeypatch.setattr(ws, "loaded_toolset", None, raising=False)
    ws.profile_status.text = "Preview T2: stale cutter"
    ws.request_clear_assembly_preview(follow_program=True)
    wait(ws.tool_profile_loads)
    assert viewer.library_tool_table_mm == baseline
    assert viewer.assembly_preview_binding is None and viewer.preview_tool_override is None
    assert ws.profile_status.text == "Workshop test • local profile\nNo toolset loaded"
    monkeypatch.setattr(ws, "loaded_toolset", {"name": "Finishing bank"})
    ws._restore_profile_status()
    assert ws.profile_status.text == "Workshop test • local profile\nFinishing bank"
    assert all(t != threading.get_ident() for t in threads)
    send.assert_not_called()
    viewer.load_tool_profiles({})


def test_scene_cutter_latest_selection_and_failed_load_preserve_saved_scene(kivy_app, monkeypatch, tmp_path):
    from carveracontroller import desktop_tool_profile_loading as loading
    from carveracontroller.desktop_scene import SceneSetupStore
    from carveracontroller.machine.desktop_profiles import ProfileStore

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    profiles = ProfileStore(tmp_path / "profiles.json")
    first = profiles.save_tool(
        {
            "name": "First",
            "number": 2,
            "shape": "flat_end_mill",
            "diameter": 6,
            "shank_diameter": 6,
            "length": 40,
            "flute_length": 12,
        }
    )
    last = profiles.save_tool(
        {
            "name": "Last",
            "number": 3,
            "shape": "flat_end_mill",
            "diameter": 4,
            "shank_diameter": 6,
            "length": 40,
            "flute_length": 12,
        }
    )
    monkeypatch.setattr(ws, "profile_store", profiles)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "test-scene"})
    save = Mock()
    monkeypatch.setattr(SceneSetupStore, "save", save)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    viewer.load_tool_profiles({})
    choice = ws.component_choices["cutter"]
    choice.dispatch("on_press")
    labels = {p["id"]: name for name, p in ws.scene_tool_options.items()}
    entered, release = threading.Event(), threading.Event()
    real = loading.prepare_tool_profiles
    calls = []

    def slow(definitions, *args):
        calls.append(tuple(definitions))
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
        return real(definitions, *args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", slow)
    try:
        choice.text = labels[first["id"]]
        assert entered.wait(2)
        choice.text = labels[last["id"]]
        ws.select("Position")
        pump_frames(4)
        assert not viewer.library_tool_table_mm and not save.called
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert calls == [(2,), (3,)]
    assert viewer.preview_tool_override == 3 and set(viewer.library_tool_table_mm) == {3}
    save.assert_called_once()
    assert save.call_args.args[1]["choices"]["cutter"] == labels[last["id"]]
    before = viewer._tool_meshes
    entered.clear()
    release.clear()
    calls.clear()
    try:
        choice.text = labels[first["id"]]
        assert entered.wait(2)
        profiles.save_tool(dict(first, diameter=5))
    finally:
        release.set()
    wait(ws.tool_profile_loads)
    assert viewer._tool_meshes is before and viewer.preview_tool_override == 3
    assert choice.text == labels[last["id"]] and save.call_count == 1
    assert "Saved cutter changed" in ws.scene_component_note.text
    monkeypatch.setattr(loading, "prepare_tool_profiles", real)
    choice.text = "Follow program"
    wait(ws.tool_profile_loads)
    assert viewer.preview_tool_override is None
    send.assert_not_called()
    viewer.load_tool_profiles({})
