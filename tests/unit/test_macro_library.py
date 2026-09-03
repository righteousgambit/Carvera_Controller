"""The shipped macros must pass the checks we apply to anyone else's programs.

These are written from documented firmware behaviour and have not been run on
a machine, so static checking is the only guarantee available. It is worth
having: a macro that fails our own linter has no business being shipped.
"""

import glob
import os

import pytest

from carveracontroller.machine.program_check import Severity, check_program

_MACRO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "carveracontroller", "gcodes", "macros")


def _macros():
    return sorted(glob.glob(os.path.join(_MACRO_DIR, "*.nc")))


def test_the_macro_library_exists():
    assert _macros(), "no macros found; the path is wrong"


@pytest.mark.parametrize("path", _macros(), ids=lambda p: os.path.basename(p))
def test_macro_passes_the_program_checker(path):
    with open(path) as handle:
        issues = check_program(handle.read().splitlines())

    assert issues == [], [f"{i.code}: {i.message}" for i in issues]


@pytest.mark.parametrize("path", _macros(), ids=lambda p: os.path.basename(p))
def test_macro_declares_units_and_distance_mode(path):
    """Modal state is inherited from whatever ran last, so every macro sets it."""
    with open(path) as handle:
        text = handle.read()

    assert "G21" in text, "must set millimetres explicitly"
    assert "G90" in text, "must set absolute distance mode explicitly"


@pytest.mark.parametrize("path", _macros(), ids=lambda p: os.path.basename(p))
def test_macro_explains_itself(path):
    """Someone runs these at a machine. They open with what it does."""
    with open(path) as handle:
        first = handle.readline().strip()

    assert first.startswith("("), "first line should be a comment naming the macro"


def test_no_macro_uses_inch_mode():
    for path in _macros():
        with open(path) as handle:
            issues = check_program(handle.read().splitlines())
        assert not [i for i in issues if i.severity is Severity.ERROR]
        with open(path) as handle:
            assert "G20" not in handle.read(), f"{path} uses broken inch mode"
