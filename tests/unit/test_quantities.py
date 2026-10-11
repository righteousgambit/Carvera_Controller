"""Operator expressions must retain units and cannot execute Python."""

import pytest

from carveracontroller.machine.quantities import QuantityError, parse_quantity


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1/4 in", 6.35),
        ('1/4"', 6.35),
        ("127/2", 63.5),
        ("(1+1/4) inches", 31.75),
        ("1 1/4 in", 31.75),
        ("-1 1/4 in", -31.75),
        ("2.5 cm", 25),
        ("50 µm", 0.05),
        ("1e-3 m", 1),
        ("-(3+2)*4 mm", -20),
        ("−(3+2)×4 mm", -20),
        ("1÷4 in", 6.35),
    ],
)
def test_length_expressions(text, expected):
    assert parse_quantity(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text,kind,expected",
    [
        ("12 ipm", "feed", 304.8),
        ("2 mm/s", "feed", 120),
        ("1/2 in/min", "feed", 12.7),
        ("3.141592653589793 rad", "angle", 180),
        ("90°", "angle", 90),
        ("12000 rpm", "rpm", 12000),
        ("6/2", "scalar", 3),
    ],
)
def test_other_dimensions(text, kind, expected):
    assert parse_quantity(text, kind) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "nan",
        "inf",
        "1e309",
        "1/0",
        "2**10",
        "__import__('os')",
        "[1][0]",
        "True",
        "1 in + 2 mm",
        "1,000",
        "0x10",
        "1 # hidden text",
        "1e13",
        "1;2",
        "1+",
        "(1+2",
        "(" * 20 + "1" + ")" * 20,
        "1+" * 40 + "1",
        "1" * 257,
    ],
)
def test_invalid_or_executable_input_is_rejected(text):
    with pytest.raises(QuantityError):
        parse_quantity(text)


def test_wrong_units_bounds_and_whole_numbers():
    for text, kind in (("10 mm", "rpm"), ("10 rpm", "length"), ("10 in", "scalar")):
        with pytest.raises(QuantityError):
            parse_quantity(text, kind)
    with pytest.raises(QuantityError, match="Maximum"):
        parse_quantity("100 in", maximum=1000)
    with pytest.raises(QuantityError, match="Minimum"):
        parse_quantity("-1", minimum=0)
    with pytest.raises(QuantityError, match="whole"):
        parse_quantity("3/2", "scalar", integer=True)
    assert parse_quantity("6/2", "scalar", integer=True) == 3
