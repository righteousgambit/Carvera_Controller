"""Real setup editors keep drafts separate from active and persisted state."""

import copy
import time
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup, restore_scene_geometry
from carveracontroller.desktop_setup_editor import open_setup_editor
from carveracontroller.desktop_view_state import capture_view
from tests.integration.conftest import pump_frames


def apply_editor(editor):
    accepted = editor.apply()
    if not editor.preparing:
        return accepted
    deadline = time.monotonic() + 5
    while editor.preparing and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not editor.preparing
    return editor.last_apply_result


def install_editor_cad(ws, monkeypatch):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    data = profile_data()
    data["components"].append({"group": "workholding", "vertices": list(data["components"][0]["vertices"])})
    cad = MachineProfile(data)
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_profile", cad)
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_component_profiles", {})
    return cad


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_cad_apply_prepares_off_ui_without_mutating_scene_until_ready(setup_workspace, monkeypatch, kind):
    import threading

    from kivy.clock import Clock

    ws, send = setup_workspace
    cad = install_editor_cad(ws, monkeypatch)
    editor = open_setup_editor(ws, kind)
    before = capture_scene_setup(ws)
    key = ("stock_size_mm", 0) if kind == "stock" else ("workholding_offset_mm", 0)
    editor.fields[key].text = "12"
    real = cad.prepare_render_buffers
    entered, release = threading.Event(), threading.Event()
    ui = threading.get_ident()

    def blocked(*args):
        assert threading.get_ident() != ui
        entered.set()
        assert release.wait(5)
        return real(*args)

    monkeypatch.setattr(cad, "prepare_render_buffers", blocked)
    try:
        assert editor.apply() and editor.preparing and editor.last_apply_result is None
        assert entered.wait(1)
        assert not editor.apply()  # Repeated activation does not start another worker.
        ticks = []
        Clock.schedule_once(lambda dt: ticks.append(dt), 0)
        pump_frames(3)
        assert ticks and editor.apply_button.disabled and "Preparing" in editor.apply_button.text
        assert capture_scene_setup(ws) == before and not ws.scene_setup_store.path.exists()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while editor.preparing and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert editor.last_apply_result is True and not editor.preparing
    assert capture_scene_setup(ws)[key[0]][0] == 12
    assert ws.scene_setup_store.get("editor-machine") == capture_scene_setup(ws)
    send.assert_not_called()


