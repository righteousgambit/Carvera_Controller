"""First-use probing retains modal/jog protection without eager startup widgets."""

from unittest.mock import Mock

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.main import ZPROBE_TOOL_NUMBER
from tests.integration.conftest import pump_frames


def test_unopened_probing_does_not_construct_on_jog_or_modal_readback(kivy_app, monkeypatch):
    root = kivy_app.root
    assert root.probing_popup is None
    monkeypatch.setattr(root.controller, "setJogMode", Mock())
    root.update_ui_for_jog_mode_cont()
    root.update_ui_for_jog_mode_step()
    root._is_popup_open()
    root._popup_prevents_jogging()
    assert root.probing_popup is None


def test_first_open_ready_immediately_retains_settings_and_restores_jog(kivy_app, monkeypatch):
    root = kivy_app.root
    old_tool, old_mode, old_keyboard = CNC.vars["tool"], root.controller.jog_mode, root.keyboard_jog_control
    monkeypatch.setattr(root.controller, "stopContinuousJog", Mock())
    monkeypatch.setattr(root, "_machine_allows_jogging", Mock(return_value=True))
    monkeypatch.setattr(kivy_app, "jog_controls_enabled", True)
    monkeypatch.setattr(root.controller, "setJogMode", Mock())
    try:
        CNC.vars["tool"] = ZPROBE_TOOL_NUMBER
        root.controller.jog_mode = Controller.JOG_MODE_CONTINUOUS
        root.keyboard_jog_control = True
        root.open_probing_popup()
        popup = root.probing_popup
        assert popup._is_open and not root.keyboard_jog_control
        assert popup.single_axis_settings is popup.ids.single_axis_settings
        assert len(popup._settings_panels) == 7
        assert all(popup.ids[name].disabled for name in ("step_xy", "step_a", "step_z"))
        popup.single_axis_settings.ids.ProbeTipDiameter.text = "4.25"
        root.update_ui_for_jog_mode_step()
        assert all(not popup.ids[name].disabled for name in ("step_xy", "step_a", "step_z"))
        popup.dismiss(animation=False)
        assert root.keyboard_jog_control
        root.open_probing_popup()
        assert root.probing_popup is popup
        assert popup.single_axis_settings.ids.ProbeTipDiameter.text == "4.25"
        assert not root.keyboard_jog_control
    finally:
        if root.probing_popup is not None:
            root.probing_popup.dismiss(animation=False)
        CNC.vars["tool"] = old_tool
        root.controller.jog_mode = old_mode
        root.keyboard_jog_control = old_keyboard
        pump_frames(3)


def test_nonprobe_tool_does_not_build_probing_workbench(kivy_app, monkeypatch):
    root = kivy_app.root
    retained = root.probing_popup
    monkeypatch.setattr(root, "probing_popup", None)
    monkeypatch.setattr(root, "_ensure_probing_popup", Mock(side_effect=AssertionError("unexpected construction")))
    selection = Mock()
    monkeypatch.setattr("carveracontroller.main.SelectAndCalibrateProbePopup", Mock(return_value=selection))
    old_tool, old_selection = CNC.vars["tool"], root.select_probe_popup
    try:
        CNC.vars["tool"] = 1
        root.open_probing_popup()
        selection.open.assert_called_once_with()
        assert root.probing_popup is None
    finally:
        CNC.vars["tool"] = old_tool
        root.select_probe_popup = old_selection
        root.probing_popup = retained
