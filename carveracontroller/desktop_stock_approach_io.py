"""Background complete route save/open, kept detached from live machine state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.machine.calculation_progress import CalculationProgress
from carveracontroller.machine.stock_approach_archive import load_approach_review, save_approach_review


@dataclass(frozen=True)
class RouteExchangeContext:
    source: Any
    offsets: Any
    comparison: Any
    clearance_mm: float
    target_raw: bytes | None = None


def initialize_exchange(card: Any) -> None:
    card.exchange_context = None
    actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
    card.save_route = Action("Save route", lambda: save_route(card), disabled=True)
    card.open_route = Action("Open route", lambda: open_route(card))
    actions.add_widget(card.save_route)
    actions.add_widget(card.open_route)
    card.content.add_widget(actions)
    card.exchange_status = flowing_text(
        "Saved routes reopen as detached historical evidence; current machine state is preserved.", 40
    )
    card.content.add_widget(card.exchange_status)


def current_exchange_context(card: Any) -> RouteExchangeContext | None:
    inputs = card.allowance.target.sections.surfaces.review.retained_inputs
    if inputs is None:
        return None
    return RouteExchangeContext(
        inputs[0],
        dict(inputs[1]),
        card.allowance.target.sections.finishing.result,
        float(card.allowance.clearance.text),
    )


def begin_exchange(card: Any, title: str) -> CalculationProgress:
    card.stop_progress()
    card.progress = CalculationProgress(title)
    card.progress_target = card.exchange_status
    card.progress_event = Clock.schedule_interval(card.tick, 0.25)
    card.exchange_status.text = title
    return card.progress


def save_route(card: Any) -> None:
    owner, result, context = card.owner, card.result, card.exchange_context
    if owner.running or result is None or context is None or result.material is None:
        return
    generation = card.generation

    def current() -> bool:
        return (
            not owner.closed
            and card.generation == generation
            and card.result is result
            and card.exchange_context is context
        )

    def chosen(path: str) -> None:
        if not current():
            card.exchange_status.text = "Route changed while choosing a file; save the current result again."
            return

        progress = begin_exchange(card, "Recompute route before saving")

        def saved(digest: str) -> None:
            if current():
                card.exchange_status.text = f"Saved and recomputed complete route · SHA256 {digest[:12]}\nSource, target bytes, stock states and all three legs retained; start packet is historical evidence."

        owner._start(
            lambda cancelled: save_approach_review(
                path,
                context.source,
                context.offsets,
                result,
                comparison=context.comparison,
                clearance_mm=context.clearance_mm,
                target_raw=context.target_raw,
                cancelled=lambda: cancelled() or not current(),
                phase=progress.phase,
            ),
            saved,
            error_target=card.exchange_status,
        )

    owner.workspace.choose_profile_file(
        chosen, save=True, extension=".cvapproachreview", title="Save complete machine approach route"
    )


def open_route(card: Any) -> None:
    owner = card.owner
    if owner.running:
        return
    generation = card.generation

    def current() -> bool:
        return not owner.closed and card.generation == generation

    def chosen(path: str) -> None:
        if not current():
            card.exchange_status.text = "Inputs changed while choosing a route; choose again."
            return

        progress = begin_exchange(card, "Recompute opened route")

        def work(cancelled: Any) -> Any:
            from carveracontroller.desktop_stock_approach import approach_rows

            archive = load_approach_review(path, cancelled=lambda: cancelled() or not current(), phase=progress.phase)
            return archive, approach_rows(archive.report)

        def loaded(delivery: Any) -> None:
            archive, rows = delivery
            if not current():
                card.exchange_status.text = "Current inputs changed; opened route withheld."
                return
            card.exchange_context = RouteExchangeContext(
                archive.source, archive.work_offsets, archive.comparison, archive.clearance_mm, archive.target_raw
            )
            card.captured_start = None
            card.present(archive.report, rows)
            card.exchange_status.text = f"Opened and recomputed detached route · SHA256 {archive.sha256[:12]}\nHistorical start only; live position, loaded program, profiles, datums, tools and current target remain preserved. Capture a fresh pose for a new live-start review."

        owner._start(work, loaded, error_target=card.exchange_status)

    owner.workspace.choose_asset_file(chosen, suffixes=(".cvapproachreview",))
