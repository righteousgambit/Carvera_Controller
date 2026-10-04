from types import SimpleNamespace

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.desktop_job_packages import capture_job
from carveracontroller.desktop_operations import OperationPanel
from carveracontroller.machine.job_packages import load_package, save_package
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations


def test_capture_preserves_program_stock_vise_and_component_assets(tmp_path):
    program = tmp_path / "part.nc"
    program.write_bytes(b"G21\r\nG90\r\n")
    cad = tmp_path / "fixture.json.gz"
    cad.write_bytes(b"fixture bytes")
    viewer = SimpleNamespace(
        machine_setup=MachineSetup((-180, -120, -110), (10, 20, 30), (-10, -20, 0)),
        machine_component_profiles={"fixture": SimpleNamespace(asset_path=str(cad))},
        workholding_offset_mm=(-70, -40, 0),
        workholding_rotation_deg=90,
        jaw_offset_mm=-74,
    )
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(program)),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
        selected_machine_profile=None,
        loaded_toolset=None,
    )
    package = capture_job(workspace)
    assert package.program == program.read_bytes()
    assert package.stock["size_mm"] == [10, 20, 30]
    assert package.stock["alignment_confirmed"] is False
    assert package.vise["rotation_deg"] == 90
    archive = tmp_path / "part.cvjob"
    save_package(package, archive)
    restored = load_package(archive, destination=tmp_path / "restored")
    assert restored.package.fixtures[0]["cad_path"].startswith("asset://")
    assert next(iter(restored.asset_paths.values())).read_bytes() == b"fixture bytes"


def test_capture_rejects_component_without_source(tmp_path):
    program = tmp_path / "part.nc"
    program.write_text("G21")
    viewer = SimpleNamespace(machine_setup=MachineSetup(), machine_component_profiles={"workholding": object()})
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(program)),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
    )
    with pytest.raises(ValueError, match="source asset"):
        capture_job(workspace)


def test_operation_selection_seeks_preview_without_controller():
    calls = []
    viewer = SimpleNamespace(set_distance_by_lineidx=lambda *args: calls.append(args))
    panel = OperationPanel(SimpleNamespace(machine=SimpleNamespace(gcode_viewer=viewer)))
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\n(Operation: Face)\nG1 X0 Y0 Z0 F100\nG1 X10\n")
    panel.generation = 1
    panel._loaded(1, program, None)
    operation = program.operations[-1]
    panel.select(operation)
    assert calls == [(operation.start_line, 0)]
    assert operation.name in panel.detail.text
    assert "Slot 1" in panel.banks.text
    panel._loaded(0, None, "stale failure")
    assert panel.program is program


def test_move_inspection_and_navigation_remain_preview_only():
    calls = []
    viewer = SimpleNamespace(set_distance_by_lineidx=lambda *args: calls.append(args))
    panel = OperationPanel(SimpleNamespace(machine=SimpleNamespace(gcode_viewer=viewer)))
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G94 G54 G49\nT17 M6\nG0 X0 Y0 Z0\n(Operation: Finish wall)\nG1 X10 F600\nG0 Z1\nG1 X20"
    )
    panel.generation = 1
    panel._loaded(1, program, None)
    panel.line_field.text = "5"
    panel.inspect_entry()
    assert calls == [(5, 0)]
    assert "Program end: X 10.000" in panel.explanation.text
    assert "Frame: G54" in panel.explanation.text
    assert "600 mm/min" in panel.explanation.text
    assert "Machine pose unavailable" in panel.explanation.text
    panel.step(1)
    assert calls[-1] == (6, 0)
    assert "> 6: G0 Z1" in panel.explanation.text
    panel.line_field.text = "999"
    panel.inspect_entry()
    assert len(calls) == 2
    assert "Choose a source line" in panel.explanation.text
    panel.search_generation = 2
    panel._search_loaded(2, panel.inspector, (5, 7))
    buttons = [child for child in panel.results.children if hasattr(child, "trigger_action")]
    buttons[-1].dispatch("on_release")
    assert calls[-1] == (5, 0)
    panel._search_loaded(1, panel.inspector, ())
    assert len(panel.results.children) == 3
    panel.load(None)
    assert panel.inspector is None and not panel.results.children
    panel._search_loaded(2, MoveInspector(program), (5,))
    assert not panel.results.children


