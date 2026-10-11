import threading
from unittest.mock import Mock

from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


def test_clearing_program_cooperatively_stops_departing_analysis_and_rejects_delivery(kivy_app, monkeypatch, tmp_path):
    panel = kivy_app.root.desktop_workspace.operation_panel
    original = ProgramOperations.from_text
    started, stopped = threading.Event(), threading.Event()
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    path = tmp_path / "cancelled-analysis.nc"
    content = "; cancellation study\nG21 G90 G17 G94 G54\nG0 X0 Y0 Z0\nG1 X5 F100"
    path.write_text(content)

    def parse(text, **kwargs):
        if text.startswith("; cancellation study"):
            started.set()
            try:
                while not kwargs["cancelled"]():
                    stopped.wait(0.005)
                raise InterruptedError("Cancelled study")
            finally:
                stopped.set()
        return original(text, **kwargs)

    monkeypatch.setattr(ProgramOperations, "from_text", staticmethod(parse))
    panel.load(str(path))
    assert started.wait(3)
    panel.load(None)
    assert stopped.wait(3)
    pump_frames(8)
    assert panel.program is None and panel.inspector is None
    assert panel.note.text == "Choose a local program to inspect operations and tool banks."
    assert path.read_text() == content
    send.assert_not_called()
