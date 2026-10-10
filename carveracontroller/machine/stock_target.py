"""Detached actual-part target occupancy and complete-grid remaining-material comparison."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import prod
from types import MappingProxyType
from typing import Any, Literal, cast

from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.addons.manufacturing_simulation.stock_mesh import StockMeshInput
from carveracontroller.addons.manufacturing_simulation.stock_solid import StockSolid
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.program_stock_inspection import StockMoveState, StockSection, section_from_state
from carveracontroller.machine.stock_finishing import FinishingComparison


@dataclass(frozen=True)
class StockTarget:
    bindings: tuple[object, object, object]
    stock: str
    source_path: str
    source_sha256: str
    source_units: str
    translation_mm: tuple[float, float, float]
    solid_volume_mm3: float
    target: Mapping[str, Any]
    initial: Mapping[str, Any]


@dataclass(frozen=True)
class TargetFit:
    material_mm3: float
    retained_target_mm3: float
    excess_mm3: float
    missing_mm3: float
    excess: Mapping[str, Any]
    missing: Mapping[str, Any]


@dataclass(frozen=True)
class TargetAnalysis:
    target: StockTarget
    segment_index: int
    line: int
    target_grid_mm3: float
    fits: Mapping[str, TargetFit]
    newly_missing_mm3: Mapping[str, float]
    cell_work: int
    qualification: str = (
        "Declared closed STL target in the stock's grid frame, before stock rotation/tilt/WCS placement. "
        "Complete center-classified grid comparison; target boundaries can cross cells. "
        "Missing target centers are potential overcut or insufficient stock, not a measured gouge. "
        "No normal-distance allowance, cutter reach, forces, machine/fixture/ATC clearance or physical qualification."
    )


def prepare_stock_target(
    state: StockMoveState,
    stock_name: str,
    path: str,
    *,
    units: Literal["mm", "inch"],
    translation_mm: tuple[float, float, float] = (0, 0, 0),
    cancelled: Callable[[], bool] = lambda: False,
) -> StockTarget:
    if stock_name not in state.after:
        raise ValueError("Choose a stock instance from the retained review")
    evolution = cast(StockEvolution, state.bindings[1])
    # A state is produced only by reconstruct_stock_move. The initial declared
    # snapshot is distinct from after-stock, so pre-existing missing stock stays visible.
    initial = evolution.inputs.stocks[stock_name][1]
    grid = StockVolume.from_snapshot(initial, cancelled=cancelled)
    mesh = StockMeshInput.load(path, units=units, cancelled=cancelled)
    solid = StockSolid.validate(mesh, cancelled=cancelled)
    target = solid.voxelize_grid(grid, translation_mm=translation_mm, cancelled=cancelled)
    return StockTarget(
        state.bindings,
        stock_name,
        mesh.source_path,
        mesh.source_sha256,
        mesh.source_units,
        (float(translation_mm[0]), float(translation_mm[1]), float(translation_mm[2])),
        solid.material_volume_mm3,
        MappingProxyType(target.snapshot(cancelled=cancelled)),
        initial,
    )


def _same_grid(left: StockVolume, right: StockVolume) -> bool:
    return (
        left.grid_bounds == right.grid_bounds
        and left.shape == right.shape
        and left.resolution_mm == right.resolution_mm
        and left.pivot == right.pivot
        and left.orientation == right.orientation
    )


def analyze_stock_target(
    target: StockTarget,
    state: StockMoveState,
    comparison: FinishingComparison | None = None,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = 8_000_000,
) -> TargetAnalysis:
    if any(a is not b for a, b in zip(target.bindings, state.bindings)) or target.stock not in state.after:
        raise ValueError("Target belongs to a different retained stock review")
    evolution = cast(StockEvolution, state.bindings[1])
    if target.initial != evolution.inputs.stocks[target.stock][1]:
        raise ValueError("Target initial stock differs from the retained review")
    if type(max_cell_work) is not int or not 1 <= max_cell_work <= 8_000_000:
        raise ValueError("Target comparison exceeds bounded cell-work contract")
    snapshots = {"Initial stock": target.initial, "After selected move": state.after[target.stock]}
    if comparison is not None:
        if (
            comparison.stock != target.stock
            or comparison.after_segment != state.segment_index
            or any(a is not b for a, b in zip(comparison.bindings, state.bindings))
        ):
            raise ValueError("Finishing comparison belongs to a different retained move or stock")
        snapshots.update(
            {
                "Planned continuation": comparison.planned.final,
                f"T{comparison.candidate_tool} continuation": comparison.candidate.final,
            }
        )
    model = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    work = prod(model.shape) * len(snapshots)
    if work > max_cell_work:
        raise ValueError("Target comparison exhausted complete shared cell-work budget; no partial result")
    fits: dict[str, TargetFit] = {}
    for label, snapshot in snapshots.items():
        stock = StockVolume.from_snapshot(snapshot, cancelled=cancelled)
        if not _same_grid(model, stock):
            raise ValueError("Target and remaining stock grids differ; no resampling or clipping")
        excess, missing = model.clone(cancelled=cancelled), model.clone(cancelled=cancelled)
        excess_count = missing_count = retained_count = 0
        for z in range(model.shape[2]):
            for y in range(model.shape[1]):
                for x in range(model.shape[0]):
                    at = model._index(x, y, z)
                    if at % 128 == 0 and cancelled():
                        raise InterruptedError("Part target comparison cancelled; previous result retained")
                    want, has = model.occupied(x, y, z), stock.occupied(x, y, z)
                    extra, lost = has and not want, want and not has
                    excess._occupied[at], missing._occupied[at] = int(extra), int(lost)
                    excess_count += extra
                    missing_count += lost
                    retained_count += want and has
        for grid, count in ((excess, excess_count), (missing, missing_count)):
            grid._remaining_count = grid._initial_count = count
        fits[label] = TargetFit(
            stock.remaining_volume_mm3,
            retained_count * model.cell_volume_mm3,
            excess.remaining_volume_mm3,
            missing.remaining_volume_mm3,
            MappingProxyType(excess.snapshot(cancelled=cancelled)),
            MappingProxyType(missing.snapshot(cancelled=cancelled)),
        )
    if cancelled():
        raise InterruptedError("Part target comparison cancelled; previous result retained")
    baseline = fits["Initial stock"].missing_mm3
    return TargetAnalysis(
        target,
        state.segment_index,
        state.line,
        model.remaining_volume_mm3,
        MappingProxyType(fits),
        MappingProxyType({label: fit.missing_mm3 - baseline for label, fit in fits.items()}),
        work,
    )


def target_sections(
    analysis: TargetAnalysis,
    label: str,
    plane: str = "XY",
    layer: int | None = None,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[StockSection, StockSection, StockSection]:
    if label not in analysis.fits:
        raise ValueError("Choose a retained target comparison state")
    fit = analysis.fits[label]
    output = []
    for snapshot in (analysis.target.target, fit.excess, fit.missing):
        snapshots = MappingProxyType({analysis.target.stock: snapshot})
        state = StockMoveState(
            analysis.target.bindings, analysis.segment_index, analysis.line, 0, snapshots, snapshots, analysis.cell_work
        )
        output.append(section_from_state(state, analysis.target.stock, plane, layer, cancelled=cancelled))
    return output[0], output[1], output[2]
