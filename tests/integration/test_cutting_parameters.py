from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.metrics import dp

from carveracontroller.desktop_cutting_parameters import CuttingParameterBench
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


def test_unit_fields_program_snapshot_and_narrow_layout(kivy_app, tmp_path):
    program = ProgramOperations.from_text("G20 G90 G95\nT2 M6\nS12000 M3\nG1 X1 F0.001")
    op = SimpleNamespace(program=program, selected_line=4)
    comparison = SimpleNamespace(
        selected=2,
        rows=[SimpleNamespace(number=2, name="Quarter-inch", library_diameter_mm=6.35)],
        workspace=SimpleNamespace(operation_panel=op),
    )
    bench = CuttingParameterBench(comparison)
    bench.width = dp(360)
    bench.load_program_line()
    assert bench.fields["feed"].value() == pytest.approx(304.8)
    assert bench.source_snapshot[:2] == (program.file_hash, 4)
    bench.fields["flutes"].text = "3"
    bench.fields["max_chip"].text = "0.0002 in"
    bench.calculate()
    assert bench.result.chip_mm_tooth == pytest.approx(304.8 / 36000)
    assert "exceeds" in bench.output.text and "unqualified" in bench.output.text
    bench.toggle_engagement()
    pump_frames(12)
    assert all(f.width > dp(200) for f in bench.fields.values())
    bench.export_to_png(str(tmp_path / "cutting-360.png"))
    bench.fields["feed"].text = "10 ipm"
    assert bench.result is None and "Inputs changed" in bench.output.text
    before = tuple(f.text for f in bench.fields.values())
    op.selected_line = 1
    bench.load_program_line()
    assert "Cannot import" in bench.output.text and before == tuple(f.text for f in bench.fields.values())
    bench.fields["flutes"].text = "2.5"
    bench.calculate()
    assert bench.result is None and "Cannot review" in bench.output.text