@pytest.mark.parametrize("change", ["draft", "cancel", "keep", "reload", "setup", "scale", "profile", "closed"])
def test_cad_apply_rejects_changed_or_closed_transaction(setup_workspace, monkeypatch, change):
    import threading

    ws, send = setup_workspace
    cad = install_editor_cad(ws, monkeypatch)
    viewer = ws.machine.gcode_viewer
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "12"
    entered, release = threading.Event(), threading.Event()

    def blocked(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(cad, "prepare_render_buffers", blocked)
    try:
        assert editor.apply() and entered.wait(1)
        if change == "draft":
            editor.fields["workholding_offset_mm", 0].text = "14"
        elif change in ("cancel", "keep", "reload"):
            getattr(editor, change)()
        elif change == "setup":
            viewer.configure_workholding((7, 8, 9))
        elif change == "scale":
            monkeypatch.setattr(viewer, "move_scale_by_positon", 0.5)
        elif change == "profile":
            monkeypatch.setattr(ws, "selected_machine_profile", {"id": "changed-machine"})
        else:
            monkeypatch.setattr(ws, "_profile_load_closed", True)
        expected = capture_scene_setup(ws)
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while ws.setup_editor_loads.lanes[editor.lane]["active"] and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not ws.setup_editor_loads.lanes[editor.lane]["active"]
    assert editor.last_apply_result is False
    assert capture_scene_setup(ws) == expected
    assert not ws.scene_setup_store.path.exists()
    send.assert_not_called()


def test_cad_preparation_failure_retains_scene_and_editable_draft(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    cad = install_editor_cad(ws, monkeypatch)
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "12"
    monkeypatch.setattr(cad, "prepare_render_buffers", Mock(side_effect=ValueError("invalid render frame")))
    assert apply_editor(editor) is False
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    assert "CAD preparation failed: invalid render frame" in editor.note.text
    assert editor.fields["workholding_offset_mm", 0].text == "12"
    assert not editor.apply_button.disabled
    send.assert_not_called()


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    baseline = capture_scene_setup(ws)
    geometry = copy.deepcopy(getattr(ws, "simulation_geometry", {}))
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "editor-machine"})
    monkeypatch.setattr(ws, "scene_setup_store", SceneSetupStore(tmp_path / "scene.json"))
    monkeypatch.setattr(ws, "setup_drafts", {}, raising=False)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    yield ws, send
    if getattr(ws, "setup_editor", None):
        ws.setup_editor.cancel()
        pump_frames(10, sleep=0.03)
    ws.scene_edit_in_progress = True
    try:
        for key, value in baseline["choices"].items():
            ws.component_choices[key].text = value
        restore_scene_geometry(ws, baseline)
        ws.simulation_geometry = geometry
    finally:
        ws.scene_edit_in_progress = False
    pump_frames(3)


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_cancel_and_close_have_distinct_draft_semantics(setup_workspace, kind):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, kind)
    key = next(iter(editor.fields))
    editor.fields[key].text = "invalid"
    assert editor.apply_button.disabled
    editor.keep()
    pump_frames(3)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    editor = open_setup_editor(ws, kind)
    assert editor.fields[key].text == "invalid"
    editor.cancel()
    pump_frames(3)
    editor = open_setup_editor(ws, kind)
    assert editor.fields[key].text != "invalid"
    assert capture_scene_setup(ws) == before
    send.assert_not_called()


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_apply_updates_only_reviewed_local_setup(setup_workspace, kind):
    ws, send = setup_workspace
    original_profile = dict(ws.selected_machine_profile)
    editor = open_setup_editor(ws, kind)
    key = ("stock_size_mm", 0) if kind == "stock" else ("workholding_offset_mm", 0)
    editor.fields[key].text = "1/4 in"
    assert "6.35 mm" in editor.summary.text
    assert apply_editor(editor)
    current = capture_scene_setup(ws)
    assert current[key[0]][0] == pytest.approx(6.35)
    assert ws.scene_setup_store.get("editor-machine") == current
    assert ws.selected_machine_profile == original_profile
    assert not ws.setup_drafts
    send.assert_not_called()


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_failed_save_restores_geometry_view_and_keeps_editable_draft(setup_workspace, monkeypatch, kind):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    view = capture_view(ws.machine.gcode_viewer)
    geometry = copy.deepcopy(getattr(ws, "simulation_geometry", {}))
    editor = open_setup_editor(ws, kind)
    key = ("stock_size_mm", 0) if kind == "stock" else ("workholding_offset_mm", 0)
    editor.fields[key].text = "12"
    monkeypatch.setattr(ws.scene_setup_store, "save", Mock(side_effect=OSError("disk full")))
    assert apply_editor(editor) is False
    assert "disk full" in editor.note.text
    assert editor.fields[key].text == "12"
    assert capture_scene_setup(ws) == before
    assert capture_view(ws.machine.gcode_viewer) == view
    assert ws.simulation_geometry == geometry
    assert not ws.scene_setup_store.path.exists()
    assert not ws.scene_edit_in_progress
    send.assert_not_called()


def test_changed_scene_or_profile_requires_reload_before_apply(setup_workspace):
    ws, send = setup_workspace
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "10"
    ws.machine.gcode_viewer.configure_workholding((20, 21, 22), 90, 4)
    assert apply_editor(editor) is False
    assert "active setup changed" in editor.note.text
    assert ws.machine.gcode_viewer.workholding_offset_mm == (20, 21, 22)
    editor.reload()
    assert editor.fields["workholding_offset_mm", 0].text == "20"
    editor.fields["workholding_offset_mm", 0].text = "30"
    ws.selected_machine_profile = {"id": "different-machine"}
    assert apply_editor(editor) is False
    editor.reload()
    assert "Machine profile changed" in editor.note.text
    assert ws.machine.gcode_viewer.workholding_offset_mm == (20, 21, 22)
    send.assert_not_called()


