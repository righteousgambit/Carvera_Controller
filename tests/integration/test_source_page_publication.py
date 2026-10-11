"""The real source browser publishes a complete page without per-row refreshes."""

import time
from unittest.mock import Mock

import pytest

from carveracontroller import main
from carveracontroller.CNC import escape_gcode_markup, highlight_gcode_line
from tests.integration.conftest import pump_frames


@pytest.fixture
def source_page(kivy_app, monkeypatch):
    root = kivy_app.root
    app = kivy_app
    saved = (root.lines, list(root.gcode_rv.data), root.gcode_rv.data_length, app.curr_page, app.total_pages)
    monkeypatch.setattr(main, "MAX_LOAD_LINES", 10000)
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    yield app, root, send
    root.lines, rows, root.gcode_rv.data_length, app.curr_page, app.total_pages = saved
    root.gcode_rv.data = rows
    pump_frames(2)


def test_ten_thousand_source_rows_publish_once_with_exact_highlighting(source_page, monkeypatch):
    app, root, send = source_page
    root.lines = [f" G1 X{index} (source [sample])\r\n" for index in range(10003)]
    app.total_pages = 2
    monkeypatch.setattr(root, "gcode_highlight_enabled", True)
    monkeypatch.setattr(root, "gcode_highlight_colors", None)
    notifications = []
    callback = lambda _view, data: notifications.append(len(data))
    root.gcode_rv.bind(data=callback)
    try:
        started = time.monotonic()
        root.load_page(1)
        print(f"SOURCE_PAGE_SECONDS={time.monotonic() - started:.6f}; DATA_NOTIFICATIONS={len(notifications)}")
    finally:
        root.gcode_rv.unbind(data=callback)
    started = time.monotonic()
    pump_frames(1)
    print(f"SOURCE_PAGE_FRAME_SECONDS={time.monotonic() - started:.6f}")
    assert notifications == [10000]
    assert root.gcode_rv.data_length == 10000 and app.curr_page == 1 and not app.loading_page
    for index in (0, 4999, 9999):
        plain = root.lines[index].strip()
        row = root.gcode_rv.data[index]
        assert row == {
            "line_no": index + 1,
            "text": plain,
            "highlighted_text": highlight_gcode_line(plain, None),
            "color": (200 / 255, 200 / 255, 200 / 255, 1),
        }
    pump_frames(2)
    send.assert_not_called()


def test_page_navigation_replaces_rows_and_retains_source_numbers(source_page, monkeypatch):
    app, root, send = source_page
    root.lines = [f"G1 X{index} [plain]\n" for index in range(10003)]
    app.total_pages = 2
    monkeypatch.setattr(root, "gcode_highlight_enabled", False)
    root.load_page(9999)
    assert app.curr_page == 2 and root.gcode_rv.data_length == 3
    assert [row["line_no"] for row in root.gcode_rv.data] == [10001, 10002, 10003]
    assert root.gcode_rv.data[-1]["highlighted_text"] == escape_gcode_markup(root.lines[-1].strip())
    root.load_page(0)
    assert app.curr_page == 2 and len(root.gcode_rv.data) == 3
    root.load_page(-1)
    assert app.curr_page == 1 and len(root.gcode_rv.data) == 10000
    root.load_page(-1)
    assert app.curr_page == 1 and len(root.gcode_rv.data) == 10000
    send.assert_not_called()


def test_large_linear_preview_keeps_full_source_and_exact_line_seek(source_page, tmp_path):
    from math import hypot

    from tests.integration.conftest import load_gcode_file

    app, root, send = source_page
    path = tmp_path / "synthetic-large.nc"
    path.write_text(
        "(SYNTHETIC LOCAL PREVIEW ONLY)\nG21 G90 G17 G94\nT1 M6\nG0 X-115 Y-90 Z51\nG1 Z50.3 F100\n"
        + "".join(f"G1 X{5 if i % 2 else -115} Y{-90 + i % 61}\n" for i in range(20000))
        + "G0 Z55\nM5\nM30\n"
    )
    previous_filename = app.selected_local_filename
    app.selected_local_filename = str(path)
    try:
        started = time.monotonic()
        load_gcode_file(app, str(path))
        print(f"LARGE_LINEAR_PREVIEW_SECONDS={time.monotonic() - started:.6f}")
        viewer = root.gcode_viewer
        assert root.selected_file_line_count == 20008
        assert len(viewer.raw_linenumbers) == len(viewer.lengths) == 40003
        assert root.gcode_rv.data_length == 10000
        rows = [index for index, number in enumerate(viewer.raw_linenumbers) if number == 7]
        assert len(rows) == 2
        assert [viewer.raw_positions[index * 3 : index * 3 + 3] for index in rows] == [
            [-115.0, -90.0, 50.3],
            [5.0, -89.0, 50.3],
        ]
        start = viewer.get_distance_by_lineidx(7, 0.0)
        end = viewer.get_distance_by_lineidx(7, 1.0)
        assert end - start == pytest.approx(hypot(120, 1) * viewer.move_scale_by_positon)
        assert viewer.get_distance_by_lineidx(7, 0.5) == pytest.approx((start + end) / 2)
        root.load_page(9999)
        assert root.gcode_rv.data_length == 8 and root.gcode_rv.data[-1]["line_no"] == 20008
        send.assert_not_called()
    finally:
        root.desktop_workspace.close_local_preview()
        app.selected_local_filename = previous_filename
