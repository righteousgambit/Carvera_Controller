from types import SimpleNamespace
from unittest.mock import Mock

from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import ACCENT
from carveracontroller.desktop_operation_list import OperationList
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


def test_large_operation_list_reuses_rows_and_routes_current_analysis_only(kivy_app):
    program = ProgramOperations.from_text(
        "G21 G90 G54\nT1 M6\nG0 X0 Y0 Z5\n"
        + "\n".join(f"(OPERATION: Pocket {number})\nG1 X{number} F100" for number in range(1000))
    )
    owner = SimpleNamespace(program=program, selected_operation=None, select=Mock())
    listing = OperationList(owner)
    popup = Popup(title="Operation list acceptance", content=listing, size_hint=(None, None), size=(dp(440), dp(360)))
    popup.open()
    try:
        listing.load(program)
        pump_frames(8)
        assert len(listing.data) == len(program.operations) == 1001
        assert 0 < len(listing.rows) <= 8
        first_row = listing.rows[0][1]
        first_row.dispatch("on_release")
        owner.select.assert_called_once_with(first_row.operation)
        owner.select.reset_mock()
        last = program.operations[-1]
        owner.selected_operation = last
        listing.select(last)
        pump_frames(8)
        assert 0 < len(listing.rows) <= 8
        row = next(row for operation, row in listing.rows if operation is last)
        assert row.base_color == ACCENT
        row.dispatch("on_release")
        owner.select.assert_called_once_with(last)
        owner.select.reset_mock()
        row.focus = True
        replacement = ProgramOperations.from_text("G21 G90\n(OPERATION: Replacement)\nG1 X1 F100")
        owner.program = replacement
        # A stale rendered row cannot route before asynchronous RV refresh.
        row.dispatch("on_release")
        owner.select.assert_not_called()
        listing.load(replacement)
        pump_frames(8)
        assert all(operation in replacement.operations for operation, _row in listing.rows)
        assert all(not row.focus for _operation, row in listing.rows)
        assert listing.scroll_y == 1
        listing.load(None)
        pump_frames(4)
        assert not listing.data and not listing.rows and listing.height == 0
    finally:
        popup.dismiss()
        pump_frames(3)
