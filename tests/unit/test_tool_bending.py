import math

import pytest

from carveracontroller.machine.quantities import QuantityError, parse_quantity
from carveracontroller.machine.tool_bending import estimate_cantilever


def test_cantilever_against_analytic_reference_and_sensitivity():
    reference = estimate_cantilever(10, 100, 100, 200000)
    inertia = math.pi * 10**4 / 64
    assert reference.displacement_mm == pytest.approx(100 * 100**3 / (3 * 200000 * inertia))
    assert reference.root_stress_mpa == pytest.approx(100 * 100 * 5 / inertia)
    assert reference.tip_slope_rad == pytest.approx(100 * 100**2 / (2 * 200000 * inertia))
    assert estimate_cantilever(10, 50, 100, 200000).compliance_mm_per_n == pytest.approx(
        reference.compliance_mm_per_n / 8
    )
    assert estimate_cantilever(20, 100, 100, 200000).compliance_mm_per_n == pytest.approx(
        reference.compliance_mm_per_n / 16
    )
    zero = estimate_cantilever(10, 100, 0, 200000)
    assert zero.displacement_mm == zero.root_stress_mpa == zero.tip_slope_rad == 0
    assert zero.compliance_mm_per_n == reference.compliance_mm_per_n


@pytest.mark.parametrize(
    "index,value", [(0, 0), (1, -1), (2, -1), (3, 0), (0, True), (2, float("nan")), (3, float("inf")), (1, 10001)]
)
def test_invalid_geometry_or_assumptions_rejected(index, value):
    args = [6.35, 30, 20, 600000]
    args[index] = value
    with pytest.raises(ValueError):
        estimate_cantilever(*args)


def test_model_assumption_limits_are_visible():
    assert "Short beam" in estimate_cantilever(10, 20, 1, 200000).limitations[0]
    assert "small-deflection" in estimate_cantilever(1, 100, 100, 1000).limitations[0]


@pytest.mark.parametrize(
    "text,kind,expected",
    [
        ("10 lbf", "force", 44.482216152605),
        ("0.1 kN", "force", 100),
        ("600 GPa", "pressure", 600000),
        ("1000 psi", "pressure", 6.894757293168),
        ("1000000 Pa", "pressure", 1),
    ],
)
def test_force_and_modulus_units(text, kind, expected):
    assert parse_quantity(text, kind) == pytest.approx(expected)
    with pytest.raises(QuantityError):
        parse_quantity(text, "length")
