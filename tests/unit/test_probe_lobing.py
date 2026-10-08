"""Tests for probe lobing characterisation."""

import math

import pytest

from carveracontroller.machine.probe_lobing import (
    FeatureType,
    LobingQuality,
    LobingSample,
    build_lobing_map,
    summarise,
)

_KNOWN = 25.000
_TIP = 1.600


def _tri_lobe(amplitude_mm, step=60):
    """Samples from a probe with three-fold periodic pre-travel."""
    return [
        LobingSample(angle, _KNOWN - (_TIP + amplitude_mm * math.cos(math.radians(3 * angle))))
        for angle in range(0, 360, step)
    ]


def test_bore_derivation_matches_the_firmware():
    """M460 computes `known - measured` for a bore (ZProbe.cpp:2364)."""
    samples = [LobingSample(0.0, _KNOWN - _TIP)]
    result = build_lobing_map(_KNOWN, samples, FeatureType.BORE)

    assert result.effective_tip_diameter == pytest.approx(_TIP)


def test_boss_derivation_flips_the_sign():
    """For a boss it is `measured - known` (ZProbe.cpp:2423)."""
    samples = [LobingSample(0.0, _KNOWN + _TIP)]
    result = build_lobing_map(_KNOWN, samples, FeatureType.BOSS)

    assert result.effective_tip_diameter == pytest.approx(_TIP)


def test_a_perfect_probe_shows_no_lobing():
    samples = [LobingSample(a, _KNOWN - _TIP) for a in range(0, 360, 45)]
    result = build_lobing_map(_KNOWN, samples)

    assert result.lobing_amplitude == pytest.approx(0.0)
    assert result.quality is LobingQuality.NEGLIGIBLE


def test_amplitude_is_peak_to_peak_not_deviation_from_mean():
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012))

    assert result.lobing_amplitude == pytest.approx(0.024, abs=1e-6)


def test_mean_survives_lobing():
    """Averaging across directions is exactly what makes the mean usable."""
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012))

    assert result.effective_tip_diameter == pytest.approx(_TIP, abs=1e-6)


def _exact_spread(peak_to_peak):
    """Two samples whose implied tip diameters differ by exactly this much.

    Constructed rather than derived from a cosine, so threshold boundaries
    can be tested without floating point turning 0.030 into 0.0299999.
    """
    return [
        LobingSample(0.0, _KNOWN - _TIP),
        LobingSample(180.0, _KNOWN - _TIP - peak_to_peak),
    ]


@pytest.mark.parametrize(
    ("peak_to_peak", "expected"),
    [
        (0.001, LobingQuality.NEGLIGIBLE),
        (0.0045, LobingQuality.NEGLIGIBLE),
        (0.0055, LobingQuality.MODERATE),
        (0.010, LobingQuality.MODERATE),
        (0.020, LobingQuality.MODERATE),
        (0.032, LobingQuality.SEVERE),
        (0.060, LobingQuality.SEVERE),
    ],
)
def test_quality_thresholds(peak_to_peak, expected):
    """Values sit either side of each threshold, never exactly on one.

    The amplitude is a difference of two numbers near 23.4, so it carries
    about a picometre of float noise -- 0.005 comes out as 0.00499999. Exact
    boundary behaviour is not a property worth asserting here.
    """
    result = build_lobing_map(_KNOWN, _exact_spread(peak_to_peak))

    assert result.lobing_amplitude == pytest.approx(peak_to_peak)
    assert result.quality is expected


def test_correction_is_zero_at_the_mean_crossing():
    """A three-lobe pattern crosses its mean midway between lobes."""
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012))
    assert result.correction_at(30.0) == pytest.approx(0.0, abs=1e-9)


def test_correction_is_extreme_on_a_lobe():
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012))
    assert result.correction_at(0.0) == pytest.approx(0.012, abs=1e-6)


def test_correction_wraps_past_the_last_sample():
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012))

    assert result.correction_at(350.0) == pytest.approx(result.correction_at(-10.0), abs=1e-9)
    assert result.correction_at(360.0) == pytest.approx(result.correction_at(0.0), abs=1e-9)


def test_correction_is_zero_with_a_single_sample():
    """One direction cannot describe a direction-dependent error."""
    result = build_lobing_map(_KNOWN, [LobingSample(0.0, _KNOWN - _TIP)])
    assert result.correction_at(123.0) == 0.0


def test_worst_and_best_angles_differ_under_lobing():
    """Sampled at 30 degrees so the pattern has intermediate values.

    A 60 degree step on a three-lobe probe lands only on the extremes, where
    every sample is equally far from the mean and the question is degenerate.
    """
    result = build_lobing_map(_KNOWN, _tri_lobe(0.012, step=30))

    assert result.worst_angle != result.best_angle
    assert abs(math.cos(math.radians(3 * result.worst_angle))) == pytest.approx(1.0)
    assert abs(math.cos(math.radians(3 * result.best_angle))) == pytest.approx(0.0, abs=1e-9)


def test_rejects_nonsense_input():
    with pytest.raises(ValueError):
        build_lobing_map(0.0, [LobingSample(0.0, 1.0)])
    with pytest.raises(ValueError):
        build_lobing_map(25.0, [])


def test_summary_gives_the_persistence_command():
    """The measured value is worthless until it is written to config."""
    text = summarise(build_lobing_map(_KNOWN, _tri_lobe(0.012)))

    assert "config-set sd zprobe.probe_tip_diameter" in text
    assert "1.6000" in text


def test_summary_advises_consistent_approach_when_lobing_matters():
    text = summarise(build_lobing_map(_KNOWN, _tri_lobe(0.008)))
    assert "consistent direction" in text


def test_summary_says_no_compensation_needed_when_lobing_is_tiny():
    text = summarise(build_lobing_map(_KNOWN, _tri_lobe(0.001)))
    assert "no compensation needed" in text.lower()


def test_summary_flags_a_probe_that_needs_mechanical_attention():
    text = summarise(build_lobing_map(_KNOWN, _tri_lobe(0.030)))
    assert "concentric" in text
