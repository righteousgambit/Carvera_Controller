"""Two independently coalesced component preparation lanes; no widget access."""

from __future__ import annotations

import threading
from typing import Callable, Literal, TypedDict

ComponentKind = Literal["fixture", "workholding"]


class ComponentLane(TypedDict):
    generation: int
    active: bool
    pending: tuple[int, Callable[[], object], Callable[[object | None, str | None], None]] | None


class ComponentLoads:
    def __init__(self, dispatch: Callable[[Callable[[], None]], None]) -> None:
        self.dispatch = dispatch
        self.closed = False
        kinds: tuple[ComponentKind, ...] = ("fixture", "workholding")
        self.lanes: dict[ComponentKind, ComponentLane] = {
            kind: {"generation": 0, "active": False, "pending": None} for kind in kinds
        }

    def invalidate(self, kind: ComponentKind) -> None:
        lane = self.lanes[kind]
        lane["generation"] += 1
        lane["pending"] = None

    def close(self) -> None:
        self.closed = True
        for kind in self.lanes:
            self.invalidate(kind)

    def submit(
        self,
        kind: ComponentKind,
        work: Callable[[], object],
        finish: Callable[[object | None, str | None], None],
    ) -> bool:
        lane = self.lanes[kind]
        if self.closed:
            return False
        lane["generation"] += 1
        request = (lane["generation"], work, finish)
        if lane["active"]:
            lane["pending"] = request
        else:
            self._start(kind, request)
        return True

    def _start(
        self,
        kind: ComponentKind,
        request: tuple[int, Callable[[], object], Callable[[object | None, str | None], None]],
    ) -> None:
        generation, work, finish = request
        lane = self.lanes[kind]
        lane["active"] = True

        def worker() -> None:
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)

            def publish() -> None:
                lane["active"] = False
                pending, lane["pending"] = lane["pending"], None
                if self.closed:
                    return
                if pending is not None:
                    self._start(kind, pending)
                    return
                if generation == lane["generation"]:
                    finish(result, error)

            self.dispatch(publish)

        threading.Thread(target=worker, name="component-prepare-" + kind, daemon=True).start()
