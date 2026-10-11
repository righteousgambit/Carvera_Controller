"""Adversarial boundary reconstruction; no viewer cache or machine IO."""

import pytest

from carveracontroller.machine.recovery_plan import RecoveryPlanError, build_reentry, parse_words, reconstruct_recovery


def program(*extra):
    return ["G21 G90 G17 G40 G94", "G54", "T2 M6", "M3 S12000 M7", "G0 X0 Y0 Z5", *extra, "G1 X9 F600"]


def boundary(*extra):
    lines = program(*extra)
    return reconstruct_recovery(lines, len(lines))


def approach(state, **kwargs):
    values = {
        "current_work_mm": (0, 0, 5),
        "current_machine_z_mm": -10,
        "clearance_machine_z_mm": -2,
        "verified_wcs_index": 0,
        "verified_tool": 2,
    }
    values.update(kwargs)
    return build_reentry(state, **values)


def test_selected_line_is_excluded_and_relative_moves_have_absolute_anchor():
    state = boundary("G91", "G1 X1 Y2 Z-3 F600")
    assert state.position_mm == (1, 2, 2)
    assert state.distance == "G91" and state.motion == "G1"
    assert state.start_line == len(program("G91", "G1 X1 Y2 Z-3 F600"))


def test_feed_is_converted_at_assignment_before_later_unit_change():
    state = boundary("G20 G1 F10", "G21", "G1 X1 Z2")
    assert state.feed_mm_min == 254
    commands = approach(state)
    assert "G1 F254.000000" in commands
    assert "G1 F254.000000" in commands


def test_inch_positions_and_feed_restore_without_rounding():
    state = boundary("G20 G1 X0.1 Y0.2 Z0.05 F10.25")
    assert state.position_mm == pytest.approx((2.54, 5.08, 1.27))
    commands = approach(state)
    assert "G1 F260.350000" in commands and "G1 F10.250000" in commands
    assert commands.index("M3 S12000.000000") < commands.index("G1 Z1.270000")
    assert "G49" not in " ".join(commands)


@pytest.mark.parametrize("word", ["G90 G91", "G20 G21", "G54 G55", "G0 G1", "M3 M5", "M7 M9", "X1 X2"])
def test_ambiguous_same_line_modal_or_axis_words_are_refused(word):
    with pytest.raises(RecoveryPlanError, match="ambiguous"):
        boundary(word)


@pytest.mark.parametrize(
    "word",
    [
        "G53 G0 X1",
        "G92 X1",
        "G10 L2 P1 X1",
        "G43 H2",
        "G49",
        "G2 X1 I1",
        "G93",
        "G38.2 Z-1",
        "M98 P1",
        "M30",
        "O100",
        "#1=2",
        "A90",
        "G1 X[1+2]",
    ],
)
def test_unsupported_geometry_macros_and_modes_are_refused(word):
    with pytest.raises(RecoveryPlanError):
        boundary(word)


def test_comments_compact_words_and_line_numbers_are_parsed_without_comment_motion():
    assert parse_words("N10G1X.5Y-2 (G53 X99 (nested)) ; M6 T7", 1) == [("N", 10), ("G", 1), ("X", 0.5), ("Y", -2)]
    state = boundary("G1X1Y2Z3F600 (G55)")
    assert state.position_mm == (1, 2, 3) and state.wcs_index == 0
    with pytest.raises(RecoveryPlanError, match="comment"):
        boundary("G1 X1 (unfinished")


def test_partial_axis_and_relative_prefix_cannot_invent_origin():
    lines = ["G21 G91 G17 G94 G54", "M5 M9", "G1 X1 F600", "G1 X2"]
    with pytest.raises(RecoveryPlanError, match="anchor"):
        reconstruct_recovery(lines, 4)
    lines[0] = "G21 G90 G17 G94 G54"
    with pytest.raises(RecoveryPlanError, match="all three"):
        reconstruct_recovery(lines, 4)


def test_wcs_or_tool_changes_reset_reconstructable_position():
    with pytest.raises(RecoveryPlanError, match="all three"):
        boundary("G55", "G1 X1 F600")
    with pytest.raises(RecoveryPlanError, match="all three"):
        boundary("T3 M6", "G1 X1 F600")
    state = boundary("G55", "G0 X1 Y2 Z3", "G1 F600")
    with pytest.raises(RecoveryPlanError, match="prepare"):
        approach(state)


def test_selected_t_is_not_active_tool_until_m6():
    state = boundary("T3", "G1 X1 F600")
    assert state.tool == 2 and state.selected_tool == 3
    assert not any("M6" in cmd for cmd in approach(state))


