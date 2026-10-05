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
        # Rare slow observations must survive routine refresh ring eviction.
        self.slowest = {}
        self.longest_start_interval = None
        self._previous_start = None

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
        if self._previous_start is not None:
            previous = self._previous_start
            interval = record["started_monotonic_s"] - previous["started_monotonic_s"]
            if self.longest_start_interval is None or interval > self.longest_start_interval["interval_s"]:
                self.longest_start_interval = {
                    "interval_s": interval,
                    "previous_sequence": previous["sequence"],
                    "previous_target": previous["target"],
                    "sequence": record["sequence"],
                    "target": target,
                }
        self._previous_start = record
        self.records.append(record)
        return record

    def _retain_slowest(self, record, kind):
        previous = self.slowest.get(kind)
        if previous is None or record[kind] > previous[kind]:
            self.slowest[kind] = deepcopy(record)

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
        self._retain_slowest(record, "callback_s")

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
            self._retain_slowest(record, kind)

    def snapshot(self):
        return {
            "schema_version": 1,
            "clock": "local monotonic seconds",
            "retention_limit": self.records.maxlen,
            "evicted": self.evicted,
            "records": deepcopy(list(self.records)),
            "slowest": deepcopy(self.slowest),
            "longest_start_interval": deepcopy(self.longest_start_interval),
            "limits": "Callback entry excludes input dispatch delay. Clock turn and window flip notifications "
            "do not prove screen presentation or machine response. Superseded targets remain unobserved. "
            "Slowest observations persist for this session independently of recent-record eviction. "
            "Start intervals measure callback cadence, not the cause of a delay; navigation intervals include operator idle time.",
        }
