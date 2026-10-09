"""Exact stock bytes, explicit units and manifold topology; no occupancy proxy."""

import hashlib
import math
import struct
from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.addons.manufacturing_simulation import stock_mesh
from carveracontroller.addons.manufacturing_simulation.stock_mesh import StockMeshInput


def box(low=(0, 0, 0), high=(2, 2, 2)):
    x, y, z = low
    X, Y, Z = high
    faces = (
        ((x, y, z), (x, y, Z), (x, Y, Z), (x, Y, z)),
        ((X, y, z), (X, Y, z), (X, Y, Z), (X, y, Z)),
        ((x, y, z), (X, y, z), (X, y, Z), (x, y, Z)),
        ((x, Y, z), (x, Y, Z), (X, Y, Z), (X, Y, z)),
        ((x, y, z), (x, Y, z), (X, Y, z), (X, y, z)),
        ((x, y, Z), (X, y, Z), (X, Y, Z), (x, Y, Z)),
    )
    return [(f[0], f[1], f[2]) for f in faces] + [(f[0], f[2], f[3]) for f in faces]


def ascii_stl(triangles):
    lines = ["solid stock"]
    for triangle in triangles:
        lines.extend(("facet normal 0 0 0", "outer loop"))
        lines.extend("vertex " + " ".join(str(v) for v in p) for p in triangle)
        lines.extend(("endloop", "endfacet"))
    return ("\n".join(lines + ["endsolid stock"]) + "\n").encode()


def binary_stl(triangles):
    return (
        b"solid binary header".ljust(80, b" ")
        + struct.pack("<I", len(triangles))
        + b"".join(struct.pack("<12fH", 0, 0, 0, *(v for p in triangle for v in p), 0) for triangle in triangles)
    )


def load(tmp_path, triangles=None, raw=None, units="mm", **kwargs):
    path = tmp_path / "stock.STL"
    path.write_bytes(raw if raw is not None else ascii_stl(box() if triangles is None else triangles))
    return StockMeshInput.load(path, units=units, **kwargs)


@pytest.mark.parametrize("encode", [ascii_stl, binary_stl])
def test_exact_bytes_and_unmodified_stock_local_coordinates(tmp_path, encode):
    triangles = box((-2, 3, 5), (4, 7, 11))
    raw = encode(triangles)
    value = load(tmp_path, raw=raw)
    assert value.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert value.minimum_mm == (-2, 3, 5)
    assert value.maximum_mm == (4, 7, 11)
    assert value.triangles_mm == tuple(triangles)
    assert value.source_units == "mm"
    with pytest.raises(FrozenInstanceError):
        value.source_units = "inch"


def test_explicit_inches_scale_without_centering_or_orientation_change(tmp_path):
    value = load(tmp_path, box((1, 2, 3), (2, 4, 5)), units="inch")
    assert value.minimum_mm == pytest.approx((25.4, 50.8, 76.2))
    assert value.maximum_mm == pytest.approx((50.8, 101.6, 127))


@pytest.mark.parametrize("units", [None, "auto", "cm", True])
def test_no_unit_guess(tmp_path, units):
    with pytest.raises(ValueError, match="explicit"):
        load(tmp_path, units=units)


def test_changed_source_refused_and_previous_detached_input_retained(tmp_path):
    previous = load(tmp_path)
    with pytest.raises(ValueError, match="bytes changed"):
        load(tmp_path, box((0, 0, 0), (3, 3, 3)), expected_sha256=previous.source_sha256)
    assert previous.maximum_mm == (2, 2, 2)
    assert previous.triangles_mm == tuple(box())


