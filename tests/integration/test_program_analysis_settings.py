import math
from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_program_analysis import CubicReview
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames

SOURCE = "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Cubic)\nG5 I0 J3 P0 Q-3 X1 Y1 F100\n"


def loaded(panel):
    for _ in range(200):
        pump_frames(1, sleep=0.005)
        if panel.program is not None:
            return panel.program
    raise AssertionError(panel.note.text)


def test_actual_analysis_controls_reparse_preserve_bytes_and_do_not_seek_machine(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    path = tmp_path / "cubic.nc"
    path.write_text(SOURCE)
    original_bytes = path.read_bytes()
    send, seek, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    monkeypatch.setattr(ws, "enter_preview", preview)
    panel.load(str(path))
    assert loaded(panel).dialect == "carvera"
    assert 4 in panel.program.unresolved_motion_lines
    panel.analysis_settings_action.dispatch("on_release")
    settings = panel.analysis_settings
    assert settings.parent is panel
    settings.dialect.text = "LinuxCNC · spline study"
    settings.tolerance.text = "0.001"
    settings.budget.text = "1000"
    settings.apply_action.dispatch("on_release")
    program = loaded(panel)
    assert program.dialect == "linuxcnc" and program.spline_block(4).tolerance_mm == 0.001
    panel.inspect_line(4, seek=True)
    pump_frames(8)
    assert panel.cubic_review.parent is panel.inspection
    assert panel.cubic_review.points == program.spline_points(4)
    assert "backend unqualified" in panel.note.text
    assert "Position error bound" in panel.cubic_review.note.text
    assert program.file_hash in panel.cubic_review.note.text
    assert "own geometry review" in panel.path_highlight_note.text
    seek.assert_not_called()
    preview.assert_not_called()
    send.assert_not_called()
    assert path.read_bytes() == original_bytes
    # Draft errors preserve the applied settings and current immutable analysis.
    settings.tolerance.text = "nan"
    settings.apply_action.dispatch("on_release")
    assert panel.program is program and settings.applied == ("linuxcnc", 0.001, 1000)
    assert "Draft not applied" in settings.status.text
    settings.dialect.text = "Carvera"
    settings.apply_action.dispatch("on_release")
    assert loaded(panel).dialect == "carvera"
    assert not panel.program.spline_blocks and panel.cubic_review.parent is None
    panel.analysis_settings_action.dispatch("on_release")
    panel.load(None)
    assert settings.apply_action.disabled and settings.applied == ("carvera", 0.01, 10000)


@pytest.mark.parametrize("tolerance,budget", [("0", "10"), ("1", "100001"), ("1", "2.5")])
def test_invalid_analysis_drafts_keep_current_program(kivy_app, tmp_path, tolerance, budget):
    panel = kivy_app.root.desktop_workspace.operation_panel
    path = tmp_path / "invalid-draft.nc"
    path.write_text(SOURCE)
    panel.load(str(path))
    program = loaded(panel)
    settings = panel.analysis_settings
    settings.dialect.text = "LinuxCNC · spline study"
    settings.tolerance.text, settings.budget.text = tolerance, budget
    settings.apply_action.dispatch("on_release")
    assert panel.program is program and settings.applied == ("carvera", 0.01, 10000)
    assert "Draft not applied" in settings.status.text
    panel.load(None)


def test_curve_review_pages_exact_contiguous_samples_and_keeps_equal_projection_scale(kivy_app, tmp_path):
    source = SOURCE.replace("J3 P0 Q-3 X1 Y1", "J1000 P0 Q-1000 X1000 Y1")
    program = ProgramOperations.from_text(source, dialect="linuxcnc", spline_tolerance_mm=0.0001)
    block = program.spline_block(4)
    assert block.segments > CubicReview.PAGE_SEGMENTS
    view = CubicReview()
    view.size_hint = (None, None)
    view.size = dp(500), dp(600)
    Window.add_widget(view)
    try:
        assert view.show(program, 4)
        assert view.curve_actions.parent is view and view.data_actions.parent is None
        pump_frames(8)
        assert len(view.plot.points) == 257 and view.plot.points == program.spline_points(4)[:257]
        assert len(view.overview) <= 1025
        assert view.overview[0] == view.points[0] and view.overview[-1] == view.points[-1]
        view.export_to_png(str(tmp_path / "cubic-review.png"))
        first_end = view.plot.points[-1]
        view.next.dispatch("on_release")
        assert view.plot.points[0] == first_end
        assert "Segments 257–512" in view.note.text
        point_a, point_b = view.plot.points[0], view.plot.points[-1]
        screen_a, screen_b = view.plot.screen_points[0], view.plot.screen_points[-1]
        assert math.dist(screen_a, screen_b) / math.dist(point_a[:2], point_b[:2]) > 0
        for a, b in zip(view.plot.points, view.plot.screen_points):
            for c, d in zip(view.plot.points, view.plot.screen_points):
                if a[0] != c[0] and a[1] != c[1]:
                    assert (b[0] - d[0]) / (a[0] - c[0]) == pytest.approx((b[1] - d[1]) / (a[1] - c[1]))
                    break
            else:
                continue
            break
        view.previous.dispatch("on_release")
        assert view.page == 0 and view.previous.disabled
        assert not view.show(program, 2) and not view.points and not view.plot.points
    finally:
        Window.remove_widget(view)


def test_quadratic_review_retains_original_polygon_and_source_identity(kivy_app):
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nG0 X-2 Y4 Z0\n(Operation: Quadratic)\nG5.1 X2 I2 J-8 F100",
        dialect="linuxcnc",
    )
    view = CubicReview()
    assert view.show(program, 4)
    assert view.curve_actions.parent is None and view.data_actions.parent is None
    assert view.title.text == "Bounded G5.1 · work-frame XY"
    assert view.plot.controls == program.spline_block(4).original_control_points_mm
    assert len(view.plot.controls) == 3
    assert "G5.1 source line 4" in view.note.text
    assert "Control 3" in view.note.text and "Control 4" not in view.note.text
    assert view.points == program.spline_points(4)


