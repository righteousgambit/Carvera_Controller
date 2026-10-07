from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.metrics import dp

from carveracontroller.desktop_tool_bending import ToolBendingBench
from tests.integration.conftest import pump_frames


def test_bending_bench_unit_inputs_invalidation_and_narrow_layout(kivy_app, tmp_path):
    comparison = SimpleNamespace(
        selected=2, rows=[SimpleNamespace(number=2, name="Quarter-inch", library_diameter_mm=6.35, stickout_mm=30)]
    )
    bench = ToolBendingBench(comparison)
    bench.width = dp(360)
    bench.fields["force"].text = "10 lbf"
    bench.fields["modulus"].text = "600 GPa"
    bench.fields["candidate_diameter"].text = "1/4 in"
    bench.fields["candidate_length"].text = "15 mm"
    bench.calculate()
    assert bench.result is not None
    assert bench.result[0].force_n == pytest.approx(44.482216152605)
    assert "0.125×" in bench.output.text
    assert "T2" in bench.context.text
    pump_frames(12)
    assert bench.height > dp(300)
    for field in bench.fields.values():
        assert field.width > dp(200)
    bench.export_to_png(str(tmp_path / "bending-360.png"))
    bench.fields["force"].text = "20 N"
    assert bench.result is None and "Inputs changed" in bench.output.text
    bench.fields["candidate_length"].text = "0 mm"
    bench.calculate()
    assert bench.result is None and "Cannot compare" in bench.output.text


def test_tool_comparison_routes_bench_without_command_or_store_mutation(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = ws.tool_comparison
    monkeypatch.setattr(panel, "rows", ())
    monkeypatch.setattr(panel, "selected", None)
    generation = ws.profile_store.generation
    panel.open_bending_comparison()
    assert panel.bending_bench.result is None
    assert all(not field.text for field in panel.bending_bench.fields.values())
    panel.custody.popup.dismiss()
    pump_frames(3)
    assert ws.profile_store.generation == generation
    send.assert_not_called()
