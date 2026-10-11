"""Selected-lease status recording and shadow monitoring; no transport or IO."""

from __future__ import annotations

import hashlib
from typing import Any

from .adaptive_monitor import AdaptiveMonitor, Sample
from .backend_live_report import BackendLiveReport, finite, integer
from .run_recording import BackendRecordingSource, RunRecording, backend_source


class BackendTelemetry:
    def __init__(self, session_id: str, connection_id: str) -> None:
        self.source: BackendRecordingSource = backend_source(
            {
                "kind": "private_backend_ipc",
                "session_id": session_id,
                "connection_id": connection_id,
                "timing_source": "host_ipc_receipt",
            }
        )
        self.monitor = AdaptiveMonitor()
        self.recording = RunRecording(source=self.source)
        self.cursor = 0
        self.lost_receipts = 0
        self._pending_lost = 0
        self.rejected_receipts = 0
        self.latest_complete = False

    def matches(self, session_id: str, connection_id: str) -> bool:
        return (session_id, connection_id) == (self.source["session_id"], self.source["connection_id"])

    def unavailable(self, reason: str) -> None:
        self._invalidate(reason)

    def _invalidate(self, reason: str) -> None:
        self.monitor.fault = reason
        self.monitor.baseline = None
        self.monitor.baseline_samples = []
        self.monitor.capturing = False
        self.monitor.reason = reason
        self.latest_complete = False

    def consume(self, batch: dict[str, Any], report: BackendLiveReport, now: float) -> None:
        if batch.get("session_id") != self.source["session_id"]:
            self._invalidate("Backend receipt session replaced; no GUI fallback")
            return
        lost = integer(batch.get("lost_receipts"), 0, 10**12)
        latest = integer(batch.get("latest_sequence"), self.cursor, 10**12)
        receipts = batch.get("receipts")
        if lost is None or latest is None or not isinstance(receipts, list):
            self._invalidate("Backend receipt batch invalid")
            return
        self.lost_receipts += lost
        self._pending_lost += lost
        if lost:
            self._invalidate("Backend status receipts lost; baseline requires explicit recapture")
        for item in receipts:
            sequence = integer(item.get("sequence"), self.cursor + 1, latest) if isinstance(item, dict) else None
            if sequence is None:
                self._invalidate("Backend receipt sequence invalid")
                continue
            self.cursor = sequence
            if item.get("connection_id") != self.source["connection_id"]:
                self.rejected_receipts += 1
                continue
            status = item.get("status")
            stamp, utc = finite(item.get("received_at_s")), finite(item.get("received_utc_s"))
            if (
                not isinstance(status, dict)
                or not isinstance(status.get("raw"), str)
                or stamp is None
                or utc is None
                or not 0 <= stamp <= now
                or utc < 0
            ):
                self.rejected_receipts += 1
                self._invalidate("Backend receipt status or clock invalid")
                continue
            try:
                self.recording.capture_backend_status(
                    status.get("reported_state"),
                    status.get("raw_fields", {}),
                    stamp,
                    utc,
                    {
                        "sequence": sequence,
                        "ipc_sha256": item.get("ipc_sha256"),
                        "status_text": status.get("raw"),
                        "status_sha256": hashlib.sha256(status.get("raw", "").encode()).hexdigest(),
                    },
                    self._pending_lost,
                )
                self._pending_lost = 0
            except ValueError:
                self.rejected_receipts += 1
                self._invalidate("Backend receipt recording validation failed")
                continue
            sample = self._sample(status, stamp)
            if report.status is None or integer(status.get("machine_model"), 1, 2) != integer(
                report.status.get("machine_model"), 1, 2
            ):
                sample = None
            missing = () if sample is not None else ("complete normalized spindle/feed/XYZ packet",)
            self.monitor.quality.record(
                stamp,
                missing=missing,
                valid=sample is not None,
                rpm=sample.rpm if sample else None,
                pwm_available=bool(sample and sample.pwm is not None),
            )
            self.latest_complete = sample is not None
            if sample is None:
                self._invalidate("Incomplete or invalid backend spindle packet; recapture baseline")
            else:
                self.monitor.observe(sample, packet_quality_recorded=True)
        self.cursor = latest
        if not report.current or (report.session_id, report.connection_id) != (
            self.source["session_id"],
            self.source["connection_id"],
        ):
            self._invalidate("Selected backend report unavailable; baseline requires explicit recapture")
        self.monitor.tick(now)

    @staticmethod
    def _sample(status: dict[str, Any], stamp: float) -> Sample | None:
        position, fields = status.get("machine_position"), status.get("raw_fields")
        if not isinstance(position, dict) or not isinstance(fields, dict) or status.get("linear_units") != "mm":
            return None
        xyz = tuple(finite(position.get(axis)) for axis in ("x", "y", "z"))
        values = [
            finite(status.get(k))
            for k in (
                "spindle_rpm",
                "spindle_target_rpm",
                "spindle_override_percent",
                "feed_mm_per_min",
                "feed_override_percent",
            )
        ]
        pwm_field = fields.get("PWM")
        pwm = finite(pwm_field[0]) if isinstance(pwm_field, list) and len(pwm_field) == 1 else None
        if pwm_field is not None and pwm is None or any(v is None for v in (*xyz, *values)):
            return None
        assert all(v is not None for v in (*xyz, *values))
        numbers = [v for v in values if v is not None]
        coordinates = [v for v in xyz if v is not None]
        sample = Sample(
            stamp,
            str(status.get("state", "")),
            numbers[0],
            numbers[1] * numbers[2] / 100,
            pwm,
            numbers[3],
            numbers[4],
            (coordinates[0], coordinates[1], coordinates[2]),
        )
        return sample if sample.valid() and sample.state != "Unknown" and 0 < numbers[2] <= 200 else None

    def command(self, command: str) -> None:
        if command == "adaptive baseline":
            self.monitor.capture_baseline()
        elif command == "adaptive reset":
            self.monitor.reset()
        elif command == "adaptive shadow":
            self.monitor.enabled = True
        elif command == "adaptive off":
            self.monitor.enabled = False
        else:
            raise ValueError("Unsupported local shadow command")
