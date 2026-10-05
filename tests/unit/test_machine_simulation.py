"""Coordinate-frame and mesh contracts for schematic machine playback."""

import math

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup, box_wireframe, build_scene


def test_stock_wireframe_retains_all_twelve_volume_edges():
    low, high = (-118.6, -94.7, -0.36), (8.4, -25.3, 50.51)
    edges = box_wireframe(low, high)
    assert len(edges.indices) == 24
    pairs = []
    for index in range(0, len(edges.vertices), 20):
        a, b = tuple(edges.vertices[index : index + 3]), tuple(edges.vertices[index + 10 : index + 13])
        assert sum(x != y for x, y in zip(a, b)) == 1
        assert all(value in (low[axis], high[axis]) for axis, value in enumerate(a))
        assert all(value in (low[axis], high[axis]) for axis, value in enumerate(b))
        pairs.append((a, b))
    assert len(set(pairs)) == 12
    with pytest.raises(ValueError):
        box_wireframe(low, low)


def test_work_machine_round_trip_for_nonzero_work_offset():
    setup = MachineSetup(work_offset_mm=(-232, -195.285, -86.4), alignment_confirmed=True)
    point = (23, 15, -4)
    assert setup.machine_point(point) == pytest.approx((-209, -180.285, -90.4))
    assert setup.work_point(setup.machine_point(point)) == pytest.approx(point)


@pytest.mark.parametrize("work_point", [(0, 0, 0), (34, 27, -12), (-90, -45, 24)])
def test_tool_stock_relative_motion_is_preserved_with_moving_y_table(work_point):
    setup = MachineSetup()
    pose = setup.pose(work_point)
    # Any stock point is translated with the table. Relative tooltip-stock
    # vector must remain precisely the program-space vector on all axes.
    stock_point = (5, 8, -15)
    stock_machine = setup.machine_point(stock_point)
    translated_stock = tuple(stock_machine[i] + pose["table"][i] for i in range(3))
    relative = tuple(pose["tool_machine_mm"][i] - translated_stock[i] for i in range(3))
    assert relative == pytest.approx(tuple(work_point[i] - stock_point[i] for i in range(3)))
    assert pose["tool_machine_mm"][1] == -120


def test_x_and_z_slide_independently_and_y_table_moves_opposite_program():
    setup = MachineSetup()
    pose = setup.pose((50, 30, -10))
    assert pose["carriage"] == (50, 0, 0)
    assert pose["spindle"] == (50, 0, -10)
    assert pose["table"] == (0, -30, 0)


@pytest.mark.parametrize(
    "point,in_range",
    [
        ((-180, -120, -30), True),
        ((180, 120, 110), True),
        ((181, 0, 0), False),
        ((0, -121, 0), False),
        ((0, 0, -31), False),
    ],
)
def test_nominal_travel_boundary(point, in_range):
    assert MachineSetup().pose(point)["in_nominal_travel"] is in_range


def test_stock_is_explicit_and_uses_lower_corner_in_program_coordinates():
    assert not build_scene(MachineSetup())["stock"].indices
    setup = MachineSetup(stock_size_mm=(127, 69.4182, 50.8762), stock_origin_mm=(-63.5, -34.7091, -50.8762))
    mesh = build_scene(setup)["stock"]
    coordinates = [mesh.vertices[i : i + 3] for i in range(0, len(mesh.vertices), 10)]
    assert min(p[0] for p in coordinates) == pytest.approx(-243.5)
    assert max(p[0] for p in coordinates) == pytest.approx(-116.5)
    assert max(p[2] for p in coordinates) == pytest.approx(-110)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"work_offset_mm": (1, 2)},
        {"work_offset_mm": (0, float("nan"), 0)},
        {"stock_size_mm": (10, 20, 0)},
        {"stock_origin_mm": (0, 0, float("inf"))},
    ],
)
def test_invalid_frames_and_stock_rejected(kwargs):
    with pytest.raises(ValueError):
        MachineSetup(**kwargs)


