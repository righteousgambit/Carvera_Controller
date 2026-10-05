import json
from dataclasses import replace

import pytest

from carveracontroller.machine.scene_interaction import SurfaceHit
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, sample_result, summary
from carveracontroller.machine.surface_measurement import plan_surface_measurement


def nominal():
    ref = SurfaceHit("stock", "stock", 4, 10, (1, 2, 3), (1, 2, 3), (0, 0, 1), ((0, 0, 3), (10, 0, 3), (0, 10, 3)))
    return plan_surface_measurement(ref, tip_diameter_mm=2, clearance_mm=5, overtravel_mm=1)


def feature(store, limits=(-0.05, 0.05)):
    return store.create(
        nominal(),
        part="A-001",
        name="Top face",
        context={"machine": "C1", "setup": {"offset": [1, 2, 3]}},
        limits=limits,
    )


def receipt(store, identity, z, **kwargs):
    return store.record(
        identity,
        (1, 2, z),
        **{
            "kind": "compensated_ball_center",
            "source_ref": "measurement-01",
            "registration_ref": "registration-A",
            "calibration_ref": "probe-A",
            "observed_at": "2026-10-05T10:00:00Z",
            **kwargs,
        },
    )


def test_retained_identity_repeat_statistics_and_roundtrip(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "inspections.json")
    identity = feature(store)
    receipt(store, identity, 4.01)
    receipt(store, identity, 4.03, source_ref="measurement-02")
    f = SurfaceInspectionStore(store.path).get(identity)
    s = summary(f)
    assert s["recorded"] == s["evaluated"] == 2
    assert s["unevaluated"] == s["outside"] == 0
    assert s["mean_mm"] == pytest.approx(0.02)
    assert s["range_mm"] == pytest.approx(0.02)
    assert s["sample_stdev_mm"] == pytest.approx(0.0141421356)
    assert f["plan"]["reference"]["triangle_index"] == 4
    assert f["context"]["setup"]["offset"] == [1, 2, 3]
    assert f["samples"][0]["observed_at"] != f["samples"][0]["recorded_at"]
    # Returned records cannot mutate retained state.
    f["samples"].clear()
    assert len(store.get(identity)["samples"]) == 2


@pytest.mark.parametrize("missing", ["registration_ref", "calibration_ref"])
def test_unregistered_or_uncompensated_positions_are_retained_unevaluated(tmp_path, missing):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    identity = feature(store)
    receipt(store, identity, 100, **{missing: ""})
    assert sample_result(store.get(identity), store.get(identity)["samples"][0]) == {
        "deviation_mm": None,
        "state": "unevaluated",
    }
    assert summary(store.get(identity))["mean_mm"] is None


def test_raw_trigger_is_never_compared_even_with_references(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    identity = feature(store)
    receipt(store, identity, 100, kind="raw_trigger")
    assert summary(store.get(identity))["evaluated"] == 0


def test_empty_untoleranced_and_outside_results_do_not_imply_conformance(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    identity = feature(store)
    assert summary(store.get(identity))["mean_mm"] is None
    receipt(store, identity, 4.2)
    assert summary(store.get(identity))["outside"] == 1
    assert summary(store.get(identity))["sample_stdev_mm"] is None
    untoleranced = feature(store, (None, None))
    receipt(store, untoleranced, 4.2)
    f = store.get(untoleranced)
    assert sample_result(f, f["samples"][0])["state"] == "untoleranced"


@pytest.mark.parametrize("limits", [(None, 0.1), (1, -1), (False, 1), (0, float("inf"))])
def test_invalid_limits_do_not_create_records(tmp_path, limits):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    with pytest.raises(ValueError):
        feature(store, limits)
    assert not store.path.exists()
    assert store.features == []


@pytest.mark.parametrize("edit", ["point", "context", "kind", "nan", "duplicate"])
def test_corrupt_records_are_preserved_and_writes_blocked(tmp_path, edit):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    identity = feature(store)
    receipt(store, identity, 4)
    data = json.loads(store.path.read_text())
    f = data["features"][0]
    if edit == "point":
        f["plan"]["reference"]["component_point_mm"][0] += 1
    elif edit == "context":
        f["context"]["machine"] = "other"
    elif edit == "kind":
        f["samples"][0]["kind"] = "unknown"
    elif edit == "nan":
        f["samples"][0]["position_mm"][0] = float("nan")
    else:
        f["samples"].append(f["samples"][0])
    store.path.write_text(json.dumps(data))
    original = store.path.read_bytes()
    broken = SurfaceInspectionStore(store.path)
    assert broken.error
    with pytest.raises(ValueError, match="repair"):
        feature(broken)
    assert store.path.read_bytes() == original


def test_stale_writer_and_failed_replace_preserve_receipts(tmp_path, monkeypatch):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    identity = feature(store)
    stale = SurfaceInspectionStore(store.path)
    receipt(store, identity, 4)
    with pytest.raises(ValueError, match="changed externally"):
        receipt(stale, identity, 4.1)
    original = store.path.read_bytes()
    monkeypatch.setattr(
        "carveracontroller.machine.surface_inspection.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError, match="disk full"):
        receipt(store, identity, 4.2)
    assert store.path.read_bytes() == original
    assert len(store.get(identity)["samples"]) == 1


def test_sloped_plane_repeat_deviation_uses_normal_not_z(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    p = nominal()
    ref = replace(p.reference, normal=(0, 0.6, 0.8), triangle=((0, 0, 4.5), (10, 0, 4.5), (0, 10, -3)))
    p = plan_surface_measurement(ref, tip_diameter_mm=2, clearance_mm=5, overtravel_mm=1)
    identity = store.create(p, part="A", name="Slope", context={})
    store.record(
        identity,
        (1, 2.7, 3.8),
        kind="compensated_ball_center",
        source_ref="slope",
        registration_ref="R",
        calibration_ref="C",
    )
    assert summary(store.get(identity))["mean_mm"] == pytest.approx(0.06)


@pytest.mark.parametrize("change", [{"component_point_mm": (20, 20, 3)}, {"normal": (0, 1, 0)}])
def test_inconsistent_nominal_geometry_cannot_be_saved(tmp_path, change):
    store = SurfaceInspectionStore(tmp_path / "inspect.json")
    p = nominal()
    p = replace(p, reference=replace(p.reference, **change))
    with pytest.raises(ValueError):
        store.create(p, part="A", name="invalid", context={})
    assert not store.path.exists()


def test_series_restores_nominal_geometry_once_and_retains_unevaluated_receipts(tmp_path, monkeypatch):
    from carveracontroller.machine import surface_inspection as module

    store = SurfaceInspectionStore(tmp_path / "series.json")
    identity = feature(store)
    receipt(store, identity, 4.02)
    receipt(store, identity, 4.2)
    receipt(store, identity, 100, kind="raw_trigger")
    f = store.get(identity)
    restore = module.restore_plan
    calls = []

    def counted(record):
        calls.append(record)
        return restore(record)

    monkeypatch.setattr(module, "restore_plan", counted)
    results = module.sample_results(f)
    assert len(calls) == 1
    assert [r["state"] for r in results] == ["within_declared_limits", "outside_declared_limits", "unevaluated"]
    assert results[-1]["deviation_mm"] is None


def test_bounded_file_read_ignores_misleading_size_metadata():
    import io

    from carveracontroller.machine.surface_inspection import read_bounded

    reads = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class GrowingFile:
        def open(self, mode):
            assert mode == "rb"
            return Stream(b"x" * 100)

    with pytest.raises(ValueError, match="size limit"):
        read_bounded(GrowingFile(), 20)
    assert reads == [21]