def test_external_save_is_preserved_and_preview_rolls_back(setup_workspace):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "10"
    newer = copy.deepcopy(before)
    newer["workholding_offset_mm"][0] = 33
    SceneSetupStore(ws.scene_setup_store.path).save("editor-machine", newer)
    newer_bytes = ws.scene_setup_store.path.read_bytes()
    assert apply_editor(editor) is False
    assert "Saved scene changed" in editor.note.text
    assert ws.scene_setup_store.path.read_bytes() == newer_bytes
    assert capture_scene_setup(ws) == before
    editor.reload()
    assert "reload the machine profile" in editor.note.text.lower()
    assert editor.fields["workholding_offset_mm", 0].text == "10"
    send.assert_not_called()


def test_corrupt_scene_can_be_reported_without_losing_editor(setup_workspace):
    ws, send = setup_workspace
    ws.scene_setup_store.path.write_text("not json")
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_size_mm", 0].text = "15"
    assert apply_editor(editor) is False
    assert "Scene file unavailable" in editor.note.text
    assert ws.scene_setup_store.path.read_text() == "not json"
    editor.keep()
    editor = open_setup_editor(ws, "stock")
    assert editor.fields["stock_size_mm", 0].text == "15"
    # The failed write still refuses the corrupt source, even with a saved draft.
    assert apply_editor(editor) is False
    assert ws.scene_setup_store.path.read_text() == "not json"
    send.assert_not_called()


