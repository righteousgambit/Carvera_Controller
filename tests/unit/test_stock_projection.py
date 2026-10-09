"""Source projections retain concavity, source units and declared frames."""

import math
from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.addons.machine_simulation.stock_projection import project_stock
from tests.unit.test_stock_solid import l_stock, mesh


def points(view):
    return {tuple(vertices[i : i + 2]) for vertices, _indices in view.batches for i in range(0, len(vertices), 4)}


@pytest.mark.parametrize("frame", ["stock", "program", "machine", "rotation"])
def test_source_edges_project_concavity_and_independent_transform(tmp_path, frame):
    # A nonzero source-local minimum must not become an unintended translation.
    triangles = tuple(tuple((x + 11, y - 7, z + 2) for x, y, z in tri) for tri in l_stock())
    source = StockModel.load(mesh(tmp_path, triangles).source_path, "mm")
    setup = MachineSetup((10, 20, 30), source.size_mm, (4, 5, 6), False, 37, source)
    drawing = project_stock(source, setup.record(), frame)
    angle = math.radians(37 if frame in ("machine", "rotation") else 0)
    c, s = math.cos(angle), math.sin(angle)
    shift = (4, 5, 6) if frame in ("machine", "program") else (0, 0, 0)
    offset = (10, 20, 30) if frame == "machine" else (0, 0, 0)

    def expected(p):
        x, y, z = p
        return (
            offset[0] + shift[0] + 1.5 + c * (x - 1.5) - s * (y - 1.5),
            offset[1] + shift[1] + 1.5 + s * (x - 1.5) + c * (y - 1.5),
            offset[2] + shift[2] + z,
        )

    vertices = {expected(p) for triangle in l_stock() for p in triangle}
    for view, vertical in zip(drawing.views, (1, 2)):
        actual = points(view)
        wanted = {(p[0], p[vertical]) for p in vertices}
        assert len(actual) == len(wanted)
        for point in wanted:
            assert any(all(abs(a - b) < 1e-10 for a, b in zip(point, p)) for p in actual)
        assert view.minimum == pytest.approx((min(p[0] for p in vertices), min(p[vertical] for p in vertices)))
        assert view.maximum == pytest.approx((max(p[0] for p in vertices), max(p[vertical] for p in vertices)))
        assert all(len(indices) % 2 == 0 and max(indices) < 65535 for _vertices, indices in view.batches)
    # The absent upper-right corner of this L is never invented as a box edge.
    empty = expected((3, 3, 0))[:2]
    assert not any(all(abs(a - b) < 1e-10 for a, b in zip(empty, p)) for p in points(drawing.views[0]))


def test_source_units_and_previous_setup_are_independent(tmp_path):
    path = mesh(tmp_path, l_stock()).source_path
    mm, inch = StockModel.load(path, "mm"), StockModel.load(path, "inch")
    record = MachineSetup(stock_size_mm=mm.size_mm, stock_model=mm).record()
    before = project_stock(mm, record, "stock")
    scaled = project_stock(inch, record, "stock")
    assert scaled.views[0].maximum == pytest.approx(tuple(v * 25.4 for v in before.views[0].maximum))
    setup = MachineSetup((10, 20, 30), mm.size_mm, (4, 5, 6), False, 90, mm)
    moved = project_stock(mm, setup.record(), "machine")
    previous = project_stock(mm, replace(setup, work_offset_mm=(1, 2, 3)).record(), "machine")
    assert moved.corner == (14, 25, 36)
    assert previous.corner == (5, 7, 9)
    assert moved.views[0].minimum[0] - previous.views[0].minimum[0] == pytest.approx(9)
    assert moved.views[1].minimum[1] - previous.views[1].minimum[1] == pytest.approx(27)


def test_projection_cancellation_returns_no_partial_snapshot(tmp_path):
    source = StockModel.load(mesh(tmp_path, l_stock()).source_path, "mm")
    with pytest.raises(InterruptedError, match="cancelled"):
        project_stock(source, MachineSetup().record(), "stock", cancelled=lambda: True)


@pytest.mark.parametrize("change", ["frame", "angle", "offset"])
def test_invalid_drawing_declarations_are_refused(tmp_path, change):
    source = StockModel.load(mesh(tmp_path, l_stock()).source_path, "mm")
    record = MachineSetup().record()
    frame = "machine"
    if change == "frame":
        frame = "unrecognized"
    elif change == "angle":
        record["stock_rotation_deg"] = True
    else:
        record["work_offset_mm"] = (math.nan, 0, 0)
    with pytest.raises(ValueError):
        project_stock(source, record, frame)
