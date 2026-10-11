from dataclasses import replace
from unittest.mock import Mock

from carveracontroller.machine.run_recording import RecordingReplay, RunRecording, selected_context
from tests.integration.test_imported_stock_workflow import settle, stock_record
from tests.integration.test_imported_stock_workflow import stock_case as stock_case


def test_recorded_stock_restore_withholds_missing_source_and_reuses_exact_geometry(stock_case, tmp_path, monkeypatch):
    ws, viewer, _cad, send = stock_case
    ws.prepare_stock_model(stock_record(tmp_path))
    settle(ws)
    retained = viewer.machine_setup
    model = retained.stock_model
    program = tmp_path / "recorded.nc"
    program.write_text("G21 G90\nG0 Z10\n")
    setup = retained.record()
    panel = ws.run_recording_panel
    panel.load(RecordingReplay(RunRecording(context=selected_context(program, setup)).export_bytes()))
    configure = Mock(wraps=viewer.configure_machine)
    monkeypatch.setattr(viewer, "configure_machine", configure)
    missing = replace(retained, stock_model=None)
    monkeypatch.setattr(viewer, "machine_setup", missing)
    panel.restore_setup()
    assert viewer.machine_setup is missing and "Recorded stock source differs" in panel.notice.text
    configure.assert_not_called()
    viewer.machine_setup = retained
    panel.restore_setup()
    assert (
        viewer.machine_setup.stock_model is model and "Recorded stock and offset applied" in panel.scene_inventory.text
    )
    assert configure.call_args.kwargs["stock_model"] is model and "stock_source" not in configure.call_args.kwargs
    block = {key: value for key, value in setup.items() if key != "stock_source"}
    panel.load(RecordingReplay(RunRecording(context=selected_context(program, block)).export_bytes()))
    panel.restore_setup()
    assert viewer.machine_setup.stock_model is None
    send.assert_not_called()
