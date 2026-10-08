"""Inspection geometry imports and frame conversion on supported interpreters."""

import pytest

from carveracontroller.addons.cmm_workbench.core.features import (
    PointGeom,
    index_by_id,
    mcs_xyz_to_wcs_xyz,
    resolve_geometry,
)
from carveracontroller.addons.cmm_workbench.core.gcode import build_m118_echo_tail
from carveracontroller.addons.cmm_workbench.core.session import CMMWorkbenchFeature
from carveracontroller.CNC import CNC


def test_inspection_feature_resolves_on_supported_python():
    # Importing this module used to evaluate a PEP 604 type alias at runtime,
    # preventing the entire inspection workbench from opening on Python 3.9.
    feature = CMMWorkbenchFeature.new_point("Measured point", 12.5, -4.0, 3.0)
    geometry = resolve_geometry(feature, index_by_id([feature]))
    assert isinstance(geometry, PointGeom)
    assert (geometry.x, geometry.y) == (12.5, -4.0)


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [(0.0, (3.0, 4.0, 5.0)), (90.0, (4.0, -3.0, 5.0))],
)
def test_inspection_coordinates_use_current_rotated_work_frame(monkeypatch, rotation, expected):
    monkeypatch.setattr(CNC, "vars", {"rotation_angle": rotation, "wcox": 10.0, "wcoy": 20.0, "wcoz": 30.0})
    assert mcs_xyz_to_wcs_xyz(13.0, 24.0, 35.0) == pytest.approx(expected)


def test_probe_echo_rejects_missing_or_empty_result_schema():
    with pytest.raises(ValueError, match="Unknown op"):
        build_m118_echo_tail("UNKNOWN")
    with pytest.raises(ValueError, match="Empty result_vars"):
        build_m118_echo_tail("M466", [])
    assert build_m118_echo_tail("M466").splitlines() == [
        "M118 CMMProbe START M466 154 155 156",
        "M118.1 P#154",
        "M118.1 P#155",
        "M118.1 P#156",
        "M118 CMMProbe END",
    ]


@pytest.mark.parametrize(("diameter_y", "expected_kind"), [(10.01, "circle"), (10.1, "ellipse")])
def test_bore_result_preserves_roundness_classification(monkeypatch, diameter_y, expected_kind):
    from carveracontroller.addons.cmm_workbench.core.features import features_from_m461_m462

    monkeypatch.setattr(CNC, "vars", {"rotation_angle": 0, "wcox": 10, "wcoy": 20, "wcoz": 0})
    labels = dict.fromkeys(
        (
            "segment_label",
            "endpoint_a_label",
            "endpoint_b_label",
            "center_label",
            "h_segment_label",
            "h_endpoint_a_label",
            "h_endpoint_b_label",
            "v_segment_label",
            "v_endpoint_a_label",
            "v_endpoint_b_label",
            "curve_label",
        ),
        "Measured bore",
    )
    features, error = features_from_m461_m462(
        {"151": 10.0, "152": diameter_y, "154": 13.0, "155": 24.0},
        ["151", "152", "154", "155"],
        preset="CenterBore",
        mx=0,
        my=0,
        source="M461",
        tolerance_mm=0.02,
        **labels,
    )
    assert error is None and len(features) == 1
    assert features[0].kind.value == expected_kind
    geometry = resolve_geometry(features[0], index_by_id(features))
    assert (geometry.cx, geometry.cy) == (3.0, 4.0)