@pytest.mark.parametrize(
    "plane,words,axes,projection",
    [("G17", "X1 Y2", (0, 1), "XY"), ("G18", "X1 Z2", (0, 2), "XZ"), ("G19", "Y1 Z2", (1, 2), "YZ")],
)
def test_nurbs_review_selects_entire_source_span_and_projects_active_plane(kivy_app, plane, words, axes, projection):
    source = f"G21 G90 {plane} G94 G54\nG0 X0 Y0 Z0\nG5.2 P2 F100\n{words} P1\n{words} P3\nG5.3"
    program = ProgramOperations.from_text(source, dialect="linuxcnc")
    view = CubicReview()
    view.size_hint = (None, None)
    view.size = dp(500), dp(600)
    Window.add_widget(view)
    try:
        assert view.show(program, 4)
        pump_frames(5)
        block = program.spline_block(6)
        assert view.block is block and view.points == program.spline_points(3)
        assert view.plot.axes == axes and projection in view.title.text
        assert "source lines 3–6" in view.note.text
        assert "weight 2" in view.note.text and "implicit pre-block position" in view.note.text
        assert block.data.source_sha256 in view.note.text
        assert block.data.interpreter_revision in view.note.text
        assert "Knot 6:" in view.note.text
        assert math.dist(view.plot.screen_points[0], view.plot.screen_points[-1]) > 0
    finally:
        Window.remove_widget(view)


def test_nurbs_control_data_is_paged_without_truncating_original_geometry(kivy_app):
    source = (
        "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\nG5.2 P1 F100\n" + "\n".join(f"X{i} Y{i} P1" for i in range(1, 33)) + "\nG5.3"
    )
    program = ProgramOperations.from_text(source, dialect="linuxcnc")
    view = CubicReview()
    assert view.show(program, 20)
    controls = view.plot.controls
    assert len(controls) == 33 and "Control 17:" not in view.note.text
    assert not view.next_data.disabled
    view.next_data.dispatch("on_release")
    assert "Control 17:" in view.note.text and "Control 1:" not in view.note.text
    assert view.plot.controls is controls
    view.next_data.dispatch("on_release")
    assert "Control 33:" in view.note.text and "Knot 36:" in view.note.text
    assert view.next_data.disabled
    view.previous_data.dispatch("on_release")
    assert view.data_page == 1
    assert view.data_actions.parent is view
    assert not view.show(None, 1)
    assert view.curve_actions.parent is None and view.data_actions.parent is None
    assert view.show(program, 20)
    assert view.data_actions.parent is view and view.data_page == 0
    assert "Control 1:" in view.note.text


def test_actual_nurbs_panel_inspection_never_seeks_the_legacy_toolpath_or_sends(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    source = "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\nG5.2 P1 F100\nX1 Y2 P1\nX3 Y0 P2\nG5.3"
    path = tmp_path / "nurbs-study.nc"
    path.write_text(source)
    send, seek = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    panel.load(str(path), analysis_settings=("linuxcnc", 0.001, 1000))
    program = loaded(panel)
    panel.inspect_line(4, seek=True)
    pump_frames(5)
    assert panel.cubic_review.parent is panel.inspection
    assert panel.cubic_review.points == program.spline_points(6)
    assert "source lines 3–6" in panel.cubic_review.note.text
    send.assert_not_called()
    seek.assert_not_called()
    assert path.read_text() == source
    panel.load(None)


def test_section_framing_enlarges_exact_page_and_preserves_source_geometry(kivy_app, tmp_path):
    source = SOURCE.replace("J3 P0 Q-3 X1 Y1", "J1000 P0 Q-1000 X1000 Y1")
    program = ProgramOperations.from_text(source, dialect="linuxcnc", spline_tolerance_mm=0.0001)
    view = CubicReview()
    view.size_hint = (None, None)
    view.size = dp(600), dp(850)
    Window.add_widget(view)
    try:
        assert view.show(program, 4)
        pump_frames(5)
        controls, points, identity = view.plot.controls, view.points, view.identity
        whole_width = max(p[0] for p in view.plot.screen_points) - min(p[0] for p in view.plot.screen_points)
        view.framing.text = "Fit current section"
        pump_frames(5)
        section_width = max(p[0] for p in view.plot.screen_points) - min(p[0] for p in view.plot.screen_points)
        assert section_width > whole_width * 2
        for x, y in view.plot.screen_points:
            assert view.plot.x <= x <= view.plot.right
            assert view.plot.y <= y <= view.plot.top
        assert "outside context clipped" in view.note.text
        view.control_visibility.text = "Hide control polygon"
        assert not view.plot.show_controls and "original data retained" in view.note.text
        pump_frames(5)
        view.export_to_png(str(tmp_path / "section-review.png"))
        view.next.dispatch("on_release")
        assert view.plot.points == points[256:513]
        assert view.plot.controls is controls and view.points is points and view.identity == identity
        view.framing.text = "Fit whole spline"
        assert not view.plot.fit_section
        assert view.show(None, 1) is False
        assert view.framing.disabled and view.control_visibility.disabled
        assert view.show(program, 4)
        assert not view.framing.disabled and not view.control_visibility.disabled
        assert view.page == 0 and view.plot.controls == controls
    finally:
        Window.remove_widget(view)
