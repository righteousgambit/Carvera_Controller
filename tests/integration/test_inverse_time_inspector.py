from unittest.mock import Mock

import pytest
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
    assert "explicit F word" in panel.motion_demand_status.text
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


def test_declared_joint_motion_handoff_binds_revision_line_duration_without_motion(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
    from carveracontroller.addons.manufacturing_simulation.kinematics import Joint, MachineKinematics, Transform
    from carveracontroller.machine.inverse_time import JointSample, JointVelocityLimit, analyze_mapped_joint_motion

    workspace = kivy_app.root.desktop_workspace
    panel = workspace.operation_panel
    program = ProgramOperations.from_text("G21 G90 G93 G54\nG1 A90 F2\nG1 A180 F4\n")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    monkeypatch.setattr(panel, "joint_motion_reviews", {})
    report = analyze_mapped_joint_motion(
        30,
        (JointSample(0, (("table", 0),)), JointSample(1, (("table", 90),))),
        (JointVelocityLimit("table", "rotary", 2, "declared test configuration"),),
        MachineKinematics(
            work_chain=(Joint("table", "rotary", Vec3(0, 0, 1), -180, 180),),
            tool_base=Transform(translation=Vec3(100, 0, 0)),
        ),
        10,
        model_source="declared test table model",
        trajectory_source="test joint trajectory; no backend observation",
    )
    send, seek = Mock(), Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    monkeypatch.setattr(workspace.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    panel.review_joint_motion(program.file_hash, 2, report)
    assert "World tip path 0 mm" in panel.motion_demand_summary.text
    assert "EXCEEDS LIMIT" in panel.motion_demand_summary.text
    assert "actual machine mapping" in panel.motion_demand_summary.text
    assert "Declared limits exceeded: table" in panel.motion_demand_status.text
    assert panel.motion_demand_details.parent is None
    assert "declared test table model" in panel.motion_demand_details.text
    assert "Cartesian error is not bounded" in panel.motion_demand_details.text
    panel.inspection.remove_widget(panel.motion_demand)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel.motion_demand)
    popup = Popup(title="Declared joint motion study", content=scroll, size_hint=(None, None), size=(950, 950))
    popup.open()
    try:
        pump_frames(5)
        panel.motion_demand.export_to_png(str(tmp_path / "mapped-joint-study.png"))
        panel.motion_demand_details_action.dispatch("on_release")
        pump_frames(5)
        assert panel.motion_demand_details.parent is panel.motion_demand
        panel.motion_demand.export_to_png(str(tmp_path / "mapped-joint-model.png"))
        panel.motion_demand_details_action.dispatch("on_release")
        assert panel.motion_demand_details.parent is None
    finally:
        popup.dismiss()
        scroll.remove_widget(panel.motion_demand)
    with pytest.raises(ValueError, match="different"):
        panel.review_joint_motion("other revision", 2, report)
    with pytest.raises(ValueError, match="duration"):
        panel.review_joint_motion(program.file_hash, 3, report)
    panel.inspect_line(3, seek=False)
    assert "Joint demand unknown" in panel.motion_demand_summary.text
    assert len(panel.joint_motion_reviews) == 1
    send.assert_not_called()
    seek.assert_not_called()
    panel.load(None)
    assert not panel.joint_motion_reviews and panel.motion_demand.parent is None


def test_joint_corner_paging_keeps_every_reversal_bound_to_its_source_line(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
    from carveracontroller.addons.manufacturing_simulation.kinematics import Joint, MachineKinematics
    from carveracontroller.machine.inverse_time import JointSample, JointVelocityLimit, analyze_mapped_joint_motion

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    program = ProgramOperations.from_text("G21 G90 G93 G54\nG1 A90 F2\nG1 A180 F4\n")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    monkeypatch.setattr(panel, "joint_motion_reviews", {})
    send, seek = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    samples = tuple(JointSample(i / 72, (("A", float(i % 2)),)) for i in range(73))
    report = analyze_mapped_joint_motion(
        30,
        samples,
        (JointVelocityLimit("A", "rotary", 100, "declared test limit"),),
        MachineKinematics(work_chain=(Joint("A", "rotary", Vec3(0, 0, 1), -180, 180),)),
        10,
        model_source="declared test model",
        trajectory_source="explicit alternating joints",
    )
    assert len(report.joint_transitions) == 71
    panel.review_joint_motion(program.file_hash, 2, report)
    assert "reversals: 71" in panel.motion_demand_summary.text
    assert "Corners 1–64 of 71" in panel.motion_demand_details.text
    assert not panel.motion_corner_next.disabled and panel.motion_corner_previous.disabled
    if not panel.motion_demand_details_open:
        panel.toggle_motion_details()
    assert panel.motion_corner_navigation.parent is panel.motion_demand
    panel.motion_corner_next.dispatch("on_release")
    assert "Corners 65–71 of 71" in panel.motion_demand_details.text
    assert "REVERSAL" in panel.motion_demand_details.text
    assert panel.motion_corner_next.disabled and not panel.motion_corner_previous.disabled
    panel.motion_corner_previous.dispatch("on_release")
    assert "Corners 1–64 of 71" in panel.motion_demand_details.text
    from dataclasses import replace

    replacement_report = replace(report, joint_transitions=report.joint_transitions[:1], trajectory_source="new study")
    panel.motion_corner_next.dispatch("on_release")
    assert panel.motion_corner_page == 1
    panel.review_joint_motion(program.file_hash, 2, replacement_report)
    assert panel.motion_corner_page == 0
    assert "Corners 1–1 of 1" in panel.motion_demand_details.text
    assert "new study" in panel.motion_demand_details.text
    assert panel.motion_corner_navigation.parent is None
    panel.review_joint_motion(program.file_hash, 2, report)
    assert panel.motion_corner_navigation.parent is panel.motion_demand
    assert (
        panel.motion_demand.children.index(panel.motion_corner_navigation)
        == panel.motion_demand.children.index(panel.motion_demand_details) + 1
    )
    panel.inspection.remove_widget(panel.motion_demand)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel.motion_demand)
    popup = Popup(title="Joint corner demand", content=scroll, size_hint=(None, None), size=(720, 1000))
    popup.open()
    try:
        pump_frames(5)
        popup.export_to_png(str(tmp_path / "joint-corner-review.png"))
    finally:
        popup.dismiss()
        scroll.remove_widget(panel.motion_demand)
        panel.inspection.add_widget(panel.motion_demand)
    panel.inspect_line(3, seek=False)
    assert panel.motion_corner_page == 0
    assert panel.motion_corner_navigation.parent is None
    send.assert_not_called()
    seek.assert_not_called()
    panel.load(None)
