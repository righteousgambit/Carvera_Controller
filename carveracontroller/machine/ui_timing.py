"""Bounded local UI timings, independent of machine telemetry and camera clocks."""

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from time import monotonic


class NavigationTimings:
    """UI-thread owned. Clock turns and flips are observations, not presentation proof."""

    def __init__(self, limit=120, clock=monotonic):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Timing retention must be between 1 and 1000")
        self.clock = clock
        self.records = deque(maxlen=limit)
        self.sequence = 0
        self.evicted = 0

    def begin(self, source, target):
        self.sequence += 1
        if len(self.records) == self.records.maxlen:
            self.evicted += 1
        record = {
            "sequence": self.sequence,
            "source": source,
            "target": target,
            "started_monotonic_s": self.clock(),
            "phases_s": {},
            "callback_s": None,
            "clock_turn_s": None,
            "window_flip_s": None,
            "completed": False,
            "superseded": False,
        }
        self.records.append(record)
        return record

    @contextmanager
    def phase(self, record, name):
        start = self.clock()
        try:
            yield
        finally:
            record["phases_s"][name] = self.clock() - start

    def finish(self, record, *, completed):
        record["callback_s"] = self.clock() - record["started_monotonic_s"]
        record["completed"] = completed

    def observe(self, record, kind, *, current):
        if kind not in ("clock_turn_s", "window_flip_s"):
            raise ValueError("Unknown UI timing observation")
        if record["superseded"] or not record["completed"]:
            return
        if record["sequence"] != self.sequence or record["target"] != current:
            record["superseded"] = True
            return
        if record[kind] is None:
            record[kind] = self.clock() - record["started_monotonic_s"]

    def snapshot(self):
        return {
            "schema_version": 1,
            "clock": "local monotonic seconds",
            "retention_limit": self.records.maxlen,
            "evicted": self.evicted,
            "records": deepcopy(list(self.records)),
            "limits": "Callback entry excludes input dispatch delay. Clock turn and window flip notifications "
            "do not prove screen presentation or machine response. Superseded targets remain unobserved.",
        }