@pytest.mark.parametrize(
    "triangles,reason",
    [
        (box()[:-1], "open"),
        (box() + [box()[0]], "duplicate"),
        ([(box()[0][0], box()[0][2], box()[0][1])] + box()[1:], "winding"),
        (box() + [((3, 0, 0), (3, 0, 0), (3, 1, 0))], "degenerate"),
        (box() + box((2, 2, 2), (4, 4, 4)), "nonmanifold vertex"),
        (box() + box((2, 2, 0), (4, 4, 2)), "nonmanifold edge"),
    ],
)
def test_invalid_topology_refused(tmp_path, triangles, reason):
    with pytest.raises(ValueError, match=reason):
        load(tmp_path, triangles)


def test_closed_cavity_and_separate_components_keep_all_faces(tmp_path):
    hollow = box((0, 0, 0), (5, 5, 5)) + [(a, c, b) for a, b, c in box((1, 1, 1), (4, 4, 4))]
    value = load(tmp_path, hollow)
    assert value.triangles_mm == tuple(hollow)
    separate = box() + box((3, 0, 0), (5, 2, 2))
    assert load(tmp_path, separate).triangles_mm == tuple(separate)


def test_no_silent_seam_welding(tmp_path):
    triangles = box()
    a, b, c = triangles[0]
    triangles[0] = ((a[0] + 1e-10, a[1], a[2]), b, c)
    with pytest.raises(ValueError, match="open"):
        load(tmp_path, triangles)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 100001])
@pytest.mark.parametrize("encode", [ascii_stl, binary_stl])
def test_invalid_coordinates_refused(tmp_path, value, encode):
    triangles = box()
    a, b, c = triangles[0]
    triangles[0] = ((value, a[1], a[2]), b, c)
    with pytest.raises(ValueError, match="coordinates"):
        load(tmp_path, raw=encode(triangles))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"solid stock\nendsolid stock\n",
        ascii_stl(box()).replace(b"outer loop", b"outer nonsense", 1),
        ascii_stl(box()).replace(b"endfacet", b"endfacet\nvertex 0 0 0", 1),
        ascii_stl(box()).replace(b"endsolid stock", b""),
        ascii_stl(box()) + b"trailing data",
        binary_stl(box())[:-1],
        binary_stl(box()) + b"trailing data",
    ],
)
def test_framing_refuses_truncation_or_ignored_extra_geometry(tmp_path, raw):
    with pytest.raises(ValueError):
        load(tmp_path, raw=raw)


@pytest.mark.parametrize("encode", [ascii_stl, binary_stl])
def test_count_and_byte_limits(tmp_path, monkeypatch, encode):
    monkeypatch.setattr(stock_mesh, "MAX_TRIANGLES", 1)
    with pytest.raises(ValueError, match="triangle budget"):
        load(tmp_path, raw=encode(box()))
    monkeypatch.setattr(stock_mesh, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="size limit"):
        load(tmp_path, raw=encode(box()))


@pytest.mark.parametrize("stop", [1, 3, 5, 7, 10])
def test_cancellation_during_read_parse_and_topology_retains_previous(tmp_path, stop):
    previous = load(tmp_path)
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= stop

    with pytest.raises(InterruptedError):
        StockMeshInput.load(tmp_path / "stock.STL", units="mm", cancelled=cancelled)
    assert calls == stop
    assert previous.maximum_mm == (2, 2, 2)


def test_non_stl_refused(tmp_path):
    path = tmp_path / "stock.step"
    path.write_text("not an STL")
    with pytest.raises(ValueError, match="requires STL"):
        StockMeshInput.load(path, units="mm")


def test_direct_construction_cannot_bypass_source_validation():
    with pytest.raises(TypeError, match="StockMeshInput.load"):
        StockMeshInput()


@pytest.mark.parametrize("binary", [False, True])
def test_nonfinite_normals_refused_in_both_stl_formats(tmp_path, binary):
    if binary:
        raw = bytearray(binary_stl(box()))
        struct.pack_into("<f", raw, 84, math.nan)
        raw = bytes(raw)
    else:
        raw = ascii_stl(box()).replace(b"facet normal 0 0 0", b"facet normal nan 0 0", 1)
    with pytest.raises(ValueError, match="nonfinite normal"):
        load(tmp_path, raw=raw)
