import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    StockVolume,
    ToolGeometry,
    Vec3,
)
from carveracontroller.addons.manufacturing_simulation.clearance import analyze_clearance
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_segments

from .conftest import pump_frames


def test_plot_filters_selection_source_seek_and_stale_inputs(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G91.1 G94 G54\nT1 M6\nG0 X1 Y0 Z0\nG3 X0 Y1 I-1 J0 F100\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    segments = simulation_segments(program)
    tool = ToolGeometry(2, 2, 2, 5, 6, 3)
    scene = CollisionScene((CollisionObstacle("jaw", AABB(Vec3(0, 4, 0), Vec3(1, 5, 8))),))
    scene.stock = AABB(Vec3(-2, -2, 0), Vec3(2, 2, 1))
    starting_stock = StockVolume(scene.stock, 0.5)
    for name, value in (
        ("clearance_inputs", (segments, {"1": tool}, scene, starting_stock)),
        ("clearance_identity", panel._identity()),
        ("clearance_context", panel._context()),
        ("running", False),
        ("clearance_stale", False),
        ("rest_context", None),
        ("_input_signature", None),
    ):
        monkeypatch.setattr(panel, name, value)
    seek, send, inspect, reveal = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
    monkeypatch.setattr(ws.operation_panel, "_reveal", reveal)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(panel.clearance_tolerance, "text", "0.002in")
    panel.review_clearance()
    deadline = time.monotonic() + 10
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running
    card = panel.clearance_card
    assert card.parent is panel.content
    monkeypatch.setattr(panel.content, "width", 900)
    card.size = (700, 600)
    pump_frames(5)
    assert "motions examined" in card.summary.text
    assert card.report.tolerance_mm == 0.0508
    assert card.report.stock_resolution_mm == 0.5
    assert "prior completed motions" in card.summary.text
    assert card.plot.rendered
    card.component.text = "holder"
    pump_frames(2)
    assert all(p.component == "holder" for p in card.plot.rendered)
    card.scale.text = "Auto"
    pump_frames(2)
    maximum = max(p.upper_mm for p in card.report.points if p.component == "holder")
    assert card.plot.y_maximum == maximum
    assert f"0–{maximum:g} mm" in card.axes.text
    card.scale.text = "5 mm"
    card.plot.paint()
    assert card.plot.scale_mm == 5
    point = card.plot.rendered[0]
    extent = max(p.end_distance_mm for p in card.report.points)
    left, _, width, _ = card.plot.plot_bounds()
    x = left + width * (point.start_distance_mm + point.end_distance_mm) / 2 / extent
    assert card.plot.on_touch_down(SimpleNamespace(pos=(x, card.plot.center_y), x=x))
    point = card.plot.selected
    assert "holder" in card.details.text and "jaw" in card.details.text
    card.inspect.dispatch("on_release")
    seek.assert_called_once_with(point.line, point.source_ratio)
    inspect.assert_called_with(point.line, seek=False)
    assert inspect.call_count == 2  # Selection updates the inspector; explicit action seeks the preview.
    card.source_action.dispatch("on_release")
    assert inspect.call_count == 3
    assert seek.call_count == 1  # Revealing the source inspector does not move the preview.
    reveal.assert_called_once_with(ws.operation_panel.inspection)
    assert "Clearance:" in panel.selection_note.text
    assert "Physical clearance unqualified" in card.headline.text
    assert card.summary.parent is None
    card.model_action.dispatch("on_release")
    pump_frames(2)
    assert card.summary.parent is card.model_body
    assert "prior completed motions" in card.summary.text
    card.model_action.dispatch("on_release")
    assert card.summary.parent is None
    # Repeated redraws own a separate canvas and retain stencil clipping.
    original = tuple(card.plot.canvas.children)
    for width in (350, 1200, 600):
        card.plot.width = width
        card.plot.paint()
    assert tuple(card.plot.canvas.children) == original
    panel.content.remove_widget(card)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(card)
    popup = Popup(title="Isolated clearance workbench render", content=scroll, size_hint=(None, None), size=(900, 850))
    popup.open()
    try:
        pump_frames(8)
        image = tmp_path / "clearance-trace.png"
        card.export_to_png(str(image))
        assert image.exists() and card.width > 700
    finally:
        popup.dismiss()
        scroll.remove_widget(card)
    viewer.library_tool_table_mm[1] = replace(definition, stickout=6)
    from carveracontroller.machine import geometry_changes

    with monkeypatch.context() as changes:
        asset_read = Mock(side_effect=AssertionError("Refresh must not read CAD files"))
        changes.setattr(geometry_changes, "asset_digest", asset_read)
        panel.refresh_inputs()
        asset_read.assert_not_called()
    assert panel.rest_context is None  # Captured-clearance freshness does not need a residual baseline.
    assert panel.clearance_stale and panel.clearance_action.disabled
    assert card.inspect.disabled and card.source_action.disabled
    assert card.plot.selected is None
    assert "Captured clearance inputs changed" in panel.input_status.text
    assert "historical" in card.headline.text
    popup = panel.review_changes()
    try:
        pump_frames(3)
        labels = [widget.text for widget in popup.content.walk() if hasattr(widget, "text")]
        assert any("Comparing: Captured clearance" in text for text in labels)
        assert any("T1 stickout" in text and "Previous: 5" in text and "Current: 6" in text for text in labels)
    finally:
        popup.dismiss()
    card.inspect.dispatch("on_release")
    card.source_action.dispatch("on_release")
    assert seek.call_count == 1
    assert reveal.call_count == 1
    assert "Inputs changed" in card.summary.text
    send.assert_not_called()


def test_desktop_dropdown_wraps_long_action_labels(kivy_app):
    from kivy.metrics import dp, sp

    from carveracontroller.desktop_components import RAISED, TEXT, Choice, ChoiceOption

    choice = Choice(text="More actions…", values=("Review change impact", "Load rest stock"))
    options = choice._dropdown.container.children
    assert len(options) == 2
    for option in options:
        assert isinstance(option, ChoiceOption)
        assert option.font_size == sp(12)
        assert tuple(option.color) == TEXT
        assert tuple(option.background_color) == RAISED
        for width in (dp(140), dp(75)):
            choice._dropdown.width = width
            choice._dropdown.container.width = width
            pump_frames(3)
            assert option.width == width
            assert option.text_size[0] == width - dp(20)
            assert option.texture_size[0] <= width
            assert option.height >= option.texture_size[1] + dp(16)
    assert not choice.is_open


def test_all_clearance_candidates_search_page_and_keep_captured_identity(kivy_app, tmp_path):
    from carveracontroller.desktop_clearance import ClearanceCandidates

    inspect = Mock()
    panel = ClearanceCandidates(inspect)
    panel.view.text = "Individual contacts"
    candidates = tuple((line, "holder" if line % 2 else "shank", f"jaw {line}") for line in range(1, 30))
    panel.set_candidates((*candidates, candidates[0]))
    assert len(panel.candidates) == 29  # Duplicate contacts do not obscure pagination.
    assert len(panel.rows.children) == 12
    assert panel.pages.parent is panel
    assert "1–12 of 29" in panel.status.text
    assert panel.previous.disabled and not panel.next.disabled
    panel.next.dispatch("on_release")
    assert "13–24 of 29" in panel.status.text
    panel.rows.children[-1].dispatch("on_release")
    inspect.assert_called_once_with(*candidates[12])
    panel.next.dispatch("on_release")
    assert "25–29 of 29" in panel.status.text
    assert len(panel.rows.children) == 5 and panel.next.disabled
    panel.query.text = "JAW 29"
    panel.filter()
    assert panel.matches == (candidates[-1],)
    assert panel.pages.parent is None
    assert panel.page == 0 and panel.previous.disabled and panel.next.disabled
    panel.rows.children[0].dispatch("on_release")
    assert inspect.call_args.args == candidates[-1]
    panel.component.text = "shank"
    panel.filter()
    assert not panel.matches and "No matching" in panel.status.text
    assert not panel.rows.children
    panel.query.text = ""
    panel.filter()
    assert len(panel.matches) == 14
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(title="Clearance candidate browser", content=scroll, size_hint=(None, None), size=(850, 1000))
    popup.open()
    try:
        pump_frames(5)
        assert panel.width > 700
        assert all(row.right <= panel.right for row in panel.rows.children)
        panel.export_to_png(str(tmp_path / "clearance-candidates.png"))
        assert (tmp_path / "clearance-candidates.png").exists()
    finally:
        popup.dismiss()
        scroll.remove_widget(panel)
    panel.set_candidates(())
    assert not panel.candidates and not panel.matches
    assert "clearance unknown" in panel.status.text
    assert panel.component.text == "All components"


def test_grouped_causes_expand_all_motions_search_and_wrap_at_narrow_width(kivy_app, tmp_path):
    from carveracontroller.addons.manufacturing_simulation.geometry import CollisionContact
    from carveracontroller.desktop_clearance import ClearanceCandidates
    from carveracontroller.desktop_components import Action, AdaptiveGrid

    inspect = Mock()
    panel = ClearanceCandidates(inspect)
    obstacle = "Long vise jaw name with a mounting identifier and an extended description"
    candidates = tuple((line, "holder", obstacle) for line in range(1, 30))
    contact = CollisionContact("holder", obstacle, (), AABB(Vec3(0, 0, 0), Vec3(1, 1, 1)), "swept bounds")
    panel.set_candidates(
        candidates,
        contacts=tuple((line, contact) for line in range(1, 30)),
        segments=tuple(SimpleNamespace(line=line, tool_id="1") for line in range(1, 30)),
        operations=(SimpleNamespace(id="rough", name="Roughing", start_line=1, end_line=40),),
    )
    assert len(panel.rows.children) == 1
    assert panel.pages.parent is None
    assert "1–1 of 1" in panel.status.text and "29 matching contacts" in panel.status.text
    panel.rows.children[0].dispatch("on_release")
    assert not inspect.called
    assert len([row for row in panel.rows.children if isinstance(row, Action) and row.text.startswith("Line")]) == 12
    for _ in range(2):
        navigation = panel.rows.children[0]
        next(action for action in navigation.children if action.text == "Next motions").dispatch("on_release")
    motion_rows = [
        row for row in reversed(panel.rows.children) if isinstance(row, Action) and row.text.startswith("Line")
    ]
    assert len(motion_rows) == 5
    motion_rows[-1].dispatch("on_release")
    inspect.assert_called_once_with(*candidates[-1])
    panel.query.text = "T1 Roughing line 29"
    panel.filter()
    assert panel.matches == candidates[-1:]
    assert panel.expanded_cause is None and panel.contact_page == 0
    panel.rows.children[0].dispatch("on_release")
    assert all(not isinstance(row, AdaptiveGrid) for row in panel.rows.children)
    assert "1 motion" in panel.rows.children[-1].text
    assert "line 29" in panel.rows.children[-1].text and "29–29" not in panel.rows.children[-1].text
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(title="Grouped clearance review", content=scroll, size_hint=(None, None), size=(460, 800))
    popup.open()
    try:
        pump_frames(8)
        actions = [row for row in panel.rows.children if isinstance(row, Action)]
        assert all(action.texture_size[0] <= action.width for action in actions)
        assert all(action.height >= action.texture_size[1] + 16 for action in actions)
        panel.export_to_png(str(tmp_path / "clearance-grouped-narrow.png"))
    finally:
        popup.dismiss()
        scroll.remove_widget(panel)
        panel._filter_trigger.cancel()
        pump_frames(3)
    panel.component.text = "shank"
    panel.filter()
    assert not panel.rows.children
    panel.set_candidates(())
    assert not panel.causes and not panel.filtered_causes and panel.expanded_cause is None


def test_partial_unknown_and_empty_coverage_are_explicit(kivy_app):
    panel = kivy_app.root.desktop_workspace.simulation_panel
    card = panel.clearance_card
    tool = ToolGeometry(2, 2, 2, 5)
    from carveracontroller.addons.manufacturing_simulation import SimulationSegment

    segment = SimulationSegment(Vec3(0, 0, 0), Vec3(1, 0, 0), "1", axis=Vec3(1, 0, 0))
    scene = CollisionScene((CollisionObstacle("jaw", AABB(Vec3(10, 10, 10), Vec3(11, 11, 11))),))
    card.set_report(analyze_clearance((segment,), {"1": tool}, scene))
    assert "2 orientation intervals unknown" in card.summary.text
    assert not card.plot.rendered
    card.set_report(analyze_clearance((segment,), {"1": tool}, scene, cancelled=lambda: True))
    assert "PARTIAL: cancelled" in card.summary.text
    card.set_report(analyze_clearance((segment,), {"1": tool}, CollisionScene()))
    assert "Clearance remains unknown" in card.details.text


def test_simulation_toolbar_scope_context_menu_and_responsive_controls(kivy_app, monkeypatch):
    from kivy.metrics import dp

    from carveracontroller.machine.move_inspection import MoveInspector

    ws = kivy_app.root.desktop_workspace
    panel, operations = ws.simulation_panel, ws.operation_panel
    program = ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\nG1 X10\n")
    monkeypatch.setattr(operations, "program", program)
    monkeypatch.setattr(operations, "inspector", MoveInspector(program))
    monkeypatch.setattr(operations, "selected_operation", None)
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel, "clearance_inputs", None)
    monkeypatch.setattr(panel, "clearance_stale", False)
    panel.scope.text = "Selected operation"
    panel.refresh_controls()
    assert panel.simulate_action.disabled
    assert "No operation selected" in panel.selection_note.text
    operations.inspect_line(5, seek=False)
    assert not panel.simulate_action.disabled
    assert operations.selected_operation.name in panel.selection_note.text
    start, review, send = Mock(), Mock(), Mock()
    monkeypatch.setattr(panel, "start", start)
    monkeypatch.setitem(panel.menu_actions, "Review change impact", review)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.simulate_action.dispatch("on_release")
    start.assert_called_once_with(True)
    panel.scope.text = "Whole program"
    panel.simulate_action.dispatch("on_release")
    assert start.call_args.args == (False,)
    panel.more.text = "Review change impact"
    review.assert_called_once_with()
    assert panel.more.text == "More actions…"
    panel.running = True
    panel.refresh_controls()
    assert panel.simulate_action.disabled and panel.more.disabled and panel.scope.disabled
    assert not panel.cancel_action.disabled
    panel.cancel_action.dispatch("on_release")
    assert panel.cancel_event.is_set()
    panel.cancel_event.clear()
    panel.more.text = "Review change impact"
    assert review.call_count == 1
    panel.running = False
    panel.refresh_controls()
    for width, columns in ((760, 4), (250, 2), (110, 1)):
        panel.content.width = dp(width)
        pump_frames(2)
        assert panel.toolbar.cols == columns
        assert all(control.width > 0 for control in panel.toolbar.children)
        assert all(control.right <= panel.toolbar.right + dp(1) for control in panel.toolbar.children)
    send.assert_not_called()
