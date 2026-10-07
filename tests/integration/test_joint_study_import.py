import json
import threading
from unittest.mock import Mock

from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames
from tests.unit.test_joint_motion_study import record


def configure(kivy_app, monkeypatch, tmp_path):
    panel = kivy_app.root.desktop_workspace.operation_panel
    program = ProgramOperations.from_text("G21 G90 G93 G54\nG1 A90 F2\nG1 A180 F1\n")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    monkeypatch.setattr(panel, "joint_motion_reviews", {})
    panel.inspect_line(2, seek=False)
    data = record()
    data["program_sha256"] = program.file_hash
    path = tmp_path / "declared-joints.json"
    path.write_text(json.dumps(data))
    send, seek = Mock(), Mock()
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    monkeypatch.setattr(panel.workspace.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    return panel, program, path, send, seek


def settle(predicate):
    for _ in range(100):
        pump_frames(2, sleep=0.01)
        if predicate():
            return
    assert predicate()


def test_picker_import_updates_real_selected_block_without_commands(kivy_app, monkeypatch, tmp_path):
    panel, program, path, send, seek = configure(kivy_app, monkeypatch, tmp_path)
    importer = panel.joint_study_import
    copy = Mock()
    monkeypatch.setattr("carveracontroller.desktop_joint_study.Clipboard.copy", copy)
    importer.identity_action.dispatch("on_release")
    assert json.loads(copy.call_args.args[0]) == {"program_sha256": program.file_hash, "line": 2, "seconds": 30}
    importer.action.dispatch("on_release")
    assert importer.browser.popup.parent is not None
    try:
        importer.browser.navigate(path.parent)
        settle(lambda: importer.browser.ready and importer.browser.path == path.parent)
        entry = next(entry for entry in importer.browser.entries if entry.name == path.name)
        importer.browser.select(entry)
        importer.browser.choose_action.dispatch("on_release")
        settle(lambda: importer.browser.closed)
    finally:
        importer.browser.dismiss()
    settle(lambda: not importer.running)
    assert (program.file_hash, 2) in panel.joint_motion_reviews
    assert panel.motion_path.parent is panel.motion_study_views
    assert len(panel.motion_path.plot.coordinates) == 91
    panel.motion_path.select(90)
    assert "preceding interval velocity 3 deg/s" in panel.motion_path.note.text
    assert panel.selected_line == 2
    assert "EXCEEDS LIMIT" in panel.motion_demand_summary.text
    assert "study SHA256" in panel.motion_demand_details.text
    assert "Imported declared" in importer.note.text
    from kivy.uix.popup import Popup

    if importer.parent:
        importer.parent.remove_widget(importer)
    popup = Popup(content=importer, size_hint=(None, None), size=(650, 350))
    popup.open(animation=False)
    try:
        pump_frames(6)
        assert importer.action.right <= importer.right
        assert importer.identity_action.texture_size[1] <= importer.identity_action.height
        importer.export_to_png(str(tmp_path / "joint-study-import.png"))
    finally:
        popup.dismiss(animation=False)
        if importer.parent:
            importer.parent.remove_widget(importer)
        panel.motion_demand.add_widget(importer)
    assert not importer.action.disabled
    assert importer.cancel_action.parent is None
    send.assert_not_called()
    seek.assert_not_called()
    panel.inspect_line(3, seek=False)
    assert importer.note.text == ""
    assert "Joint demand unknown" in panel.motion_demand_summary.text
    assert panel.motion_path.parent is None
    assert panel.motion_path.plot.coordinates == ()


def test_feedback_import_exposes_nonuniform_derivatives_and_provenance_without_motion(kivy_app, monkeypatch, tmp_path):
    panel, program, path, send, seek = configure(kivy_app, monkeypatch, tmp_path)
    data = json.loads(path.read_text())
    data["observed_feedback"] = {
        "source": "Recorded encoder feedback",
        "timing_source": "Selected-block relative time; alignment declaration",
        "duration_seconds": 32,
        "samples": [
            {"seconds": t, "reported": {"table": t * t / 10}, "commanded": {"table": t * t / 10 - 0.1}}
            for t in (0, 5, 15, 32)
        ],
    }
    path.write_text(json.dumps(data))
    importer = panel.joint_study_import
    importer.import_path(path)
    settle(lambda: not importer.running)
    assert "Supplied feedback · 4 samples" in panel.motion_demand_summary.text
    assert "duration 32 s (requested 30 s; difference +2 s)" in panel.motion_demand_summary.text
    assert "acceleration 0.2 deg/s²" in panel.motion_demand_summary.text
    assert "command/reported error 0.1 deg" in panel.motion_demand_summary.text
    assert "Recorded encoder feedback" in panel.motion_demand_details.text
    assert "Between-sample peaks" in panel.motion_demand_details.text
    assert panel.motion_feedback.parent is None
    panel.motion_study_views.actions["Feedback"].dispatch("on_release")
    assert panel.motion_feedback.parent is panel.motion_study_views
    panel.motion_feedback.metric.text = "Velocity"
    panel.motion_feedback.select(1)
    assert "t 10 s" in panel.motion_feedback.note.text
    assert panel.selected_line == 2
    send.assert_not_called()
    seek.assert_not_called()
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    panel.inspection.remove_widget(panel.motion_demand)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel.motion_demand)
    popup = Popup(title="Sourced feedback review", content=scroll, size_hint=(None, None), size=(900, 650))
    popup.open(animation=False)
    try:
        pump_frames(6)
        assert panel.motion_demand_summary.texture_size[1] <= panel.motion_demand_summary.height
        assert panel.motion_demand_summary.right <= scroll.right
        scroll.export_to_png(str(tmp_path / "feedback-review.png"))
        print("Feedback render:", tmp_path / "feedback-review.png")
    finally:
        popup.dismiss(animation=False)
        scroll.remove_widget(panel.motion_demand)
        panel.inspection.add_widget(panel.motion_demand)
    accepted = panel.joint_motion_reviews[(program.file_hash, 2)]
    data["observed_feedback"]["samples"][1]["reported"] = {}
    path.write_text(json.dumps(data))
    importer.import_path(path)
    settle(lambda: not importer.running)
    assert panel.joint_motion_reviews[(program.file_hash, 2)] is accepted
    send.assert_not_called()
    seek.assert_not_called()