@pytest.mark.parametrize("width", [420, 800])
def test_move_explanation_wraps_without_fixed_height_clipping(width):
    from kivy.clock import Clock

    panel = OperationPanel(
        SimpleNamespace(machine=SimpleNamespace(gcode_viewer=SimpleNamespace(set_distance_by_lineidx=lambda *_: None)))
    )
    panel.width = width
    panel.generation = 1
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G94 G54 G49\nT1 M6\nG0 X0 Y0 Z0\n"
        "(Operation: A long operation name to check responsive desktop wrapping)\nG1 X10 F100\n#1=2\nG1 X20"
    )
    panel._loaded(1, program, None)
    panel.select(program.operations[-1])
    panel.inspect_line(7)
    for _ in range(5):
        Clock.tick()
    panel.explanation.texture_update()
    assert panel.explanation.text_size[1] is None
    assert panel.explanation.height >= panel.explanation.texture_size[1]
    assert panel.explanation.width < width
    assert "Inherited uncertainty" in panel.explanation.text


def test_playback_inspection_updates_operation_without_seeking_or_clobbering_entry():
    calls = []
    workspace = SimpleNamespace(
        active_section="Job",
        machine=SimpleNamespace(gcode_viewer=SimpleNamespace(set_distance_by_lineidx=lambda *args: calls.append(args))),
    )
    panel = OperationPanel(workspace)
    panel.generation = 1
    panel._loaded(
        1,
        ProgramOperations.from_text(
            "G21 G90 G94 G54\nG0 X0 Y0 Z0\n(Operation: Rough)\nG1 X10 F100\n(Operation: Finish)\nG1 X20"
        ),
        None,
    )
    panel.observe_preview_line(4.0)
    assert panel.selected_operation.name == "Rough"
    panel.observe_preview_line(6)
    assert panel.selected_operation.name == "Finish"
    assert not calls
    panel.line_field.focus = True
    panel.observe_preview_line(4)
    assert panel.selected_line == 6
    panel.line_field.focus = False
    workspace.active_section = "Scene"
    panel.observe_preview_line(4)
    assert panel.selected_line == 6
    panel.observe_preview_line(99)
    assert not calls


@pytest.mark.parametrize("width,height", [(600, 350), (360, 180)])
def test_empty_content_labels_collapse_and_inspection_keeps_history_visible(width, height):
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.scrollview import ScrollView

    panel = OperationPanel(
        SimpleNamespace(machine=SimpleNamespace(gcode_viewer=SimpleNamespace(set_distance_by_lineidx=lambda *_: None)))
    )
    assert panel.detail.height == 0 and panel.banks.height == 0
    outer = ScrollView(size=(width, height), size_hint=(None, None))
    host = BoxLayout(size=(width, height), size_hint=(None, None))
    host.add_widget(outer)
    body = BoxLayout(orientation="vertical", size_hint_y=None)
    body.bind(minimum_height=body.setter("height"))
    body.add_widget(panel)
    outer.add_widget(body)
    panel.generation = 1
    panel._loaded(1, ProgramOperations.from_text("G21 G90 G17 G91.1 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X10 F100"), None)
    for _ in range(5):
        Clock.tick()
    panel.inspect_line(4, seek=True)
    for _ in range(5):
        Clock.tick()
    assert outer.scroll_y < 1
    bottom = outer.to_window(outer.x, outer.y)[1]
    top = outer.to_window(outer.x, outer.top)[1]
    for control in (panel.back_action, panel.forward_action):
        assert control.to_window(control.x, control.y)[1] >= bottom
        assert control.to_window(control.x, control.top)[1] <= top


def test_explicit_seek_is_not_replaced_by_preceding_segment_callback():
    workspace = SimpleNamespace(active_section="Job")
    viewer = SimpleNamespace(set_distance_by_lineidx=lambda line, ratio: panel.observe_preview_line(line - 1))
    workspace.machine = SimpleNamespace(gcode_viewer=viewer)
    panel = OperationPanel(workspace)
    panel.generation = 1
    panel._loaded(1, ProgramOperations.from_text("G21 G90 G94 G54\nG0 X0 Y0 Z0\nG1 X10 F100\nG1 X20"), None)
    panel.inspect_line(4, seek=True)
    assert panel.selected_line == 4
    assert "> 4: G1 X20" in panel.explanation.text
    assert panel._seeking is False
    panel.observe_preview_line(3)
    assert panel.selected_line == 3
