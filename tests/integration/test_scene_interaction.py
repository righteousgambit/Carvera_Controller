from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.graphics.transformation import Matrix

from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.machine.scene_interaction import plane_point
from tests.integration import test_setup_editor
from tests.integration.conftest import pump_frames


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    yield from test_setup_editor.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch)


@pytest.mark.parametrize("perspective", [False, True])
def test_projection_ray_roundtrip_in_machine_coordinates(setup_workspace, monkeypatch, perspective):
    ws, send = setup_workspace
    interaction = ws.scene_interaction
    viewer = interaction.viewer
    monkeypatch.setattr(viewer, "m_viewMatrix", Matrix().look_at(0, -20, 20, 0, 0, 0, 0, 0, 1))
    projection = Matrix()
    projection.view_clip(-2, 2, -1, 1, 1, 100, perspective)
    monkeypatch.setattr(viewer, "_proj_matrix", projection)
    monkeypatch.setattr(viewer, "move_scale_by_positon", 0.5)
    monkeypatch.setattr(viewer, "lines_center", (1, 2, 3))
    rendered = (1, 0, 0)
    offset = viewer.machine_setup.work_offset_mm
    target = tuple((rendered[i] + viewer.lines_center[i]) / 0.5 + offset[i] for i in range(3))
    screen = viewer.m_viewMatrix.project(
        *rendered, viewer.m_viewMatrix, projection, *viewer._view_cube_gl_origin(), viewer.width, viewer.height
    )
    origin, direction = interaction.screen_ray(viewer.parent.to_widget(*screen[:2]))
    assert plane_point(origin, direction, target, (0, 0, 1)) == pytest.approx(target, abs=1e-5)
    send.assert_not_called()


def begin_drag(ws, monkeypatch):
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    ws.active_section = "Scene"
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "machine_visible", True)
    interaction.mode.text = "Move XY"
    monkeypatch.setattr(interaction, "center", lambda: ("stock", (0, 0, 0)))
    monkeypatch.setattr(interaction, "refresh_handle", lambda *args: None)
    monkeypatch.setattr(interaction, "window_pos", lambda pos: pos)
    interaction.color.a = 1
    interaction.handle.circle = (10, 10, 8)
    monkeypatch.setattr(interaction, "screen_ray", lambda pos, inverse=None: ((pos[0], pos[1], 10), (0, 0, -1)))
    touch = SimpleNamespace(pos=(10, 10), button="left")
    assert interaction.down(touch)
    assert interaction.gesture is not None
    touch.pos = (12, 13)
    return interaction, touch


