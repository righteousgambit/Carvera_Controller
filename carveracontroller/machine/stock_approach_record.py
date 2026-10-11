"""Complete route evidence with shared group members and per-leg source wrappers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from carveracontroller.machine.program_surface_archive import exact_record, mesh_record
from carveracontroller.machine.stock_approach_clearance import ApproachClearance


def approach_record(result: ApproachClearance, *, cancelled: Callable[[], bool]) -> dict[str, Any]:
    scene = result.scene
    if len(scene.body_review.segments) != 3 or result.material is None or result.start_evidence is None:
        raise ValueError("Route archive requires complete retract, traverse and insertion context")
    if any(
        len(getattr(scene, name)) > cap
        for name, cap in (
            ("contacts", 30_000),
            ("groups", 30_000),
            ("occupancy", 300_000),
            ("rotating", 100_000),
            ("gaps", 30_000),
        )
    ):
        raise ValueError("Complete three-leg route exceeds bounded logical result storage")
    pool, wrappers, identities = [], [], {}
    members = 0
    for index, row in enumerate(scene.groups):
        if index % 64 == 0 and cancelled():
            raise InterruptedError("Route evidence capture cancelled")
        key = id(row.group)
        if key not in identities:
            members += len(row.group.triangle_pairs)
            if len(pool) >= 10_000 or members > 100_000:
                raise ValueError("Route evidence exceeds unique complete group storage")
            identities[key] = len(pool)
            pool.append(exact_record(asdict(row.group)))
        wrappers.append(
            {
                **{
                    name: exact_record(getattr(row, name))
                    for name in (
                        "segment_index",
                        "line",
                        "tool",
                        "first",
                        "second",
                        "source_lower_ratio",
                        "source_upper_ratio",
                    )
                },
                "group": identities[key],
            }
        )
    rows = {}
    for name in ("contacts", "occupancy", "rotating", "gaps"):
        captured = []
        for index, row in enumerate(getattr(scene, name)):
            if index % 64 == 0 and cancelled():
                raise InterruptedError("Route evidence capture cancelled")
            captured.append(exact_record(asdict(row)))
        rows[name] = captured
    inspection = result.inspection
    if inspection.approach is None:
        raise ValueError("Complete route lost its original tool inspection")
    analysis = inspection.analysis
    legs = []
    for leg in result.material.legs:
        if cancelled():
            raise InterruptedError("Route material evidence capture cancelled")
        material_row = {
            name: getattr(leg, name) for name in ("index", "label", "start_program_mm", "end_program_mm", "cutting")
        }
        for name in ("target_contacts", "stock_contacts"):
            records = []
            for index, contact in enumerate(getattr(leg, name)):
                if index % 64 == 0 and cancelled():
                    raise InterruptedError("Route material evidence capture cancelled")
                records.append(exact_record(asdict(contact)))
            material_row[name] = records
        legs.append(material_row)
    if cancelled():
        raise InterruptedError("Route evidence capture cancelled")
    return {
        "proposal_sha256": result.proposal_sha256,
        "waypoints_mm": result.waypoints_mm,
        "leg_labels": result.leg_labels,
        "included_bodies": result.included_bodies,
        "replaced_initial_stock": result.replaced_initial_stock,
        "qualification": result.qualification,
        "scene": {
            **rows,
            "group_pool": pool,
            "group_wrappers": wrappers,
            "geometry_sha256": mesh_record(scene, cancelled=cancelled)["sha256"],
            **{
                name: getattr(scene, name)
                for name in (
                    "refined_pairs",
                    "nodes",
                    "triangle_pairs",
                    "triangles",
                    "solid_counts",
                    "qualification",
                    "contact_mode",
                    "group_counts",
                    "rigid_reused_pairs",
                )
            },
        },
        "inspection": {
            **{
                name: exact_record(getattr(inspection, name))
                for name in (
                    "label",
                    "cell",
                    "category",
                    "center_grid_mm",
                    "center_program_mm",
                    "signed_distance_mm",
                    "cell_distance_interval_mm",
                    "half_diagonal_mm",
                    "distance_nodes",
                    "distance_faces",
                    "qualification",
                )
            },
            "nearest": exact_record(asdict(inspection.nearest)),
            "approach": exact_record(asdict(inspection.approach)),
        },
        "target_analysis": {
            "segment_index": analysis.segment_index,
            "line": analysis.line,
            "target_grid_mm3": analysis.target_grid_mm3,
            "cell_work": analysis.cell_work,
            "newly_missing_mm3": dict(analysis.newly_missing_mm3),
            "qualification": analysis.qualification,
            "target_source_sha256": analysis.target.source_sha256,
            "fits": {
                label: {
                    "material_mm3": fit.material_mm3,
                    "retained_target_mm3": fit.retained_target_mm3,
                    "excess_mm3": fit.excess_mm3,
                    "missing_mm3": fit.missing_mm3,
                    "excess": dict(fit.excess),
                    "missing": dict(fit.missing),
                }
                for label, fit in analysis.fits.items()
            },
        },
        "material": {
            "legs": legs,
            **{
                name: getattr(result.material, name)
                for name in ("nodes", "face_queries", "declared_cell_work_bound", "coverage", "qualification")
            },
            "target_triangles": result.material.target_mesh.triangles,
        },
    }
