from types import SimpleNamespace

import pytest

from carveracontroller.desktop_declared_path import DeclaredPathPanel
from tests.unit.test_joint_motion_study import read, record


def test_declared_work_world_geometry_and_signed_axis_demand_are_linked(tmp_path):
    review = read(tmp_path)
    panel = DeclaredPathPanel()
    panel.show(review, ("p", 2))
    assert len(panel.plot.coordinates) == 91
    assert "unknown at initial pose" in panel.note.text
    panel.select(90)
    assert panel.plot.coordinates[-1] == pytest.approx((0, -100))
    assert "declared t 30 s" in panel.note.text
    assert "table: 90 deg · preceding interval velocity 3 deg/s" in panel.note.text
    panel.frame.text = "World frame"
    assert all(point == (100, 0) for point in panel.plot.coordinates)
    panel.plane.text = "XZ"
    assert all(point == (100, -10) for point in panel.plot.coordinates)
    assert panel.cursor == 90 and panel.identity == ("p", 2)
    panel.show(review, ("p", 2))
    assert panel.cursor == 90
    panel.show(review, ("p", 3))
    assert panel.cursor == 0
    panel.show(None, None)
    assert not panel.plot.coordinates and panel.next.disabled


def test_equal_scale_pick_wheel_passthrough_and_complete_paging(tmp_path):
    data = record()
    data["samples"][1]["positions"]["table"] = 500
    review = read(tmp_path, data)
    panel = DeclaredPathPanel()
    panel.show(review, ("p", 2))
    assert len(panel.plot.coordinates) == 200
    panel.select(400)
    assert len(panel.plot.coordinates) == 101
    panel.plot.pos = (0, 0)
    panel.plot.size = (400, 200)
    x, y = panel.plot.screen_points[-1]
    assert panel.plot.on_touch_down(SimpleNamespace(pos=(x, y), button="left"))
    assert panel.cursor == 500
    assert "displayed 401–501" in panel.note.text
    for button in ("scrolldown", "scrollup", "right"):
        assert not panel.plot.on_touch_down(SimpleNamespace(pos=(x, y), button=button))
        assert panel.cursor == 500
    panel.select(-1)
    assert panel.cursor == 0
    panel.select(99999)
    assert panel.cursor == 500


def test_large_path_projection_reads_only_visible_page_and_selected_pose(tmp_path):
    from dataclasses import replace

    class PagedPoints:
        def __init__(self, point):
            self.point = point
            self.reads = 0

        def __len__(self):
            return 50000

        def __getitem__(self, index):
            if isinstance(index, slice):
                indices = range(*index.indices(len(self)))
                self.reads += len(indices)
                assert len(indices) <= 200
                return tuple(self.point for _ in indices)
            if not 0 <= index < len(self):
                raise IndexError(index)
            self.reads += 1
            assert self.reads <= 1000, "A page change walked the entire declared path"
            return self.point

    review = read(tmp_path)
    points = PagedPoints(review.path_points[0])
    panel = DeclaredPathPanel()
    panel.show(replace(review, path_points=points), ("large", 2))
    for cursor in (24999, 49999, 0):
        points.reads = 0
        panel.select(cursor)
        assert points.reads <= 201
        assert panel.cursor == cursor
        assert len(panel.plot.coordinates) == 200
        assert f"Pose {cursor + 1} of 50000" in panel.note.text
    points.reads = 0
    panel.frame.text = "World frame"
    assert points.reads <= 201
    assert all(point == (100, 0) for point in panel.plot.coordinates)


@pytest.mark.parametrize("width", [360, 650])
def test_path_inspector_responsive_layout_and_projection_shape(width, tmp_path):
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    from tests.integration.conftest import pump_frames

    panel = DeclaredPathPanel()
    panel.show(read(tmp_path), ("p", 2))
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(content=scroll, size_hint=(None, None), size=(width, 650))
    popup.open(animation=False)
    try:
        pump_frames(6)
        assert panel.plot.width <= scroll.width
        assert panel.note.texture_size[1] <= panel.note.height
        assert panel.joint.right <= panel.right
        start, corner, end = (panel.plot.screen_points[i] for i in (0, 45, 90))
        # A quarter-circle's midpoint and endpoints remain on one radius.
        cx, cy = end[0], start[1]
        radii = [((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in (start, corner, end)]
        assert radii == pytest.approx([radii[0]] * 3)
        scroll.export_to_png(str(tmp_path / f"declared-path-{width}.png"))
    finally:
        popup.dismiss(animation=False)
