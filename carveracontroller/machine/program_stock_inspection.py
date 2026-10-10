"""Reconstruct a retained move and inspect complete stock-local cell sections."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance
from carveracontroller.machine.program_stock_evolution import (
    MAX_CELL_WORK,
    StockEvolution,
    StockEvolutionInput,
    review_stock_evolution,
)

Rectangle = tuple[float, float, float, float]
PLANES = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}


@dataclass(frozen=True)
class StockSection:
    stock: str
    segment_index: int
    line: int
    tool: int
    plane: str
    layer: int
    layers: int
    coordinate_mm: float
    bounds: Rectangle
    remaining: tuple[Rectangle, ...]
    removed: tuple[Rectangle, ...]
    before_mm3: float
    after_mm3: float
    cell_work: int


def inspect_stock_section(
    body: ProgramBodyClearance,
    evolution: StockEvolution,
    envelopes: Mapping[int, Mapping[str, Sequence[AxialEnvelope]]],
    stock_name: str,
    segment_index: int,
    plane: str = "XY",
    layer: int | None = None,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = MAX_CELL_WORK,
    max_rectangles: int = 8192,
) -> StockSection:
    """Replay the prefix once, then one move; refuse incomplete or mismatched history.

    No per-move full grids are retained in the report. Both replays share the
    original work ceiling. Sections merge only equal runs of classified cells;
    a budget refusal never returns a truncated or decimated section.
    """
    if (
        type(segment_index) is not int
        or not 0 <= segment_index < len(body.segments)
        or stock_name not in evolution.inputs.stocks
        or plane not in PLANES
        or (layer is not None and type(layer) is not int)
        or type(max_rectangles) is not int
        or not 1 <= max_rectangles <= 8192
    ):
        raise ValueError("Choose a retained stock, resolved move and valid section plane/layer")
    stocks_count = len(evolution.inputs.stocks)
    if len(evolution.steps) != len(body.segments) * stocks_count:
        raise ValueError("Stock inspection requires complete ordered move/stock history")
    before = review_stock_evolution(
        replace(body, segments=body.segments[:segment_index]),
        evolution.inputs,
        envelopes,
        cancelled=cancelled,
        max_cell_work=max_cell_work,
    )
    if before.steps != evolution.steps[: segment_index * stocks_count]:
        raise ValueError("Reconstructed stock prefix differs from retained history")
    remaining_work = max_cell_work - before.cell_work
    if remaining_work < 1:
        raise ValueError("Stock inspection exhausted shared work budget; previous section retained")
    inputs = StockEvolutionInput(
        MappingProxyType(
            {name: (offset, before.final_snapshots[name]) for name, (offset, _) in evolution.inputs.stocks.items()}
        ),
        evolution.inputs.tools,
    )
    after = review_stock_evolution(
        replace(body, segments=(body.segments[segment_index],)),
        inputs,
        envelopes,
        cancelled=cancelled,
        max_cell_work=remaining_work,
    )
    normalized = tuple(replace(s, segment_index=segment_index) for s in after.steps)
    if normalized != evolution.steps[segment_index * stocks_count : (segment_index + 1) * stocks_count]:
        raise ValueError("Reconstructed stock move differs from retained history")
    if segment_index == len(body.segments) - 1 and after.final_snapshots != evolution.final_snapshots:
        raise ValueError("Reconstructed final cells differ from retained stock")
    original = StockVolume.from_snapshot(before.final_snapshots[stock_name], cancelled=cancelled)
    final = StockVolume.from_snapshot(after.final_snapshots[stock_name], cancelled=cancelled)
    u, v, normal = PLANES[plane]
    selected_layer = original.shape[normal] // 2 if layer is None else layer
    if not 0 <= selected_layer < original.shape[normal]:
        raise ValueError(f"Section layer must be 0..{original.shape[normal] - 1}")
    low, high = original.grid_bounds.minimum.tuple, original.grid_bounds.maximum.tuple
    size = original.cell_size.tuple
    rectangles: list[list[Rectangle]] = [[], []]
    active: dict[tuple[int, int, int], int] = {}
    for row in range(original.shape[v]):
        if cancelled():
            raise InterruptedError("Stock section cancelled; previous section retained")
        next_active = {}
        column = 0
        while column < original.shape[u]:
            if column % 128 == 0 and cancelled():
                raise InterruptedError("Stock section cancelled; previous section retained")
            point = [0, 0, 0]
            point[normal], point[v], point[u] = selected_layer, row, column
            had, has = original.occupied(*point), final.occupied(*point)
            if has and not had:
                raise ValueError("Stock reconstruction added material; section withheld")
            category = 0 if has else 1 if had else -1
            start = column
            column += 1
            while column < original.shape[u]:
                if column % 128 == 0 and cancelled():
                    raise InterruptedError("Stock section cancelled; previous section retained")
                point[u] = column
                had, has = original.occupied(*point), final.occupied(*point)
                if has and not had:
                    raise ValueError("Stock reconstruction added material; section withheld")
                if (0 if has else 1 if had else -1) != category:
                    break
                column += 1
            if category < 0:
                continue
            key = (category, start, column)
            rect = (
                low[u] + start * size[u],
                low[v] + row * size[v],
                low[u] + column * size[u],
                low[v] + (row + 1) * size[v],
            )
            if key in active:
                at = active[key]
                previous = rectangles[category][at]
                rectangles[category][at] = (previous[0], previous[1], previous[2], rect[3])
            else:
                if sum(map(len, rectangles)) >= max_rectangles:
                    raise ValueError("Stock section exceeds complete rectangle budget; previous section retained")
                at = len(rectangles[category])
                rectangles[category].append(rect)
            next_active[key] = at
        active = next_active
    if cancelled():
        raise InterruptedError("Stock section cancelled; previous section retained")
    segment = body.segments[segment_index]
    return StockSection(
        stock_name,
        segment_index,
        segment.line,
        int(segment.tool_id),
        plane,
        selected_layer,
        original.shape[normal],
        low[normal] + (selected_layer + 0.5) * size[normal],
        (low[u], low[v], high[u], high[v]),
        tuple(rectangles[0]),
        tuple(rectangles[1]),
        original.remaining_volume_mm3,
        final.remaining_volume_mm3,
        before.cell_work + after.cell_work,
    )
