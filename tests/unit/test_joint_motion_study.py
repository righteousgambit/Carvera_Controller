import hashlib
import json

import pytest

from carveracontroller.machine.joint_motion_study import MAX_STUDY_BYTES, read_joint_study

SHA = "a" * 64


def record():
    return {
        "schema": 1,
        "program_sha256": SHA,
        "line": 2,
        "seconds": 30,
        "model_source": "Declared table geometry",
        "trajectory_source": "Entered unwrapped joints",
        "machine": {
            "schema": 1,
            "name": "Declared table",
            "work_chain": [{"name": "table", "kind": "rotary", "axis": [0, 0, 1], "minimum": -720, "maximum": 720}],
            "tool_base": {"translation": [100, 0, 0]},
        },
        "tool_length_mm": 10,
        "samples": [{"fraction": 0, "positions": {"table": 0}}, {"fraction": 1, "positions": {"table": 90}}],
        "velocity_limits": [{"name": "table", "kind": "rotary", "per_second": 2, "source": "Declared config"}],
    }


def read(tmp_path, data=None, raw=None, **kwargs):
    path = tmp_path / "study.json"
    path.write_bytes(raw if raw is not None else json.dumps(data or record()).encode())
    return read_joint_study(path, program_sha256=SHA, line=2, seconds=30, **kwargs)


def test_operator_file_produces_real_joint_and_work_frame_demand_with_content_identity(tmp_path):
    data = record()
    report = read(tmp_path, data)
    assert report.world_tip_length_mm == 0
    assert report.work_tip_length_mm == pytest.approx(157.0796, rel=0.0001)
    assert report.joint_demands[0].maximum_sampled_per_second == 3
    assert report.joint_demands[0].exceeds_limit
    assert "model SHA256" in report.model_source
    assert hashlib.sha256(json.dumps(data).encode()).hexdigest() in report.trajectory_source


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", True),
        ("line", True),
        ("program_sha256", "b" * 64),
        ("line", 3),
        ("seconds", 15),
        ("seconds", True),
        ("seconds", float("nan")),
        ("tool_length_mm", -1),
        ("model_source", ""),
        ("trajectory_source", "x" * 241),
        ("samples", []),
        ("velocity_limits", []),
        ("linear_step_mm", 0),
        ("rotary_step_degrees", True),
        ("unexpected", 1),
    ],
)
def test_mismatched_or_invalid_studies_do_not_produce_a_report(tmp_path, key, value):
    data = record()
    data[key] = value
    with pytest.raises(ValueError):
        read(tmp_path, data)


@pytest.mark.parametrize("mutation", ["kind", "joint", "boolean", "fraction", "incomplete", "tcp"])
def test_joint_mapping_and_samples_remain_explicit(tmp_path, mutation):
    data = record()
    if mutation == "kind":
        data["velocity_limits"][0]["kind"] = "linear"
    elif mutation == "joint":
        data["velocity_limits"][0]["name"] = "invented"
    elif mutation == "boolean":
        data["velocity_limits"][0]["per_second"] = True
    elif mutation == "fraction":
        data["samples"][1]["fraction"] = 0
    elif mutation == "incomplete":
        data["samples"][1]["positions"] = {}
    else:
        data["machine"]["controller_tcp_supported"] = True
    with pytest.raises(ValueError):
        read(tmp_path, data)


def test_duplicate_keys_oversized_and_non_utf8_files_are_rejected(tmp_path):
    raw = json.dumps(record()).replace('"schema": 1', '"schema": 1, "schema": 1', 1).encode()
    for malformed in (raw, b" " * (MAX_STUDY_BYTES + 1), b"\xff"):
        with pytest.raises(ValueError):
            read(tmp_path, raw=malformed)


def test_cancellation_withholds_report(tmp_path):
    with pytest.raises(InterruptedError):
        read(tmp_path, cancelled=lambda: True)


def test_feedback_import_is_bound_to_block_and_exact_joint_names(tmp_path):
    data = record()
    data["observed_feedback"] = {
        "source": "Recorded rotary trace",
        "timing_source": "Block-relative timestamps; clock qualification pending",
        "samples": [
            {"seconds": t, "reported": {"table": t * t / 10}, "commanded": {"table": t * t / 10 - 0.1}}
            for t in (0, 10, 20, 30)
        ],
    }
    report = read(tmp_path, data)
    assert report.feedback.samples == 4
    assert report.feedback.demands[0].maximum_acceleration == pytest.approx(0.2)
    assert report.feedback.demands[0].maximum_following_error == pytest.approx(0.1)
    data["observed_feedback"]["samples"][-1]["seconds"] = 29
    with pytest.raises(ValueError, match="cover"):
        read(tmp_path, data)


def test_retained_declared_pose_geometry_has_exact_interval_timing_and_rates(tmp_path):
    data = record()
    data["samples"] = [
        {"fraction": 0, "positions": {"table": 0}},
        {"fraction": 0.25, "positions": {"table": 90}},
        {"fraction": 1, "positions": {"table": 0}},
    ]
    report = read(tmp_path, data)
    assert len(report.path_points) == report.pose_samples == 181
    initial, corner, final = (report.path_points[i] for i in (0, 90, 180))
    assert initial.incoming_rates == ()
    assert corner.elapsed == 7.5 and final.elapsed == 30
    assert dict(corner.incoming_rates)["table"] == 12
    assert dict(final.incoming_rates)["table"] == -4
    assert corner.work_tip_mm == pytest.approx((0, -100, -10))
    assert final.work_tip_mm == pytest.approx(initial.work_tip_mm)
    assert corner.world_tip_mm == initial.world_tip_mm
