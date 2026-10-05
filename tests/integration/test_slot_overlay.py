from types import SimpleNamespace

from kivy.graphics import RenderContext

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from carveracontroller.desktop_slot_overlay import SlotOverlay
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
    )
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
