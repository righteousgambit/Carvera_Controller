"""Worker-prepared array surfaces; GPU instructions remain on the UI thread."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.machine.repeat_parts import RepeatPartPlan, plan_revision, repeat_stock_geometry


@dataclass(frozen=True, eq=False)
class RepeatStockDisplay(Mapping[str, GeometrySnapshot]):
    stocks: Mapping[str, GeometrySnapshot]
    revision: str | None
    selected_index: int
    scale: float
    solids: GeometrySnapshot
    edges: GeometrySnapshot

    def __getitem__(self, key: str) -> GeometrySnapshot:
        return self.stocks[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.stocks)

    def __len__(self) -> int:
        return len(self.stocks)

    def matches(self, plan: RepeatPartPlan, selected_index: int) -> bool:
        return self.revision == plan_revision(plan) and self.selected_index == selected_index

    @classmethod
    def prepare(
        cls,
        plan: RepeatPartPlan,
        selected_index: int,
        stocks: Mapping[str, GeometrySnapshot],
        scale: float,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> RepeatStockDisplay:
        if set(stocks) != {part.wcs for part in plan.parts} or any(
            not isinstance(mesh, GeometrySnapshot) for mesh in stocks.values()
        ):
            raise ValueError("Array display requires a complete immutable result")
        if isinstance(stocks, cls) and stocks.matches(plan, selected_index) and stocks.scale == scale:
            if cancelled is not None and cancelled():
                raise InterruptedError("Array display preparation cancelled")
            return stocks
        if any(part.stock_source is not None for part in plan.parts):
            if (
                plan.prepared_index != selected_index
                or plan.prepared_revision != plan_revision(plan)
                or plan.nominal_geometry is None
            ):
                plan = plan.prepared(scale=scale, selected_index=selected_index, cancelled=cancelled)
        # A new selection owns only its own combined buffers. Do not cache all
        # six possible copies of a large array or retain a chain of prior views.
        captured = MappingProxyType(dict(stocks))
        solids, edges = repeat_stock_geometry(plan, selected_index, captured, cancelled=cancelled)
        solid = GeometrySnapshot(solids.vertices, solids.indices, cancelled=cancelled)
        edge = GeometrySnapshot(edges.vertices, edges.indices, cancelled=cancelled)
        offset = plan.parts[selected_index].work_offset_mm
        captured[plan.parts[selected_index].wcs].render_batches(offset, scale, cancelled=cancelled)
        solid.render_batches(offset, scale, cancelled=cancelled)
        edge.render_line_batches(offset, scale, cancelled=cancelled)
        return cls(captured, plan_revision(plan), selected_index, scale, solid, edge)
