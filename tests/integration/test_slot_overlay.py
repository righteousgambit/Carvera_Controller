from types import SimpleNamespace

from kivy.graphics import RenderContext

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.desktop_slot_overlay import SlotOverlay
from carveracontroller.GcodeViewer import GCodeViewer
from tests.unit.test_machine_profile import profile_data


def test_targets_follow_table_and_visibility_without_changing_tool_geometry():
    rows = [(0, (-100, -40, -50)), (6, (-100, -10, -50))]
    panel = SimpleNamespace(overlay_rows=lambda: rows)
    viewer = SimpleNamespace(
        machine_profile=MachineProfile(profile_data()),
        machine_visible=True,
        machine_group_visibility={"atc": True},
        disabled=False,
        _machine_pose={"table": (0, 30, 0)},
        explosion_mm=0,
        pose_mode="Preview",
    )
    viewer.explosion_offset = GCodeViewer.explosion_offset.__get__(viewer)
    viewer.machine_display_movement = GCodeViewer.machine_display_movement.__get__(viewer)
    projected = []

    def project(point):
        projected.append(point)
        return point[0] + 200, point[1] + 100, 0.5

    interaction = SimpleNamespace(
        overlay=RenderContext(),
        workspace=SimpleNamespace(slot_inventory_panel=panel),
        viewer=viewer,
        project=project,
        viewport=lambda: (0, 0, 300, 200),
    )
    overlay = SlotOverlay(interaction)
    overlay.refresh()
    assert projected == [(-100, -10, -50), (-100, 20, -50)]
    assert [marker[3] for marker in overlay.markers[:2]] == [0, 6]
    assert all(marker[0].a == 1 for marker in overlay.markers[:2])
    first_texture = overlay.markers[0][2].texture
    viewer._machine_pose["table"] = (0, 40, 0)
    overlay.refresh()
    assert projected[-2:] == [(-100, 0, -50), (-100, 30, -50)]
    assert overlay.markers[0][2].texture is first_texture
    viewer.explosion_mm = 25
    offset = viewer.explosion_offset("atc")
    overlay.refresh()
    assert projected[-2:] == [
        tuple(point[i] + offset[i] for i in range(3))
        for point in ((-100, 0, -50), (-100, 30, -50))
    ]
    viewer.pose_mode = "Live"
    overlay.refresh()
    assert projected[-2:] == [(-100, 0, -50), (-100, 30, -50)]
    viewer.explosion_mm = 0
    viewer.recorded_machine_point = (0, 0, 0)
    overlay.refresh()
    assert all(marker[0].a == 0 for marker in overlay.markers)
    viewer.recorded_machine_point = None
    viewer.machine_group_visibility["atc"] = False
    overlay.refresh()
    assert all(marker[0].a == 0 for marker in overlay.markers)
    viewer.machine_group_visibility["atc"] = True
    rows.clear()
    overlay.refresh()
    assert all(marker[0].a == 0 for marker in overlay.markers)
    rows.append((1, (-1000, -40, -50)))
    overlay.refresh()
    assert all(marker[0].a == 0 for marker in overlay.markers)

    def unprojectable(_point):
        raise OverflowError("outside GL numeric range")

    interaction.project = unprojectable
    overlay.refresh()
    assert all(marker[0].a == 0 for marker in overlay.markers)


def test_crowded_captions_are_inside_viewport_and_never_overlap():
    from carveracontroller.desktop_slot_overlay import label_positions

    def overlaps(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    for viewport in ((0, 0, 300, 200), (40, 70, 220, 60)):
        ox, oy, width, height = viewport
        for x, y in ((ox + 2, oy + 2), (ox + width - 2, oy + height - 2), (ox + width / 2, oy + height / 2)):
            items = [(index, (x, y + index * 0.1), (28, 16)) for index in range(6)]
            positions = label_positions(items, viewport, gap=4, inset=4)
            rectangles = []
            for index, _anchor, size in items:
                px, py = positions[index]
                assert ox <= px <= ox + width - size[0]
                assert oy <= py <= oy + height - size[1]
                rectangles.append((px, py, *size))
            for index, rectangle in enumerate(rectangles):
                assert not any(overlaps(rectangle, other) for other in rectangles[index + 1 :])
            assert label_positions(items, viewport, gap=4, inset=4) == positions
    assert label_positions([], (0, 0, 300, 200), gap=4, inset=4) == {}


def test_crowded_overlay_preserves_targets_and_updates_leaders():
    rows = [(number, (-100, -40 + number, -50)) for number in range(6)]
    viewer = SimpleNamespace(
        machine_profile=MachineProfile(profile_data()),
        machine_visible=True,
        machine_group_visibility={"atc": True},
        disabled=False,
        _machine_pose={"table": (0, 30, 0)},
        explosion_mm=0,
        pose_mode="Preview",
    )
    viewer.explosion_offset = GCodeViewer.explosion_offset.__get__(viewer)
    viewer.machine_display_movement = GCodeViewer.machine_display_movement.__get__(viewer)
    interaction = SimpleNamespace(
        overlay=RenderContext(),
        workspace=SimpleNamespace(slot_inventory_panel=SimpleNamespace(overlay_rows=lambda: rows)),
        viewer=viewer,
        project=lambda point: (100, 100 + point[1] / 10, 0.5),
        viewport=lambda: (0, 0, 300, 200),
    )
    overlay = SlotOverlay(interaction)
    overlay.refresh()
    captions = []
    for number, marker in enumerate(overlay.markers):
        color, ring, text, identifier, leader = marker
        assert color.a == 1 and identifier == number
        assert tuple(leader.points[:2]) == (100, 99 + number / 10)
        assert leader.points[-1] == text.pos[1] + text.size[1] / 2
        captions.append((*text.pos, *text.size))
    for index, (x, y, width, height) in enumerate(captions):
        for bx, by, bw, bh in captions[index + 1 :]:
            assert x + width <= bx or bx + bw <= x or y + height <= by or by + bh <= y
    rows[:] = [(6, (-100, -10, -50))]
    overlay.refresh()
    assert overlay.markers[0][3] == 6
    assert overlay.markers[0][0].a == 1
    assert all(marker[0].a == 0 for marker in overlay.markers[1:])