def test_no_reentry_motion_when_verified_machine_is_already_at_boundary():
    state = boundary("G1 F600")
    commands = approach(state)
    assert not any(any(axis in cmd for axis in (" X", " Y", " Z", "G53")) for cmd in commands)
    assert commands[-1] == "G1"


def test_clearance_must_raise_in_machine_space_and_cover_target_height():
    state = boundary("G1 X1 Z2 F600")
    with pytest.raises(RecoveryPlanError, match="lower"):
        approach(state, clearance_machine_z_mm=-11)
    with pytest.raises(RecoveryPlanError, match="lower"):
        approach(state, current_machine_z_mm=-1)
    with pytest.raises(RecoveryPlanError, match="lower"):
        approach(boundary("G1 X1 Z20 F600"))


def test_missing_feed_cannot_descend_but_exact_pose_needs_no_feed_motion():
    state = boundary()
    assert approach(state)
    with pytest.raises(RecoveryPlanError, match="feed"):
        approach(state, current_work_mm=(1, 2, 3))


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_nonfinite_or_boolean_clearance_refused(value):
    with pytest.raises(RecoveryPlanError, match="finite"):
        approach(boundary("G1 F600"), clearance_machine_z_mm=value)


@pytest.mark.parametrize(
    "plane, arc, expected",
    [
        ("G17", "G2 X1 Y1 I1 J0 F600", (1, 1, 5)),
        ("G18", "G3 X1 Z6 I1 K0 F600", (1, 0, 6)),
        ("G19", "G2 Y1 Z6 J1 K0 F600", (0, 1, 6)),
    ],
)
def test_ijk_arc_endpoints_preserve_plane_and_modal_motion(plane, arc, expected):
    state = boundary(plane, arc)
    assert state.position_mm == expected
    assert state.plane == plane
    commands = approach(state)
    assert f"{plane} G40 G94" in commands
    assert commands[-1] == arc.split()[0]


def test_arc_full_circle_and_helical_endpoint_require_valid_center():
    state = boundary("G2 I1 J0 Z4 F600")
    assert state.position_mm == (0, 0, 4)
    assert boundary("G2 I1 J0 F600").position_mm == (0, 0, 5)
    for arc in ("G2 X1 R1 F600", "G2 X1 I0 J0 F600", "G2 X4 I1 F600", "G18 G2 X1 Z6 J1 F600", "G90.1", "G91.1"):
        with pytest.raises(RecoveryPlanError):
            boundary(arc)


def test_rapid_feed_does_not_overwrite_modal_cutting_feed():
    state = boundary("G1 F600", "G0 X1 F3000")
    assert state.feed_mm_min == 600
    assert "G1 F600.000000" in approach(state)


@pytest.mark.parametrize(
    "word", ["G1 X1 G20", "G2 X1 Y1 I1 J0 G18", "G1 X1 (G91)", "G1 X1; G91", "G1 X1 (note) Y2", "g1 x1", "G20 F10"]
)
def test_firmware_lexical_and_dispatch_ambiguities_are_refused(word):
    with pytest.raises(RecoveryPlanError):
        boundary(word)


def test_same_line_units_and_distance_before_motion_are_supported():
    state = boundary("G20 G91 G1 X0.1 Y0.2 Z-0.1 F10")
    assert state.position_mm == pytest.approx((2.54, 5.08, 2.46))
    assert state.feed_mm_min == 254


@pytest.mark.parametrize(
    "change",
    [
        {"position_mm": (0, 0, float("nan"))},
        {"feed_mm_min": -1},
        {"wcs_index": True},
        {"tool": True},
        {"motion": "G80"},
        {"spindle": "M3", "spindle_rpm": None},
    ],
)
def test_immutable_state_constructor_cannot_bypass_numeric_and_modal_checks(change):
    from dataclasses import replace

    with pytest.raises(RecoveryPlanError):
        replace(boundary("G1 F600"), **change)


def test_toolless_program_cannot_assume_a_mounted_probe_is_the_cutting_tool():
    lines = ["G21 G90 G17 G94 G54", "M3 S12000 M9", "G0 X0 Y0 Z5", "G1 X1 F600", "G1 X2"]
    state = reconstruct_recovery(lines, 5)
    assert state.tool is None
    with pytest.raises(RecoveryPlanError, match="active tool"):
        approach(state, verified_tool=999999)


def test_g53_clearance_then_work_anchor_preserves_selected_g55():
    state = boundary("G55", "G53 G0 Z-1", "G0 X1 Y2 Z3", "G1 F600")
    assert state.wcs_index == 1 and state.position_mm == (1, 2, 3)


