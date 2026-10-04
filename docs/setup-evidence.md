# Setup evidence workbench

The Evidence shortcut opens a right-hand workbench inspector while keeping the
machine and camera visible. The next-action strip guides program selection,
setup review, connection inspection and program review. It does not start a job.

Four evidence groups cover stock, fixture/vise mounting, loaded tool geometry and
preview work-coordinate alignment. Their states are:

- **Unresolved**: required local configuration or evidence storage is unavailable.
- **Entered**: geometry/preferences exist, but no measurement receipt describes them.
- **Measured**: an operator-recorded measurement reference matches the current
  dependencies and is within its explicitly entered validity interval.
- **Stale**: dependencies changed, the interval expired, the record is future-dated,
  or the operator invalidated it after a physical change.

Record a measurement only after checking the physical setup. Enter the method,
measurement-log/photo/probe-result reference, timezone-aware measurement time and
validity interval. The UI refuses blank provenance and future timestamps. The
record is a report from the operator, not independently verified measurement data.
It does not change offsets, tool tables, fixtures or machine motion.

A vise placement change invalidates stock and coordinate receipts as well as the
mounting receipt. Changing loaded cutter geometry invalidates tooling and coordinate
receipts. Program tool requirements participate in tooling identity. Replacing an
identical physical cutter or reclamping on the same holes cannot be detected from
unchanged geometry: use **Invalidate after physical change** and record the reason.
Prior receipts are retained. A receipt dialog refuses to save if its setup changed
while it was open.

Controller-reported tool/TLO and telemetry age are displayed separately. Missing
or stale packets are not promoted to current physical evidence. The evidence
summary is not a complete preflight or execution authorization; travel, clearance,
program compatibility, physical tool-slot reconciliation and machine protections
remain separate checks.

Receipts persist per machine profile in `~/.carvera/setup-evidence.json`. The
versioned, bounded store validates records and writes atomically. Corrupt evidence
is preserved and saving refused pending repair. Integration tests isolate this
store from operator data. Timestamp/geometry binding tests and Kivy interaction
checks cover persistence, edits, tool replacement, manual invalidation, form
validation and navigation without commands. Rendered checks cover 1440×900 and
1000×700 logical window sizes.

Remaining integration includes receipt-bound numerical probe/instrument results,
per-physical-tool identity, asset-content replacement detection, portable job
receipt custody, dependency-specific calibration rules, observed offset comparison
and complete readiness across limits, program semantics and machine capabilities.