def test_tool_review_route_no_store_or_machine_mutation(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel = ws.tool_comparison
    monkeypatch.setattr(panel, "rows", ())
    monkeypatch.setattr(panel, "selected", None)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    generation = ws.profile_store.generation
    panel.open_cutting_parameters()
    bench = panel.cutting_parameter_bench
    bench.load_program_line()
    assert bench.result is None
    assert "Cannot import" in bench.output.text
    panel.custody.popup.dismiss()
    pump_frames(3)
    assert ws.profile_store.generation == generation
    send.assert_not_called()


def test_selected_line_routes_review_and_disables_unsupported_feed(kivy_app, monkeypatch):
    from carveracontroller.machine.move_inspection import MoveInspector

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    program = ProgramOperations.from_text("G21 G90 G94\nT2 M6\nS12000 M3\nG0 X0 Y0 Z0\nG1 X5 F600\nG93 G1 X10 F2")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.inspect_line(5, seek=False)
    assert not panel.move_cutting_action.disabled
    panel.move_cutting_action.trigger_action(0)
    pump_frames(5)
    bench = ws.tool_comparison.cutting_parameter_bench
    assert bench.source_snapshot[:2] == (program.file_hash, 5)
    assert bench.fields["rpm"].value() == 12000
    assert bench.fields["feed"].value() == 600
    ws.tool_comparison.custody.popup.dismiss()
    panel.inspect_line(6, seek=False)
    assert panel.move_cutting_action.disabled
    panel.reset_move_card("unloaded")
    assert panel.move_cutting_action.disabled
    send.assert_not_called()


def test_engagement_disclosure_units_unknown_demand_and_invalidation(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    bench = CuttingParameterBench(SimpleNamespace(selected=None, rows=(), workspace=ws))
    bench.width = dp(360)
    assert bench.engagement_grid.parent is None
    bench.engagement_action.trigger_action(0)
    pump_frames(12)
    assert bench.engagement_grid.parent is bench.engagement_holder
    for key, text in {
        "diameter": "1/4 in",
        "flutes": "3",
        "rpm": "12000",
        "feed": "600",
        "radial": "0.125 in",
        "axial": "2",
        "energy": "2",
        "max_power": "100",
        "max_torque": "0.05",
    }.items():
        bench.fields[key].text = text
    bench.calculate()
    assert bench.result.removal_mm3_min == pytest.approx(3810)
    assert bench.result.cutting_power_w == pytest.approx(127)
    assert len(bench.result.violations) == 2
    assert "in³/min" in bench.output.text and "Estimated cutting power 127" in bench.output.text
    bench.engagement_action.trigger_action(0)
    pump_frames(5)
    assert bench.engagement_grid.parent is None
    assert bench.fields["radial"].text == "0.125 in"
    bench.fields["energy"].text = ""
    assert bench.result is None
    bench.calculate()
    assert bench.result.cutting_power_w is None
    assert "demand unknown" in bench.output.text
    bench.fields["axial"].text = ""
    bench.calculate()
    assert bench.result is None and "both radial" in bench.output.text
    send.assert_not_called()


def test_operation_settings_route_exact_snapshot_without_changing_selection(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.desktop_cutting_parameters import OperationCuttingBench
    from carveracontroller.machine.move_inspection import MoveInspector

    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT2 M6\nS12000 M3\nG0 X0 Y0 Z0\n"
        "(Operation: Face)\n" + "\n".join(f"G1 X{i + 1} F{100 + i}" for i in range(14))
    )
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    panel.select(program.operations[-1])
    selected = panel.selected_line
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.operation_cutting_action.trigger_action(0)
    pump_frames(8)
    bench = panel.operation_cutting_bench
    assert isinstance(bench, OperationCuttingBench) and len(bench.items.children) == 12
    assert "14 distinct" in bench.context.text
    bench.following.trigger_action(0)
    pump_frames(5)
    assert len(bench.items.children) == 2 and bench.following.disabled
    bench.size_hint_x = None
    bench.width = dp(360)
    pump_frames(8)
    assert bench.width == dp(360)
    bench.export_to_png(str(tmp_path / "operation-cutting-360.png"))
    bench.choose(bench.review.settings[-1])
    pump_frames(8)
    target = ws.tool_comparison.cutting_parameter_bench
    assert target.source_snapshot[:2] == (program.file_hash, 19)
    assert target.fields["feed"].value() == 113
    assert panel.selected_line == selected
    ws.tool_comparison.custody.popup.dismiss()
    monkeypatch.setattr(panel, "program", None)
    bench.choose(bench.review.settings[0])
    assert "changed" in bench.error.text
    send.assert_not_called()


def test_explicit_radial_model_toggle_geometry_and_narrow_report(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    bench = CuttingParameterBench(SimpleNamespace(selected=None, rows=(), workspace=ws))
    bench.size_hint_x = None
    bench.width = dp(360)
    for key, value in {
        "diameter": "1/4 in",
        "flutes": "3",
        "rpm": "12000",
        "feed": "10 ipm",
        "radial": "0.025 in",
        "axial": "2",
    }.items():
        bench.fields[key].text = value
    bench.calculate()
    assert bench.result.ideal_max_chip_mm is None
    assert "unassessed" in bench.output.text
    bench.radial_model_action.trigger_action(0)
    assert bench.result is None
    bench.calculate()
    assert bench.result.ideal_max_chip_mm == pytest.approx(254 / 36000 * 0.6)
    assert "straight wall" in bench.output.text and "No feed compensation" in bench.output.text
    bench.toggle_engagement()
    pump_frames(12)
    bench.export_to_png(str(tmp_path / "radial-chip-360.png"))
    before = {k: f.text for k, f in bench.fields.items()}
    bench.radial_model_action.trigger_action(0)
    assert bench.result is None and before == {k: f.text for k, f in bench.fields.items()}
    bench.fields["radial"].text = ""
    bench.fields["axial"].text = ""
    bench.radial_model_action.trigger_action(0)
    bench.calculate()
    assert bench.result is None and "requires declared" in bench.output.text
    send.assert_not_called()
