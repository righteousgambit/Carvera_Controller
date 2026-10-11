"""Admission diagnostics distinguish known validation from untrusted errors."""

import json

import pytest

from carveracontroller.headless.job_admission_receipts import admission_refusal


def test_retains_owned_refusal_and_distinguishes_the_two_host_receipt_ages():
    reason = "The probe-settings workflow owns an unfinished transaction"
    result = admission_refusal(
        ValueError(reason),
        {"last_machine_snapshot_age_s": 0.5, "last_machine_snapshot": {"status_age_ms": 400}},
    )
    assert result["reason"] == reason
    assert result["error_type"] == "ValueError"
    assert result["cached_snapshot_age_s"] == 0.5
    assert result["child_status_age_s"] == 0.4
    assert result["combined_report_age_s"] == 0.9
    assert "not firmware sample age" in result["timing_source"]


@pytest.mark.parametrize("error_class", [ValueError, RuntimeError])
def test_does_not_retain_freeform_error_or_private_context(error_class):
    result = admission_refusal(
        error_class("sensitive exception detail"),
        {"private": "sensitive context", "last_machine_snapshot": {"private": "sensitive snapshot"}},
    )
    assert result["reason"] == "Final UI admission refused; inspect the retained context and current state"
    assert "sensitive" not in json.dumps(result)
    assert result["combined_report_age_s"] is None


@pytest.mark.parametrize("bad", [None, True, False, -1, float("inf"), float("nan"), "0.1"])
def test_unknown_or_invalid_ages_stay_unknown_and_json_remains_finite(bad):
    result = admission_refusal(
        ValueError("Run context retired before submission"),
        {"last_machine_snapshot_age_s": bad, "last_machine_snapshot": {"status_age_ms": bad}},
    )
    assert result["cached_snapshot_age_s"] is None
    assert result["child_status_age_s"] is None
    assert result["combined_report_age_s"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("state", [None, {"last_machine_snapshot": []}, {"last_machine_snapshot_age_s": 0.2}])
def test_partial_context_does_not_invent_complete_report_age(state):
    result = admission_refusal(ValueError("Run context retired before submission"), state)
    assert result["child_status_age_s"] is None
    assert result["combined_report_age_s"] is None