def test_invalid_import_retains_previous_study_and_rejects_late_picker(kivy_app, monkeypatch, tmp_path):
    panel, program, path, send, seek = configure(kivy_app, monkeypatch, tmp_path)
    importer = panel.joint_study_import
    importer.import_path(path)
    settle(lambda: not importer.running)
    accepted = panel.joint_motion_reviews[(program.file_hash, 2)]
    path.write_text("{}")
    importer.import_path(path)
    settle(lambda: not importer.running)
    assert "missing or unknown" in importer.note.text
    assert panel.joint_motion_reviews[(program.file_hash, 2)] is accepted
    identity = importer.current()
    panel.inspect_line(3, seek=False)
    importer.import_path(path, identity)
    assert not importer.running and (program.file_hash, 3) not in panel.joint_motion_reviews
    send.assert_not_called()
    seek.assert_not_called()


def test_navigation_cancels_worker_and_discards_even_noncooperative_late_result(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.joint_motion_study import read_joint_study

    panel, program, path, send, seek = configure(kivy_app, monkeypatch, tmp_path)
    importer = panel.joint_study_import
    report = read_joint_study(path, program_sha256=program.file_hash, line=2, seconds=30)
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        returned.set()
        return report

    monkeypatch.setattr("carveracontroller.desktop_joint_study.read_joint_study", delayed)
    importer.import_path(path)
    settle(entered.is_set)
    cancel = importer.cancel_event
    panel.inspect_line(3, seek=False)
    assert cancel.is_set() and not importer.running
    release.set()
    settle(returned.is_set)
    pump_frames(6)
    assert not panel.joint_motion_reviews
    assert importer.note.text == ""
    send.assert_not_called()
    seek.assert_not_called()


def test_unknown_duration_disables_import_and_identity_copy(kivy_app, monkeypatch, tmp_path):
    panel, _, path, send, seek = configure(kivy_app, monkeypatch, tmp_path)
    program = ProgramOperations.from_text("G21 G90 G93 G54\nG1 A90\n")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    panel.inspect_line(2, seek=False)
    importer = panel.joint_study_import
    assert importer.action.disabled and importer.identity_action.disabled
    importer.import_path(path)
    assert not importer.running and not panel.joint_motion_reviews
    send.assert_not_called()
    seek.assert_not_called()
