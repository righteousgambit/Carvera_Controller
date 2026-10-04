from unittest.mock import Mock

from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations

from .conftest import pump_frames


def test_inverse_time_card_tracks_source_and_distinguishes_unknown_joint_demand(kivy_app, monkeypatch, tmp_path):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.operation_panel
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G54 G49\nG0 X0 Y0 Z0\nG93 G1 X10 F2\nG1 X20\nG94 G1 X30 F300\n"
    )
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    send, seek = Mock(), Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    monkeypatch.setattr(workspace.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    panel.inspect_line(3, seek=False)
    assert panel.motion_demand.parent is panel.inspection
    assert "30 s requested for the entire block" in panel.motion_demand_summary.text
    assert "20 mm/min average" in panel.motion_demand_summary.text
    assert "Joint demand unknown" in panel.motion_demand_summary.text
    assert "not machine-joint or TCP motion" in panel.motion_demand_summary.text
    panel.inspect_line(4, seek=False)
    assert "Requested duration unknown" in panel.motion_demand_summary.text
    assert "explicit F word" in panel.motion_demand_summary.text
    panel.inspect_line(5, seek=False)
    assert panel.motion_demand.parent is None
    panel.inspect_line(3, seek=False)
    panel.inspection.remove_widget(panel.motion_demand)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel.motion_demand)
    popup = Popup(title="Inverse-time motion review", content=scroll, size_hint=(None, None), size=(900, 650))
    popup.open()
    try:
        pump_frames(5)
        assert panel.motion_demand_summary.height > 0
        assert panel.motion_demand_summary.right <= panel.motion_demand.right
        panel.motion_demand.export_to_png(str(tmp_path / "inverse-time-review.png"))
    finally:
        popup.dismiss()
        scroll.remove_widget(panel.motion_demand)
    panel.inspect_line(5, seek=False)
    send.assert_not_called()
    seek.assert_not_called()