def test_drag_creates_reviewed_draft_without_changing_scene_then_apply_persists(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    configure = Mock(wraps=interaction.viewer.configure_machine)
    monkeypatch.setattr(interaction.viewer, "configure_machine", configure)
    interaction.move(touch)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    configure.assert_not_called()
    interaction.up(touch)
    editor = ws.setup_editor
    assert editor.fields["stock_origin_mm", 0].value() == before["stock_origin_mm"][0] + 2
    assert editor.fields["stock_origin_mm", 1].value() == before["stock_origin_mm"][1] + 3
    assert capture_scene_setup(ws) == before
    assert editor.apply()
    assert ws.scene_setup_store.get("editor-machine") == capture_scene_setup(ws)
    send.assert_not_called()


@pytest.mark.parametrize("change", ["profile", "camera", "state", "viewport"])
def test_changed_context_discards_gesture(setup_workspace, monkeypatch, change):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.move(touch)
    if change == "profile":
        ws.selected_machine_profile = {"id": "different"}
    elif change == "camera":
        monkeypatch.setattr(interaction.viewer, "m_viewMatrix", Matrix().translate(1, 0, 0))
    elif change == "state":
        ws.app.state = "Run"
    else:
        monkeypatch.setattr(interaction.viewer, "width", interaction.viewer.width + 1)
    interaction.up(touch)
    assert interaction.gesture is None
    assert "discarded" in interaction.note.text
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    send.assert_not_called()


def test_cancel_placement_and_default_view(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.up(touch)
    ws.setup_editor.cancel()
    pump_frames(10, sleep=0.03)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    interaction.mode.text = "View"
    assert not interaction.down(touch)
    send.assert_not_called()


def test_retained_draft_is_not_overwritten_by_drag(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.gesture = None
    ws.setup_drafts[("editor-machine", "stock")] = {"sentinel": "operator draft"}
    touch.pos = (10, 10)
    assert interaction.down(touch)
    assert interaction.gesture is None
    assert ws.setup_drafts[("editor-machine", "stock")] == {"sentinel": "operator draft"}
    assert "retained" in interaction.note.text
    send.assert_not_called()


def test_invalid_drag_point_discards_entire_gesture(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.move(touch)
    monkeypatch.setattr(interaction, "screen_ray", Mock(side_effect=ValueError("invalid ray")))
    interaction.up(touch)
    assert interaction.gesture is None
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    assert "discarded" in interaction.note.text
    send.assert_not_called()


@pytest.mark.parametrize("stale", [False, True])
def test_surface_pick_delivers_only_current_view(setup_workspace, monkeypatch, stale):
    ws, send = setup_workspace
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    from carveracontroller import desktop_scene_interaction as module
    from carveracontroller.addons.machine_simulation.model import Geometry

    geometry = Geometry()
    geometry.triangle(((0, 0, 0), (2, 0, 0), (0, 2, 0)), (0, 0, 1), (1, 1, 1, 1))
    monkeypatch.setattr(viewer, "_inspection_geometry", {"stock": geometry})
    monkeypatch.setattr(viewer, "_machine_pose", {**viewer._machine_pose, "table": (0, 0, 0)})
    monkeypatch.setattr(viewer, "machine_visible", True)
    monkeypatch.setattr(viewer, "machine_group_visibility", {**viewer.machine_group_visibility, "stock": True})
    monkeypatch.setattr(interaction, "screen_ray", lambda pos: ((0.5, 0.5, 10), (0, 0, -1)))
    ws.active_section = "Scene"
    interaction.mode.text = "Pick component"
    selected = Mock()
    monkeypatch.setattr(ws.object_inspector, "select", selected)
    # Execute worker deterministically, leaving delivery on the actual UI Clock.
    monkeypatch.setattr(module.threading, "Thread", lambda **kwargs: SimpleNamespace(start=kwargs["target"]))
    interaction.pick((10, 10))
    if stale:
        monkeypatch.setattr(viewer, "m_viewMatrix", Matrix().translate(3, 0, 0))
    pump_frames(3)
    if stale:
        selected.assert_not_called()
    else:
        selected.assert_called_once_with("stock", reveal=False)
    assert not interaction.picking
    send.assert_not_called()


def test_real_stock_handle_render_and_task_visibility(setup_workspace, monkeypatch):
    from kivy.core.window import Window

    ws, send = setup_workspace
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "disabled", False)
    ws.select("Scene")
    ws.object_inspector.select("stock", reveal=False)
    viewer.set_machine_visible(True)
    viewer.configure_machine((-180, -120, -110), (30, 20, 10), (0, 0, 0))
    interaction.mode.text = "Move XY"
    viewer.restore_default_view()
    pump_frames(5)
    interaction.refresh_handle()
    assert interaction.center() is not None
    assert interaction.color.a == 1
    x, y = interaction.handle.circle[:2]
    local = viewer.parent.to_widget(x, y)
    assert viewer.collide_point(*local)
    Window.screenshot(name="/tmp/carvera-scene-handle.png")
    before = capture_scene_setup(ws)
    touch = SimpleNamespace(pos=local, button="left")
    assert interaction.down(touch)
    assert interaction.gesture is not None
    touch.pos = viewer.parent.to_widget(x + 25, y + 15)
    interaction.up(touch)
    assert ws.setup_editor is not None
    assert capture_scene_setup(ws) == before
    ws.setup_editor.cancel()
    pump_frames(10, sleep=0.03)
    ws.select("Job")
    interaction.refresh_handle()
    assert interaction.color.a == 0
    send.assert_not_called()
