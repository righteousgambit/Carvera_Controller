"""Cancellation stops bounded asset reads, validation and complete mesh packing."""

import gzip
import io
import json
from pathlib import Path

import pytest

from carveracontroller.addons.cad_identity import read_asset_bytes
from carveracontroller.addons.tool_visualization import cad_assets
from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_mesh
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition


def payload(count=1000, origin="tip"):
    return {
        "schema": "carvera-tool-mesh-v1",
        "units": "mm",
        "axis": "+Z",
        "origin": origin,
        "triangles": [-1, 0, 0, 1, 0, 0, 0, 1, 12] * count,
    }


def test_cancel_before_file_open(tmp_path, monkeypatch):
    def no_open(*args, **kwargs):
        pytest.fail("Cancelled work must not open a file")

    monkeypatch.setattr(Path, "open", no_open)
    with pytest.raises(InterruptedError):
        build_tool_mesh(ToolDefinition(1, geometry_path=str(tmp_path / "missing.json")), cancelled=lambda: True)


def test_asset_read_stops_after_first_bounded_chunk(monkeypatch):
    reads = []

    class Stream(io.BytesIO):
        def read(self, count):
            reads.append(count)
            return super().read(count)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: Stream(b"x" * 200000))
    with pytest.raises(InterruptedError):
        read_asset_bytes("synthetic.json", 200000, cancelled=lambda: bool(reads))
    assert reads == [65536]


@pytest.mark.parametrize("compressed", [False, True])
def test_completed_asset_preserves_digest_schema_and_full_mesh(tmp_path, compressed):
    path = tmp_path / ("synthetic.json.gz" if compressed else "synthetic.json")
    raw = json.dumps(payload()).encode()
    path.write_bytes(gzip.compress(raw) if compressed else raw)
    expected = build_tool_mesh(ToolDefinition(1, geometry_path=str(path)))
    actual = build_tool_mesh(ToolDefinition(1, geometry_path=str(path)), cancelled=lambda: False)
    assert actual == expected
    assert len(actual[0]) == 3000 * 12
    assert len(actual[1]) == 3000
    assert (
        cad_assets.load_tool_asset(path)["_converted_sha256"]
        == cad_assets.load_tool_asset(path, cancelled=lambda: False)["_converted_sha256"]
    )


def test_cancel_during_expansion_stops_before_json_decode(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json.gz"
    path.write_bytes(gzip.compress(json.dumps(payload(10000)).encode()))
    original = gzip.GzipFile.read
    reads = []

    def read(stream, count):
        reads.append(count)
        return original(stream, count)

    monkeypatch.setattr(gzip.GzipFile, "read", read)
    monkeypatch.setattr(cad_assets.json, "loads", lambda *_args: pytest.fail("Cancelled expansion must not decode"))
    with pytest.raises(InterruptedError):
        cad_assets.load_tool_asset(path, cancelled=lambda: bool(reads))
    assert reads == [65536]


def test_cancel_after_json_decode_never_starts_validation(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(payload()))
    decoded = []
    original = cad_assets.json.loads

    def decode(raw):
        result = original(raw)
        decoded.append(True)
        return result

    monkeypatch.setattr(cad_assets.json, "loads", decode)
    with pytest.raises(InterruptedError):
        cad_assets.load_tool_asset(path, cancelled=lambda: bool(decoded))


def test_coordinate_validation_checks_cancel_every_128_values(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json"
    path.write_text("{}")
    visited = []

    class Values(list):
        def __iter__(self):
            for value in super().__iter__():
                visited.append(value)
                yield value

    data = payload()
    data["triangles"] = Values(data["triangles"])
    monkeypatch.setattr(cad_assets.json, "loads", lambda _raw: data)
    with pytest.raises(InterruptedError):
        cad_assets.load_tool_asset(path, cancelled=lambda: len(visited) >= 128)
    assert len(visited) == 129  # next value fetched before its boundary check
    assert "_converted_sha256" not in data


def test_mesh_packing_stops_at_128_triangles_without_partial_result(monkeypatch):
    slices = []

    class Values(list):
        def __getitem__(self, key):
            if isinstance(key, slice):
                slices.append(key)
            return super().__getitem__(key)

    data = payload()
    data["triangles"] = Values(data["triangles"])
    monkeypatch.setattr(cad_assets, "load_tool_asset", lambda *_args, **_kwargs: data)
    with pytest.raises(InterruptedError):
        cad_assets.asset_mesh("synthetic.json", 1.0, clip_height=5, cancelled=lambda: len(slices) >= 3 * 128)
    assert len(slices) == 3 * 128


def test_cancel_between_cutter_and_holder_never_reads_holder(tmp_path, monkeypatch):
    cutter = tmp_path / "cutter.json"
    cutter.write_text(json.dumps(payload(1)))
    ready, calls = [], []
    original = cad_assets.asset_mesh

    def mesh(path, *args, **kwargs):
        calls.append(path)
        result = original(path, *args, **kwargs)
        ready.append(True)
        return result

    monkeypatch.setattr(cad_assets, "asset_mesh", mesh)
    with pytest.raises(InterruptedError):
        build_tool_mesh(
            ToolDefinition(1, geometry_path=str(cutter), holder_geometry_path="missing-holder.json", stickout=20),
            cancelled=lambda: bool(ready),
        )
    assert calls == [str(cutter)]


def test_cancelled_loader_keeps_invalid_coordinates_and_digest_guards(tmp_path):
    path = tmp_path / "synthetic.json"
    data = payload(1)
    data["triangles"][-1] = float("nan")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="invalid coordinates"):
        cad_assets.load_tool_asset(path, cancelled=lambda: False)
    with pytest.raises(ValueError, match="CAD bytes changed"):
        cad_assets.load_tool_asset(path, "0" * 64, cancelled=lambda: False)


@pytest.mark.parametrize("cancelled", [None, lambda: False])
def test_encoded_size_guard_retained(tmp_path, cancelled):
    path = tmp_path / "synthetic.json"
    path.write_bytes(b"x" * 20)
    with pytest.raises(ValueError, match="size limit"):
        read_asset_bytes(path, 10, cancelled=cancelled)


def test_expanded_size_guard_retained(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json.gz"
    path.write_bytes(gzip.compress(b"x" * 1000))
    monkeypatch.setattr(cad_assets, "MAX_BYTES", 64)
    with pytest.raises(ValueError, match="Expanded tool asset exceeds size limit"):
        cad_assets.load_tool_asset(path, cancelled=lambda: False)


def test_completed_clipped_cutter_and_holder_match_existing_geometry(tmp_path):
    cutter, holder = tmp_path / "cutter.json", tmp_path / "holder.json.gz"
    cutter.write_text(json.dumps(payload(10)))
    holder.write_bytes(gzip.compress(json.dumps(payload(10, "collet")).encode()))
    tool = ToolDefinition(1, geometry_path=str(cutter), holder_geometry_path=str(holder), stickout=5)
    assert build_tool_mesh(tool, cancelled=lambda: False) == build_tool_mesh(tool)