def test_component_meshes_are_finite_and_fit_unsigned_short_index_limit():
    for mesh in build_scene(MachineSetup(stock_size_mm=(100, 50, 20))).values():
        assert all(math.isfinite(value) for value in mesh.vertices)
        assert len(mesh.vertices) % 10 == 0
        assert len(mesh.indices) % 3 == 0
        assert max(mesh.indices) < len(mesh.vertices) // 10 < 65536
        for i in range(0, len(mesh.vertices), 10):
            assert sum(v * v for v in mesh.vertices[i + 3 : i + 6]) == pytest.approx(1)


def test_viewer_rehearsal_interpolates_xyz_despite_legacy_rotary_flag():
    from kivy.clock import Clock

    from carveracontroller.GcodeViewer import GCodeViewer

    viewer = GCodeViewer()
    try:
        viewer.machine_profile = None  # deterministic schematic fallback contract
        viewer.high_precision_time_estimate = False
        viewer.configure_machine((-180, -120, -100), (100, 60, 40), (-50, -30, -40))
        viewer.load_array(
            [
                [0, 0, 10, 0, 1, 1, 1, 600],
                [30, 20, -5, 0, 1, 2, 1, 600],
                [50, -15, -8, 0, 1, 3, 1, 600],
            ]
        )
        assert viewer.set_machine_visible(True)
        viewer.show_all()
        viewer._on_frame_tick(0)
        assert viewer._machine_pose["carriage"] == pytest.approx((50, 0, 0))
        assert viewer._machine_pose["table"] == pytest.approx((0, 15, 0))
        assert viewer._machine_pose["tool_machine_mm"] == pytest.approx((-130, -120, -108))
        assert viewer.get_machine_simulation_info()["alignment_configured"]
        # Scaling may be enormous for a tiny program, but far clipping still
        # encloses the machine because camera distance is fitted separately.
        assert viewer.m_distance >= 650 * viewer.move_scale_by_positon * 3
        viewer.set_machine_visible(False)
        assert viewer.m_distance == 10
        assert viewer.set_machine_visible(True)
        viewer.load_array([[0, 0, 0, 0, 1, 1, 1, 600], [20, 0, 0, 90, 1, 2, 1, 600]])
        assert not viewer.machine_visible
        assert not viewer.set_machine_visible(True)
    finally:
        Clock.unschedule(viewer._on_frame_tick)


@pytest.mark.parametrize("angle", [90, 37, -125])
def test_declared_rotated_stock_mesh_matches_removal_frame(angle):
    from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3

    setup = MachineSetup(stock_origin_mm=(2, -1, 0), stock_size_mm=(10, 4, 4), stock_rotation_deg=angle)
    stock = StockVolume(AABB(Vec3(2, -1, 0), Vec3(12, 3, 4)), rotation_deg=angle)
    for point in ((2, -1, 0), (12, 3, 4), (6, 1, 2)):
        assert setup.stock_point(point) == pytest.approx(stock.program_point(Vec3(*point)).tuple)
    for mesh in (setup.stock_mesh(), setup.stock_mesh(wireframe=True)):
        for i in range(0, len(mesh.vertices), 10):
            program = setup.work_point(mesh.vertices[i : i + 3])
            inverse = StockVolume(stock.grid_bounds, rotation_deg=-angle).program_point(Vec3(*program))
            assert all(
                value == pytest.approx(lo) or value == pytest.approx(hi)
                for value, lo, hi in zip(
                    inverse.tuple, stock.grid_bounds.minimum.tuple, stock.grid_bounds.maximum.tuple
                )
            )
            assert sum(v * v for v in mesh.vertices[i + 3 : i + 6]) == pytest.approx(1)
    assert setup.work_point(setup.machine_point((7, 3, -2))) == pytest.approx((7, 3, -2))


@pytest.mark.parametrize("angle", [True, float("inf"), float("nan"), "90"])
def test_declared_stock_rejects_invalid_rotation(angle):
    with pytest.raises(ValueError, match="rotation"):
        MachineSetup(stock_rotation_deg=angle)
