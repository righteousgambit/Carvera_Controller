"""Quantity UI feeds actual profile/planner transactions in canonical units."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_components import Action, QuantityField
from carveracontroller.desktop_hole_planning import parse_holes
from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.desktop_surface_planning import points
from carveracontroller.machine.desktop_profiles import ProfileStore
from tests.integration.conftest import pump_frames
from tests.integration.test_desktop_surface_planning import configure


def test_quantity_feedback_and_invalid_input(kivy_app):
    field = QuantityField(text="1/4 in", maximum=1000)
    assert field.value() == pytest.approx(6.35)
    assert "6.35 mm" in field.interpretation.text
    field.text = "1/0"
    assert "divide by zero" in field.error
    with pytest.raises(ValueError):
        field.value()
    field.text = "1/8 in"
    assert not field.error and field.value() == pytest.approx(3.175)
    field.step_buttons[1].dispatch("on_release")
    assert field.value() == pytest.approx(3.275)
    field.text = "1000"
    field.step_buttons[1].dispatch("on_release")
    assert field.text == "1000" and "Maximum" in field.error


def test_quantity_controls_survive_textinput_graphics_refresh(kivy_app):
    field = QuantityField(text="1/4 in", pos=(40, 40), size=(360, 54))
    pump_frames(3)
    for expression in ("1/8 in", "10 rpm", "127/2 mm"):
        field.text = expression
        field._update_graphics()
        pump_frames(3)
        for control in (field.interpretation, *field.step_buttons):
            assert control.canvas in field.canvas.after.children
            assert control.parent is field
            assert field.collide_point(*control.center)
    assert "63.5 mm" in field.interpretation.text


def test_tool_library_saves_and_loads_canonical_geometry(kivy_app, tmp_path):
    ws = kivy_app.root.desktop_workspace
    store = ProfileStore(tmp_path / "profiles.json")
    library = ProfileLibrary(ws, store=store)
    library.select_kind("tools")
    library.new()
    library.fields["name"].text = "Imperial cutter"
    for key, text in {
        "diameter": "1/4 in",
        "shank_diameter": '1/4"',
        "length": "3 in",
        "flute_length": "1 in",
        "stickout": "1 1/4 in",
    }.items():
        library.fields[key].text = text
    saved = library.save()
    assert saved and saved["diameter"] == pytest.approx(6.35)
    assert saved["stickout"] == pytest.approx(31.75)
    reloaded = next(t for t in ProfileStore(store.path).data["tools"] if t["id"] == saved["id"])
    assert reloaded == saved
    library.fields["diameter"].text = "2 rpm"
    assert library.save() is None
    assert "Diameter" in library.status.text
    assert next(t for t in ProfileStore(store.path).data["tools"] if t["id"] == saved["id"]) == saved


def test_facing_process_converts_feed_and_depth_without_commands(kivy_app, monkeypatch):
    ws, panel = configure(kivy_app)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(panel.fields["feed_mm_min"], "text", "12 ipm")
    monkeypatch.setattr(panel.fields["final_z_mm"], "text", "-1/100 in")
    monkeypatch.setattr(panel.fields["pass_depth_mm"], "text", ".005 in")
    p, _tool = panel.parameters()
    assert p.feed_mm_min == pytest.approx(304.8)
    assert p.final_z_mm == pytest.approx(-0.254)
    assert p.pass_depth_mm == pytest.approx(0.127)
    send.assert_not_called()


def test_bulk_coordinates_have_explicit_units_and_legacy_compatibility():
    assert points("1/4 in, 1/2 in\n0, 0", 2)[0] == pytest.approx((6.35, 12.7))
    hole = parse_holes("1/4 in, 1/2 in, 1/4 in, 1/8 in")[0]
    assert hole.x_mm == pytest.approx(6.35)
    assert hole.thread_depth_mm == pytest.approx(3.175)
    assert points("1 2\n3 4", 2) == ((1, 2), (3, 4))


def test_measurement_dialog_has_space_for_all_rows_at_desktop_size(kivy_app, monkeypatch):
    from kivy.core.window import Window
    from kivy.uix.scrollview import ScrollView

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "measurement-layout"})
    old_size = Window.size
    try:
        Window.size = (1440, 900)
        ws.readiness.record_dialog("workholding")
        pump_frames(6)
        popup = ws.readiness.record_popup
        scroll = next(w for w in popup.walk() if isinstance(w, ScrollView))
        assert scroll.height >= scroll.children[0].height
        popup.dismiss()
    finally:
        Window.size = old_size


def test_stock_form_resizes_and_invalid_units_never_apply(kivy_app, monkeypatch):
    from kivy.core.window import Window
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    configure_machine = Mock()
    monkeypatch.setattr(ws.machine.gcode_viewer, "configure_machine", configure_machine)
    old_size = Window.size
    try:
        Window.size = (1000, 700)
        ws._machine_setup()
        pump_frames(6)
        popup = next(w for w in Window.children if isinstance(w, Popup))
        assert popup.height <= Window.height * 0.9
        field = next(w for w in popup.walk() if isinstance(w, QuantityField))
        field.text = "10 rpm"
        next(w for w in popup.walk() if isinstance(w, Action) and "Apply" in w.text).dispatch("on_release")
        configure_machine.assert_not_called()
        popup.dismiss()
    finally:
        Window.size = old_size
