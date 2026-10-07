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
