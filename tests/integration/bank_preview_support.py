"""Completed local preview fixture with restored session navigation and program."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_job_transaction import LocalJobTransaction
from tests.integration.conftest import pump_frames
from tests.integration.test_completed_program_source import load, until

BANK_SOURCE = "G21 G90\nG0 X0 Y0 Z10\n" + "\n".join(f"T{tool} M6" for tool in range(1, 13)) + "\n"


@pytest.fixture
def completed_bank_preview(kivy_app, monkeypatch, tmp_path):
    app, root = kivy_app, kivy_app.root
    ws = root.desktop_workspace
    assert not root.loading_file
    backup = LocalJobTransaction(ws)
    previous_program = ws.operation_panel.program
    navigation = ws.active_section, ws.setup_tasks.active
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    path = tmp_path / "completed-bank.nc"
    path.write_text(BANK_SOURCE)
    try:
        program = load(app, path)
        yield SimpleNamespace(app=app, root=root, workspace=ws, program=program, path=path, send=send)
    finally:
        root.progress_popup.dismiss(animation=False)
        root.message_popup.dismiss(animation=False)
        root.loading_file = False
        backup.rollback()
        ws.operation_panel.load(app.selected_local_filename or None)
        if previous_program is not None:
            until(lambda: ws.operation_panel.program is not None, "Previous program analysis did not restore")
        ws.setup_tasks.show(navigation[1])
        ws.select(navigation[0])
        pump_frames(2)
        send.assert_not_called()
