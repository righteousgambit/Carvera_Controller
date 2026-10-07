import pytest

from carveracontroller.machine.joint_feedback import review_joint_feedback


def trace(times=(0, 1, 3, 6), function=lambda t: t * t, commands=True):
    return {
        "source": "Test encoder trace",
        "timing_source": "Block-relative recorded timestamps",
        "samples": [
            {
                "seconds": t,
                "reported": {"axis": function(t)},
                **({"commanded": {"axis": function(t) - 0.25}} if commands else {}),
            }
            for t in times
        ],
    }


def review(record=None, **kwargs):
    return review_joint_feedback(record or trace(), 6, (("axis", "linear"),), **kwargs)


def test_nonuniform_quadratic_feedback_retains_timing_and_paired_error():
    result = review()
    axis = result.demands[0]
    assert axis.maximum_velocity == 9
    assert axis.maximum_acceleration == 2
    assert axis.maximum_jerk == 0
    assert axis.maximum_following_error == 0.25
    assert axis.reversals == 0
    assert result.maximum_gap_seconds == 3
    assert result.source == "Test encoder trace"


def test_cubic_trace_has_correct_third_difference():
    result = review_joint_feedback(trace((0, 1, 2, 3), lambda t: t**3), 3, (("axis", "rotary"),))
    assert result.demands[0].maximum_jerk == 6
    assert result.demands[0].maximum_acceleration == 12


def test_two_samples_do_not_invent_acceleration_jerk_or_command_error():
    result = review(trace((0, 6), commands=False)).demands[0]
    assert result.maximum_velocity == 6
    assert result.maximum_acceleration is None
    assert result.maximum_jerk is None
    assert result.maximum_following_error is None


def test_unwrapped_rotary_and_reversal_through_stop_are_retained():
    values = {0: 350, 1: 10, 2: 10, 3: 20}
    result = review_joint_feedback(trace((0, 1, 2, 3), values.__getitem__, False), 3, (("axis", "rotary"),)).demands[0]
    assert result.maximum_velocity == 340
    assert result.reversals == 1


@pytest.mark.parametrize(
    "mutation",
    ["boolean", "nan", "missing", "extra", "duplicate_time", "partial", "command_gap", "missing_source", "overflow"],
)
def test_invalid_trace_withholds_report(mutation):
    data = trace()
    if mutation == "boolean":
        data["samples"][1]["reported"]["axis"] = True
    elif mutation == "nan":
        data["samples"][1]["seconds"] = float("nan")
    elif mutation == "missing":
        data["samples"][1]["reported"] = {}
    elif mutation == "extra":
        data["samples"][1]["reported"]["other"] = 4
    elif mutation == "duplicate_time":
        data["samples"][1]["seconds"] = 0
    elif mutation == "partial":
        data["samples"][-1]["seconds"] = 5
    elif mutation == "command_gap":
        del data["samples"][1]["commanded"]
    elif mutation == "missing_source":
        data["timing_source"] = ""
    else:
        data["samples"][0]["reported"]["axis"] = -1e308
        data["samples"][1]["reported"]["axis"] = 1e308
    with pytest.raises(ValueError):
        review(data)


def test_cancellation_and_trace_bounds():
    with pytest.raises(InterruptedError):
        review(cancelled=lambda: True)
    data = trace()
    data["samples"] *= 501
    with pytest.raises(ValueError, match="2001"):
        review(data)
