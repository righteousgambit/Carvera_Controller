import time
from unittest.mock import Mock

from carveracontroller.desktop_commands import CommandPalette
from carveracontroller.desktop_components import DesktopScrollView

from .conftest import pump_frames


def settle_search(palette):
    deadline = time.monotonic() + 5
    while palette.search_pending and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not palette.search_pending


def settle_closed(palette):
    # Modal dismissal animates in wall-clock time. A fixed frame count can
    # finish before that animation on a fast viewport, even with no worker.
    deadline = time.monotonic() + 2
    while palette.popup.parent and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not palette.popup.parent


def test_slow_job_index_keeps_actions_and_close_available_and_discards_old_delivery(kivy_app, monkeypatch):
    from threading import Event

    import carveracontroller.desktop_commands as commands
    from carveracontroller.machine.program_operations import ProgramOperations

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    panel.load(None)
    panel._loaded(panel.generation, ProgramOperations.from_text("(OPERATION: old job)\nG21 G90 G54\nM30"), None)
    entered, release = Event(), Event()
    original = commands._operation_commands

    def slow_index(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(commands, "_operation_commands", slow_index)
    palette = CommandPalette(ws)
    try:
        palette.open()
        assert entered.wait(2)
        pump_frames(4)
        assert palette.search_pending
        palette.input.text = "camera"
        pump_frames(4)
        assert any(item.id.startswith("camera.") for item in palette.matches)
        # An in-flight worker does not own the popup or capture its Close input.
        assert palette.keydown(None, 27, None, "", [])
        pump_frames(4)
        settle_closed(palette)
        panel.load(None)
        release.set()
        palette.open()
        settle_search(palette)
        pump_frames(6)
        assert all(not item.id.startswith("job.operation.") for item in palette.matches)
        assert palette._entity_program is None
    finally:
        release.set()
        palette.popup.dismiss()
        panel.load(None)
        pump_frames(3)


def test_failed_job_index_reports_failure_and_keeps_local_actions(kivy_app, monkeypatch):
    import carveracontroller.desktop_commands as commands
    from carveracontroller.machine.program_operations import ProgramOperations

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    panel.load(None)
    panel._loaded(panel.generation, ProgramOperations.from_text("G21 G90 G54\nM30"), None)

    def failed_index(*_args, **_kwargs):
        raise ValueError("Injected index failure")

    monkeypatch.setattr(commands, "_operation_commands", failed_index)
    palette = CommandPalette(ws)
    try:
        palette.open()
        settle_search(palette)
        assert "ValueError" in palette.result_note.text
        assert "actions remain available" in palette.result_note.text
        assert any(item.id == "scene.coordinates" for item in palette.matches)
        assert palette.keydown(None, 27, None, "", [])
        pump_frames(4)
        settle_closed(palette)
    finally:
        palette.popup.dismiss()
        panel.load(None)
        pump_frames(3)


def test_palette_job_search_routes_operation_and_rechecks_loaded_job(kivy_app, monkeypatch):
    from carveracontroller.machine.program_operations import ProgramOperations

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    program = ProgramOperations.from_text(
        "G21 G90 G54\n(OPERATION: Finish attachment wall)\nT2 M6\nG0 X0 Y0 Z5\nG1 X10 F100\nM30\n"
    )
    panel.load(None)
    panel._loaded(panel.generation, program, None)
    palette = CommandPalette(ws)
    try:
        palette.open()
        settle_search(palette)
        pump_frames(5)
        palette.input.text = "attachment T2"
        settle_search(palette)
        pump_frames(5)
        assert len(palette.matches) == 1
        match = palette.matches[0]
        assert palette.keydown(None, 13, None, "", [])
        pump_frames(8)
        assert ws.active_section == "Job"
        assert ws.program_tasks.active == "Operations"
        assert panel.selected_operation.name == "Finish attachment wall"
        assert panel.selected_line == panel.selected_operation.start_line
        settle_closed(palette)
        palette.open()
        settle_search(palette)
        pump_frames(5)
        panel.load(None)
        assert not palette.execute(match)
        settle_search(palette)
        assert palette.popup.parent
        assert all(not item.id.startswith("job.operation.") for item in palette.matches)
        send.assert_not_called()
    finally:
        palette.popup.dismiss()
        panel.load(None)
        pump_frames(3)


def test_palette_bounds_rows_and_refreshes_entities_after_background_replacement(kivy_app):
    from carveracontroller.machine.program_operations import ProgramOperations

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    program = ProgramOperations.from_text(
        "G21 G90 G54\nT1 M6\nG0 X0 Y0 Z5\n"
        + "\n".join(f"(OPERATION: Pocket unique{index})\nG1 X{index} F100" for index in range(100))
    )
    panel.load(None)
    panel._loaded(panel.generation, program, None)
    palette = CommandPalette(ws)
    try:
        palette.open()
        settle_search(palette)
        pump_frames(5)
        palette.input.text = "pocket"
        settle_search(palette)
        pump_frames(5)
        assert len(palette.matches) == len(palette.rows) == 40
        assert "101 matches" in palette.result_note.text  # 100 operations plus the setup-tools action.
        assert "refine" in palette.result_note.text
        cached = palette._entity_commands
        palette.input.text = "pocket unique99"
        settle_search(palette)
        pump_frames(5)
        assert palette._entity_commands is cached
        assert len(palette.matches) == 1
        panel.load(None)
        palette.refresh()
        settle_search(palette)
        assert not palette.matches
        assert not palette._entity_commands
    finally:
        palette.popup.dismiss()
        panel.load(None)
        pump_frames(3)


def test_palette_keyboard_short_results_stay_top_and_task_routes_send_no_commands(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    palette = CommandPalette(ws)
    try:
        palette.open()
        settle_search(palette)
        pump_frames(6)
        assert palette.input.focus
        assert isinstance(palette.scroll, DesktopScrollView)
        palette.input.text = "camera"
        settle_search(palette)
        pump_frames(6)
        assert len(palette.matches) >= 2
        assert palette.keydown(None, 274, None, "", [])
        pump_frames(8)
        assert palette.selected == 1
        assert palette.scroll.scroll_y == 1
        palette.input.text = "portable archive"
        settle_search(palette)
        pump_frames(6)
        assert len(palette.matches) == 1
        assert palette.keydown(None, 13, None, "", [])
        pump_frames(6)
        settle_closed(palette)
        assert ws.program_tasks.active == "Job package"
        send.assert_not_called()
        palette.open()
        settle_search(palette)
        pump_frames(5)
        assert palette.keydown(None, 27, None, "", [])
        pump_frames(5)
        settle_closed(palette)
    finally:
        palette.popup.dismiss()
        pump_frames(3)


def test_retained_inspection_action_search_opens_offline_without_commands(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.desktop_commands import search_commands, workspace_commands
    from carveracontroller.machine.surface_inspection import SurfaceInspectionStore

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "surface_inspection_store", SurfaceInspectionStore(tmp_path / "empty.json"), raising=False)
    commands = workspace_commands(ws)
    matches = search_commands(commands, "inspection")
    assert matches[0].id == "inspection.records"
    assert search_commands(commands, "batch TSV")[0].id == "inspection.records"
    assert matches[0].invoke()
    pump_frames(6)
    review = ws.surface_inspection_review
    assert review.popup._is_open and "Pick a surface" in review.report.text
    assert review.batch_button.disabled
    review.popup_close()
    pump_frames(6)
    send.assert_not_called()


def test_scene_palette_routes_and_reassembly_preserve_setup_and_send_no_commands(kivy_app, monkeypatch):
    from carveracontroller.desktop_commands import workspace_commands
    from carveracontroller.machine.scene_inspection import COMPONENT_TITLES

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    commands = {c.id: c for c in workspace_commands(ws)}
    original_mode, original_selected = viewer.pose_mode, ws.object_inspector.selected
    original_distance = viewer.explosion_mm
    original_distance_text = ws.object_inspector.explode_distance.text
    setup = viewer.machine_setup
    try:
        for component in COMPONENT_TITLES:
            assert commands[f"scene.inspect.{component}"].invoke()
            pump_frames(2)
            assert ws.active_section == "Scene"
            assert ws.object_inspector.selected == component
        ws.set_pose_mode("Preview")
        ws.object_inspector.explode_distance.text = "1 in"
        assert commands["scene.explode"].invoke()
        pump_frames(4)
        assert viewer.explosion_mm == 25.4
        assert viewer.machine_setup == setup
        ws.set_pose_mode("Live")
        assert not commands["scene.explode"].invoke()
        assert viewer.explosion_offset("stock") == (0, 0, 0)
        assert commands["scene.reassemble"].invoke()
        assert viewer.explosion_mm == 0
        send.assert_not_called()
    finally:
        ws.set_pose_mode("Preview")
        viewer.set_explosion(original_distance)
        ws.set_pose_mode(original_mode)
        ws.object_inspector.select(original_selected)
        ws.object_inspector.explode_distance.text = original_distance_text
