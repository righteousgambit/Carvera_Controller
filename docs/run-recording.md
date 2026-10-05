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

OPEN: workbench recording/export/import controls, synchronized camera images
and custody, program/setup binding, backend execution-versus-queue attribution,
override/alarm receipts, linked toolpath seeking, package/native acceptance and
physical workflow qualification. This is a transport/archive/replay checkpoint,
not a completed recorded-run workflow.
