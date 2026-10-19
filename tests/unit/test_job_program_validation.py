"""Detached real parser preparation cannot replace live machine telemetry."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.machine.job_program_validation import PreviewParserInputs, validate_preview_program


def inputs(**changes):
    return PreviewParserInputs(**{"clearance_z": -3.0, "wcoz": -100.0, "inch": False, "accuracy": 0.01, **changes})


@pytest.mark.parametrize(
    "lines",
    [
        ("G21 G90 G0 X0 Y0 Z10", "S12000 G1 X10 Z1 F100", "G93 G1 X20 F2"),
        ("G20 G90 G0 X0 Y0 Z1", "S12000 G1 X1 F10", "G91 G1 X-0.5"),
        ("G0 X10 Y0 Z10", "G2 X0 Y10 I-10 J0 F100"),
        ("G0 X0 Y0 Z10 A0", "G1 X10 A90 F100"),
        ("G0 X0 Y0 Z10", "G91 G81 X1 Y1 Z-1 R1 L3"),
    ],
)
def test_real_parser_preparation_does_not_change_global_variables_or_input(lines):
    before = copy.deepcopy(CNC.vars)
    assert validate_preview_program(lines, inputs()) > 0
    assert CNC.vars == before


def test_default_parser_keeps_existing_shared_state_behavior():
    before = copy.deepcopy(CNC.vars)
    try:
        parser = CNC()
        parser["feedmode"] = 93
        assert CNC.vars["feedmode"] == 93
        parser.parseLine("G0 X0 Y0 Z10", 1)
        parser.parseLine("S12000 G1 X10 Y20 Z1 F100", 2)
        assert CNC.vars["xmax"] == 10 and parser.getMargins()[-2:] == (10, 20)
    finally:
        CNC.vars.clear()
        CNC.vars.update(before)


def test_detached_parser_owns_a_copy_and_uses_its_declared_clearance():
    state = {"clearance_z": -3.0, "wcoz": -100.0}
    parser = CNC(variables=state)
    parser.parseLine("G0 X1 Y2", 1)
    assert parser.coordinates[-1][2] == 97
    assert state == {"clearance_z": -3.0, "wcoz": -100.0}
    parser["feedmode"] = 93
    assert "feedmode" not in state


@pytest.mark.parametrize("line", ["G1 X10 A100000000000 F100", "G91 G81 X1 Z-1 R1 L10000000000"])
def test_work_budget_stops_inside_large_single_block_without_global_changes(line):
    before = copy.deepcopy(CNC.vars)
    with pytest.raises(ValueError, match="point budget"):
        validate_preview_program(("G0 X0 Y0 Z10", line), inputs(), point_budget=20)
    assert CNC.vars == before


def test_cancellation_stops_inside_a_single_interpolated_block():
    before = copy.deepcopy(CNC.vars)
    calls = []

    def cancelled():
        calls.append(True)
        return len(calls) >= 10

    with pytest.raises(InterruptedError):
        validate_preview_program(("G0 X0 Y0 Z10", "G1 X10 A10000000 F100"), inputs(), cancelled=cancelled)
    assert CNC.vars == before and len(calls) == 10


def test_parallel_detached_parsers_cannot_cross_contaminate_clearance_or_telemetry():
    before = copy.deepcopy(CNC.vars)
    barrier = threading.Barrier(2)

    def parse(wco):
        parser = CNC(variables={"clearance_z": -3, "wcoz": wco})
        barrier.wait(2)
        parser.parseLine("G0 X10 Y20", 1)
        parser.parseLine("G93 G1 X15 F2", 2)
        return parser.vars.copy(), parser.coordinates[0][2]

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [future.result() for future in (pool.submit(parse, -100), pool.submit(parse, -50))]
    assert a[1] == 97 and b[1] == 47 and CNC.vars == before


@pytest.mark.parametrize("changes", [{"accuracy": 0}, {"accuracy": float("nan")}, {"inch": 1}, {"wcoz": True}])
def test_invalid_parser_inputs_are_not_replaced_by_defaults(changes):
    with pytest.raises(ValueError):
        inputs(**changes)


def test_unrepresentable_arc_step_refuses_instead_of_hanging():
    with pytest.raises(ValueError, match="not representable"):
        validate_preview_program(("G0 X1 Y0", "G2 X1 Y0 I-1 J0"), inputs(accuracy=1e-100))


def test_capture_retains_unknown_raw_values_for_worker_validation():
    declaration = PreviewParserInputs.declarations({"clearance_z": None, "wcoz": 4}, inch=False, accuracy=0.01)
    assert declaration["clearance_z"] is None
    with pytest.raises(ValueError):
        PreviewParserInputs(**declaration)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "G1 X1",
        "G1 (a) X2 (b)",
        "G1 ((nested) X2)",
        "G1 (((",
        "G1 )))",
        "(open\nG1 (closed) X2",
        "(open\rclosed) X2",
        "G1 (a\nb) X2",
        "(a)(b)(c)",
        "(((a)\n(b))",
        "G1 (\x00) X2",
        "(a\u2028b) X2",
    ],
)
def test_linear_comment_stripping_preserves_exact_regex_semantics(text):
    from carveracontroller.CNC import PARENPAT, strip_parenthesized_comments

    assert strip_parenthesized_comments(text) == PARENPAT.sub("", text)


def test_linear_comment_stripping_matches_regex_on_randomized_text():
    import random

    from carveracontroller.CNC import PARENPAT, strip_parenthesized_comments

    rng = random.Random(39193694883)
    for _ in range(1000):
        text = "".join(rng.choices("G1 XYZ0123() \n\r\t", k=rng.randrange(250)))
        assert strip_parenthesized_comments(text) == PARENPAT.sub("", text)


def test_cancellation_is_observed_inside_an_unmatched_comment_block():
    before = copy.deepcopy(CNC.vars)
    checks = []

    def cancelled():
        checks.append(True)
        return len(checks) >= 12

    with pytest.raises(InterruptedError):
        validate_preview_program(("G1 X1 " + "(" * 2_000_000,), inputs(), cancelled=cancelled)
    assert len(checks) == 12 and CNC.vars == before
