# Recorded-run transport checkpoint

Original requirement 18 remains open. The controller now retains up to 10,000
status/gap/connection events in memory. Capture runs on the status transport path
without disk I/O, new polling, or controller commands. Monotonic receive time is
shared with the observed pose; UTC capture time is retained separately. Wire
coordinates and unit/mode flags stay together. Missing packet fields do not
inherit earlier values. Raw P counters are reported values, not proof of executed
motion or a program revision binding.

`Controller.run_recording.export_bytes()` exports a versioned, digest-checked
local archive. Retention loss is explicit. Import rejects corrupt digests,
duplicate keys, invalid sequences, non-finite values and oversized archives.
The digest establishes byte integrity, not trusted origin or machine accuracy.

`RecordingReplay(data).at(monotonic_at)` seeks the retained observation and its
age. It does not interpolate motion or extrapolate outside the recording.
Telemetry gaps and connection boundaries yield unknown motion. Archive values
and replay results own their copies so consumers cannot edit the active record.

The Program workbench now includes a Run record task with freeze/live-buffer,
event stepping, packet details, and archive import/export. Artifact processing
runs off the UI thread; heartbeat readback copies only the latest packet. Export
refuses to overwrite an existing archive and validates saved bytes. Failed
imports and unexpected worker errors preserve the loaded replay and release
controls. Empty archives clear the previous sample. The five Program tasks fit
one row at wide widths and reflow at narrow widths.

Current source UI checkpoint: 10 focused integration/core tests passed in
12.24 s, including freeze, gap seeking, export/readback, corrupt import, existing
file preservation, worker failure recovery, empty archives and responsive render
captures. Ruff and diff checks passed. These are source tests, not installed
desktop acceptance. Replay remains separate from Live and Preview geometry.

OPEN: synchronized camera images
and custody, program/setup binding, backend execution-versus-queue attribution,
override/alarm receipts, linked toolpath seeking, package/native acceptance and
physical workflow qualification. This is a transport/archive/replay checkpoint,
not a completed recorded-run workflow.

Source validation: 23 focused recording, observed-pose, spindle-parser and
receive-heartbeat tests passed (0.33 s). Ruff lint/format passed. Tests cover
roundtrip retention, corruption/duplicate-key rejection, packet/snapshot isolation,
gap/reconnect replay, shared packet timestamps, missing-field handling and capture
without command dispatch. This source checkpoint is isolated from DESKTOP140.