def test_g53_z_invalidates_only_z_until_absolute_work_z_reanchors():
    state = boundary("G53 G0 Z-1", "G0 Z3", "G1 F600")
    assert state.wcs_index == 0 and state.position_mm == (0, 0, 3)
    with pytest.raises(RecoveryPlanError, match="all three"):
        boundary("G53 G0 Z-1")


def test_machine_xy_cannot_invent_unknown_work_transform_or_rotation():
    for extra in (("G53 G0 X-1 Y-2", "G0 X1"), ("G53 G0 X-1", "G0 X1"), ("G53 G0 X-1", "G53 G0 Y-2", "G0 X1")):
        with pytest.raises(RecoveryPlanError, match="all three"):
            boundary(*extra)
    assert boundary("G53 G0 X-1", "G0 X1 Y2", "G1 F600").position_mm == (1, 2, 5)


def test_g53_machine_target_is_absolute_even_under_g91_and_inch_mode():
    state = boundary("G20 G91", "G53 G0 Z-0.1", "G21 G90 G0 Z3", "G1 F600")
    assert state.position_mm == (0, 0, 3) and state.distance == "G90" and state.units == "G21"
    with pytest.raises(RecoveryPlanError, match="anchor"):
        boundary("G91", "G53 G0 Z-1", "G1 Z1 F600")


@pytest.mark.parametrize("word", ["G53 G2 X1 I1 J0", "G53 G0 X1 I1", "G53 Z-1", "G0 G53 Z-1"])
def test_ambiguous_or_arc_machine_moves_are_refused(word):
    with pytest.raises(RecoveryPlanError):
        boundary(word)


def test_g53_before_wcs_selection_can_be_followed_by_complete_work_anchor():
    lines = ["G21 G90 G17 G94", "G53 G0 Z-1", "G55", "T2 M6", "M3 S12000 M9", "G0 X1 Y2 Z3", "G1 F600", "G1 X2"]
    state = reconstruct_recovery(lines, 8)
    assert state.wcs_index == 1 and state.position_mm == (1, 2, 3)


def test_linear_boundary_cannot_assume_startup_plane_for_later_arcs():
    # An earlier job or MDI could have selected G18; position telemetry does
    # not reveal that mode. Even a linear boundary cannot restore guessed G17.
    lines = program("G1 X1 F600")
    lines[0] = lines[0].replace(" G17", "")
    lines[-1] = "G2 X2 Z4 I1 K0 F600"
    with pytest.raises(RecoveryPlanError, match="explicit G17/G18/G19 plane"):
        reconstruct_recovery(lines, len(lines))


def test_later_plane_declaration_cannot_qualify_an_earlier_arc():
    lines = program("G2 X1 Y1 I1 J0 F600", "G17")
    lines[0] = lines[0].replace(" G17", "")
    with pytest.raises(RecoveryPlanError, match="arc has no explicitly established plane"):
        reconstruct_recovery(lines, len(lines))


def test_rapid_boundary_cannot_assume_previous_inverse_time_mode_is_clear():
    lines = program()
    lines[0] = lines[0].replace(" G94", "")
    with pytest.raises(RecoveryPlanError, match="explicit G94 feed mode"):
        reconstruct_recovery(lines, len(lines))


@pytest.mark.parametrize("cut", ["F600", "G1 X1", "G2 X1 Y1 I1 J0"])
def test_later_g94_cannot_qualify_prior_unknown_cutting_feed_or_motion(cut):
    lines = program(cut, "G94")
    lines[0] = lines[0].replace(" G94", "")
    with pytest.raises(RecoveryPlanError, match="no explicit G94 mode"):
        reconstruct_recovery(lines, len(lines))


def test_standalone_f_after_rapid_sets_cutting_feed_and_g1_modal_motion():
    state = boundary("G0 X1 F3000", "F275", "X2")
    assert state.feed_mm_min == 275 and state.motion == "G1"
    assert state.position_mm == (2, 0, 5)
    assert "G1 F275.000000" in approach(state)


def test_standalone_feed_update_and_rapid_feed_remain_distinct():
    state = boundary("G1 F600", "G0 X1 F3000", "F275", "G0 X2 F4000", "G1 X3")
    assert state.feed_mm_min == 275 and state.motion == "G1"
    assert state.position_mm == (3, 0, 5)


def test_f_leading_line_with_axes_is_implicit_g1_but_axis_leading_keeps_g0():
    assert boundary("F275 X1").motion == "G1"
    assert boundary("F275 X1").feed_mm_min == 275
    assert boundary("G1 F600", "G0 X1", "X2 F275").feed_mm_min == 600
    for line in ("F275 G0 X1", "N10 F275"):
        with pytest.raises(RecoveryPlanError):
            boundary(line)
