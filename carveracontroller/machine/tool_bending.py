"""Declared uniform circular cantilever comparison; no cutting-force inference."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CantileverEstimate:
    diameter_mm: float
    overhang_mm: float
    force_n: float
    modulus_mpa: float
    compliance_mm_per_n: float
    displacement_mm: float
    root_stress_mpa: float
    tip_slope_rad: float
    limitations: tuple[str, ...]


def estimate_cantilever(
    diameter_mm: float, overhang_mm: float, force_n: float, modulus_mpa: float
) -> CantileverEstimate:
    """Euler-Bernoulli solid-round beam, fixed root, transverse tip point load.

    Units N and mm give E and stress in MPa. This is a declared sensitivity
    model, not a fluted cutter/holder model or proof of machining tolerance.
    """
    for name, value, minimum, maximum in (
        ("Equivalent diameter", diameter_mm, 0.001, 10000),
        ("Unsupported length", overhang_mm, 0.001, 10000),
        ("Transverse force", force_n, 0, 1e9),
        ("Elastic modulus", modulus_mpa, 0.001, 1e9),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    inertia = math.pi * diameter_mm**4 / 64
    compliance = overhang_mm**3 / (3 * modulus_mpa * inertia)
    displacement = force_n * compliance
    limitations = []
    if overhang_mm / diameter_mm < 3:
        limitations.append("Short beam: shear deformation is omitted and may be significant.")
    if displacement / overhang_mm > 0.01:
        limitations.append("Deflection exceeds 1% of length: small-deflection assumptions need review.")
    return CantileverEstimate(
        diameter_mm,
        overhang_mm,
        force_n,
        modulus_mpa,
        compliance,
        displacement,
        force_n * overhang_mm * diameter_mm / (2 * inertia),
        force_n * overhang_mm**2 / (2 * modulus_mpa * inertia),
        tuple(limitations),
    )