def test_render_failure_restores_data_even_if_redraw_is_unavailable(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_size_mm", 0].text = "15"
    with monkeypatch.context() as patch:
        patch.setattr(viewer, "machine_visible", True)
        patch.setattr(viewer, "_build_machine_scene", Mock(side_effect=OSError("mesh unavailable")))
        assert apply_editor(editor) is False
        assert "prior geometry restored, redraw unavailable" in editor.note.text
        assert capture_scene_setup(ws) == before
        assert not ws.scene_setup_store.path.exists()
        assert not ws.scene_edit_in_progress
        send.assert_not_called()


def test_editor_open_suspends_keyboard_jog_and_reuses_existing_dialog(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    monkeypatch.setattr(ws.machine, "keyboard_jog_control", True)
    disable = Mock()
    monkeypatch.setattr(ws.machine, "toggle_keyboard_jog_control", disable)
    editor = open_setup_editor(ws, "stock")
    disable.assert_called_once_with(disable=True)
    editor.fields["stock_size_mm", 0].text = "15"
    assert open_setup_editor(ws, "stock") is editor
    assert editor.fields["stock_size_mm", 0].text == "15"
    send.assert_not_called()


def test_stock_drawing_tracks_dimensions_frames_invalidity_and_reload(setup_workspace, tmp_path):
    from kivy.metrics import dp

    ws, send = setup_workspace
    ws.scene_edit_in_progress = True
    try:
        ws.machine.gcode_viewer.configure_machine(stock_size_mm=(80, 60, 20))
    finally:
        ws.scene_edit_in_progress = False
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    field = editor.fields["stock_size_mm", 2]
    field.focus = True
    field.text = "1/4 in"
    pump_frames(4)
    assert editor.drawing.selected == ("stock_size_mm", 2)
    assert editor.drawing.setup["stock_size_mm"][2] == pytest.approx(6.35)
    assert "Draft" in editor.drawing_status.text
    assert "Stock Z: 6.35 mm" in editor.drawing_status.text
    assert "Stock frame · XZ" in editor.drawing.annotations[1].text
    editor.body.export_to_png(str(tmp_path / "stock-draft-z.png"))
    editor.fields["stock_origin_mm", 0].focus = True
    assert "program coordinates" in editor.drawing_status.text
    editor.fields["work_offset_mm", 0].focus = True
    assert "machine coordinates (not drawn to scale)" in editor.drawing_status.text
    field.text = "invalid"
    pump_frames(3)
    assert editor.drawing.setup is None
    assert editor.drawing.opacity == 0
    assert editor.drawing_card.height == pytest.approx(editor.drawing_status.height + dp(16))
    assert editor.apply_button.disabled
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    editor.reload()
    pump_frames(4)
    assert editor.drawing.setup == before
    assert editor.drawing.opacity == 1
    assert "Current setup" in editor.drawing_status.text
    editor.body.export_to_png(str(tmp_path / "stock-editor.png"))
    editor.popup.size_hint = (None, None)
    editor.popup.size = (1100, 850)
    pump_frames(5)
    assert editor.drawing_card.parent is editor.form
    assert editor.summary.parent is editor.form
    assert editor.scroll.height > editor.fields["stock_size_mm", 0].height
    editor.scroll.scroll_to(editor.fields["stock_size_mm", 0], animate=False)
    pump_frames(4)
    assert editor.drawing.top <= editor.drawing_card.top
    assert editor.drawing.y >= editor.drawing_status.top
    assert editor.drawing_status.texture_size[1] <= editor.drawing_status.height
    editor.body.export_to_png(str(tmp_path / "stock-editor-narrow.png"))
    send.assert_not_called()


def test_origin_edit_does_not_invent_unconfigured_stock(setup_workspace):
    ws, send = setup_workspace
    ws.scene_edit_in_progress = True
    try:
        ws.machine.gcode_viewer.configure_machine(stock_size_mm=None)
    finally:
        ws.scene_edit_in_progress = False
    editor = open_setup_editor(ws, "stock")
    assert editor.candidate()["stock_size_mm"] is None
    assert editor.drawing.opacity == 0
    editor.fields["work_offset_mm", 0].text = "-200"
    assert editor.candidate()["stock_size_mm"] is None
    assert "No stock configured" in editor.drawing_status.text
    editor.reload()
    assert editor.candidate()["stock_size_mm"] is None
    assert editor.apply_button.disabled
    send.assert_not_called()


def test_stock_dimension_click_focuses_field_without_applying(setup_workspace):
    from kivy.tests.common import UnitTestTouch

    ws, send = setup_workspace
    ws.scene_edit_in_progress = True
    try:
        ws.machine.gcode_viewer.configure_machine(stock_size_mm=(80, 60, 20))
    finally:
        ws.scene_edit_in_progress = False
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    pump_frames(5)
    for axis in (0, 1, 2):
        if editor.drawing_card.parent is editor.form:
            editor.scroll.scroll_to(editor.drawing_card, animate=False)
            pump_frames(4)
        key, points = next(item for item in editor.drawing.dimension_targets if item[0][1] == axis)
        midpoint = ((points[0] + points[2]) / 2, (points[1] + points[3]) / 2)
        assert editor.drawing.dimension_at(midpoint) == key
        x, y = editor.drawing.to_window(*midpoint)
        touch = UnitTestTouch(x, y)
        touch.profile.append("button")
        touch.button = "left"
        touch.touch_down()
        pump_frames(4, sleep=0.03)
        touch.touch_up()
        pump_frames(5, sleep=0.03)
        assert editor.fields[key].focus
        assert editor.selected_dimension == key
        assert capture_scene_setup(ws) == before
        assert editor.apply_button.disabled
    if editor.drawing_card.parent is editor.form:
        editor.scroll.scroll_to(editor.drawing_card, animate=False)
        pump_frames(4)
    points = editor.drawing.dimension_targets[0][1]
    x, y = editor.drawing.to_window((points[0] + points[2]) / 2, (points[1] + points[3]) / 2)
    touch = UnitTestTouch(x, y)
    touch.touch_down()
    pump_frames(4, sleep=0.03)
    touch.touch_move(x + 30, y + 30)
    touch.touch_up()
    pump_frames(4, sleep=0.03)
    assert editor.selected_dimension == ("stock_size_mm", 2)
    editor.fields["stock_size_mm", 2].text = "1/4 in"
    pump_frames(4)
    assert editor.drawing.setup["stock_size_mm"][2] == pytest.approx(6.35)
    assert capture_scene_setup(ws) == before
    editor.fields["stock_size_mm", 2].text = "invalid"
    pump_frames(3)
    assert editor.drawing.dimension_targets == []
    assert editor.drawing.dimension_at(editor.drawing.center) is None
    send.assert_not_called()


def test_vise_drawing_tracks_rotated_jaw_and_preserves_active_setup(setup_workspace, monkeypatch, tmp_path):
    from carveracontroller.addons.machine_simulation.model import Geometry
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    ws, send = setup_workspace
    components = []
    for low, high, role in (((0, 0, 0), (40, 10, 10), "fixed"), ((0, 30, 0), (40, 40, 10), "movable")):
        mesh = Geometry()
        mesh.box(low, high, (1, 1, 1, 1))
        components.append({"group": "workholding", "role": role, "vertices": mesh.vertices})
    data = profile_data()
    data["components"].extend(components)
    data["workholding"] = {"pivot_mm": (0, 0, 0)}
    profile = MachineProfile(data)
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_component_profiles", {"workholding": profile})
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "workholding")
    for axis, value in enumerate((10, 20, 30)):
        editor.fields["workholding_offset_mm", axis].text = str(value)
    editor.fields["workholding_rotation_deg", None].focus = True
    editor.fields["workholding_rotation_deg", None].text = "90 deg"
    pump_frames(4)
    fixed, movable = editor.drawing.placed
    editor.fields["jaw_offset_mm", None].focus = True
    editor.fields["jaw_offset_mm", None].text = "1/4 in"
    pump_frames(4)
    assert editor.drawing.selected == ("jaw_offset_mm", None)
    assert "6.35 mm before rotation" in editor.drawing_status.text
    assert editor.drawing.placed[0] == fixed
    for old, new in zip(movable[0], editor.drawing.placed[1][0]):
        assert new == pytest.approx((old[0] - 6.35, old[1], old[2]))
    from kivy.tests.common import UnitTestTouch

    assert {key for key, _ in editor.drawing.dimension_targets} == {
        ("workholding_offset_mm", 0),
        ("workholding_offset_mm", 1),
        ("workholding_offset_mm", 2),
        ("workholding_rotation_deg", None),
        ("jaw_offset_mm", None),
    }
    key = ("workholding_rotation_deg", None)
    points = next(points for target, points in editor.drawing.dimension_targets if target == key)
    midpoint = ((points[0] + points[2]) / 2, (points[1] + points[3]) / 2)
    assert editor.drawing.dimension_at(midpoint) == key
    x, y = editor.drawing.to_window(*midpoint)
    touch = UnitTestTouch(x, y)
    touch.profile.append("button")
    touch.button = "left"
    touch.touch_down()
    pump_frames(4, sleep=0.03)
    touch.touch_up()
    pump_frames(5, sleep=0.03)
    assert editor.selected_dimension == key
    assert editor.fields[key].focus
    editor.fields["jaw_offset_mm", None].focus = True
    pump_frames(4)
    editor.body.export_to_png(str(tmp_path / "vise-jaw-draft.png"))
    for axis in range(3):
        editor.fields["workholding_offset_mm", axis].text = "0"
    editor.fields["workholding_rotation_deg", None].text = "0"
    editor.fields["jaw_offset_mm", None].text = "0"
    pump_frames(4)
    zero_draft = editor.candidate()
    for key, button in editor.drawing.dimension_buttons.items():
        if editor.drawing_card.parent is editor.form:
            editor.scroll.scroll_to(editor.drawing_card, animate=False)
            pump_frames(4)
        x, y = button.to_window(*button.center)
        touch = UnitTestTouch(x, y)
        touch.profile.append("button")
        touch.button = "left"
        touch.touch_down()
        pump_frames(4, sleep=0.03)
        touch.touch_up()
        pump_frames(5, sleep=0.03)
        assert editor.selected_dimension == key
        assert editor.fields[key].focus
        assert editor.candidate() == zero_draft
        assert capture_scene_setup(ws) == before
    editor.body.export_to_png(str(tmp_path / "vise-zero-dimensions.png"))
    editor.fields["workholding_rotation_deg", None].text = "invalid"
    pump_frames(4)
    assert editor.drawing.opacity == 0
    assert editor.drawing.placed == ()
    assert all(button.disabled for button in editor.drawing.dimension_buttons.values())
    rejected_touch = Mock(pos=editor.drawing.center)
    assert editor.drawing.on_touch_down(rejected_touch) is False
    rejected_touch.grab.assert_not_called()
    assert editor.apply_button.disabled
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    editor.reload()
    pump_frames(4)
    assert editor.drawing.opacity == 1
    assert editor.drawing.setup == before
    assert "Current setup" in editor.drawing_status.text
    editor.popup.size_hint = (None, None)
    editor.popup.size = (1100, 850)
    pump_frames(4)
    assert editor.drawing_card.parent is editor.form
    assert editor.summary.parent is editor.form
    assert editor.scroll.height > editor.fields["jaw_offset_mm", None].height
    editor.scroll.scroll_to(editor.fields["jaw_offset_mm", None], animate=False)
    pump_frames(4)
    editor.body.export_to_png(str(tmp_path / "vise-editor-narrow.png"))
    send.assert_not_called()


def test_vise_without_cad_does_not_invent_geometry(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_component_profiles", {})
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_profile", None)
    editor = open_setup_editor(ws, "workholding")
    pump_frames(3)
    assert editor.drawing.opacity == 0
    assert "No workholding CAD loaded" in editor.drawing_status.text
    assert editor.drawing.placed == ()
    editor.fields["jaw_offset_mm", None].text = "4"
    assert not editor.apply_button.disabled
    assert "No workholding CAD loaded" in editor.drawing_status.text
    send.assert_not_called()


def test_untouched_fields_preserve_full_precision_and_named_stock(setup_workspace):
    ws, send = setup_workspace
    ws.scene_edit_in_progress = True
    try:
        ws.component_choices["stock"].text = "Precision stock"
        ws.machine.gcode_viewer.configure_machine(
            stock_size_mm=(127.123456789123, 69.418212345678, 50.876212345678),
            stock_origin_mm=(-118.6123456789, -94.7091234567, -0.36788123456),
        )
    finally:
        ws.scene_edit_in_progress = False
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    assert editor.candidate() == before
    assert editor.apply_button.disabled
    editor.fields["work_offset_mm", 0].text = "-200"
    candidate = editor.candidate()
    assert candidate["stock_size_mm"] == before["stock_size_mm"]
    assert candidate["stock_origin_mm"] == before["stock_origin_mm"]
    assert candidate["choices"]["stock"] == before["choices"]["stock"]
    assert apply_editor(editor)
    assert ws.scene_setup_store.read_current("editor-machine")["stock_size_mm"] == before["stock_size_mm"]
    send.assert_not_called()


def test_stock_edit_preserves_rotated_frame_and_restart_state(setup_workspace):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    viewer.configure_machine(
        work_offset_mm=(-180, -120, -110),
        stock_size_mm=(30, 20, 10),
        stock_origin_mm=(-15, -10, 0),
        stock_rotation_deg=37,
    )
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_size_mm", 0].text = "40 mm"
    assert capture_scene_setup(ws) == before
    assert apply_editor(editor)
    assert viewer.machine_setup.stock_rotation_deg == 37
    saved = SceneSetupStore(ws.scene_setup_store.path).get("editor-machine")
    assert saved["stock_rotation_deg"] == 37
    viewer.configure_machine(stock_size_mm=(1, 1, 1))
    restore_scene_geometry(ws, saved)
    assert viewer.machine_setup.stock_rotation_deg == 37
    assert viewer.machine_setup.stock_size_mm == (40, 20, 10)
    assert ws.simulation_geometry["rotation_deg"] == 37
    send.assert_not_called()


def test_stock_rotation_field_is_reviewed_then_applied_and_persisted(setup_workspace):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    viewer.configure_machine(stock_size_mm=(30, 20, 10))
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_rotation_deg", None].text = "1.5707963267948966 rad"
    assert capture_scene_setup(ws) == before
    assert apply_editor(editor)
    assert viewer.machine_setup.stock_rotation_deg == pytest.approx(90)
    assert SceneSetupStore(ws.scene_setup_store.path).get("editor-machine")["stock_rotation_deg"] == pytest.approx(90)
    send.assert_not_called()


def test_facing_uses_rotated_stock_footprint(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    viewer.configure_machine(stock_size_mm=(30, 20, 10), stock_origin_mm=(-15, -10, 2), stock_rotation_deg=37)
    panel = ws.surface_planning_panel
    for field in (panel.boundary, panel.fields["top_z_mm"], panel.fields["clearance_z_mm"], panel.note):
        monkeypatch.setattr(field, "text", field.text)
    panel.use_stock()
    actual = [tuple(float(value) for value in row.split()) for row in panel.boundary.text.splitlines()]
    for values, corner in zip(actual, ((-15, -10, 2), (15, -10, 2), (15, 10, 2), (-15, 10, 2))):
        assert values == pytest.approx(viewer.machine_setup.stock_point(corner)[:2], abs=0.0001)
    assert float(panel.fields["top_z_mm"].text) == 12
    send.assert_not_called()
