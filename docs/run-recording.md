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

Start bound recording hashes the selected local program on an artifact worker
and snapshots the declared stock/work offset into a new recording session.
Schema 2 retains that context; schema 1 archives remain readable and explicitly
unbound. The binding applies only to packets received after the new session
becomes active. It identifies local selection at start, not a machine-executed
file or a calibrated setup. The exact byte digest includes original line endings.
Only the program basename is retained; its source path and bytes are not embedded.
The preceding buffer remains inspectable/exportable until another start replaces
that previous-buffer slot. A failed start preserves both active and previous
buffers. Changing the current file or scene does not rewrite historical context.

Use recorded stock & offset restores the retained nominal setup to the local
viewer, including its original alignment declaration. It does not change machine
WCS values, tools or transport state. Historical tooling, fixture/vise assets,
camera calibration and their transformations are not yet retained.

Open matching program checks a chosen file against the recording's exact byte
digest and size before changing preview selection. A matching decoded UTF-8 text
program is staged under its content hash in the controller's local preview cache;
the staged bytes are independently read back. Existing corrupt cache entries are
preserved and rejected. Source-file changes after staging do not change the cache.
Compressed/binary programs need a separate immutable decode workflow; they are
rejected here so the legacy loader cannot mutate the content-addressed source.
The preview loader runs asynchronously and keeps recording actions disabled until
it returns. Parser exceptions, viewer rejection and changed selection are reported
separately from a successful byte match. No upload or execution command is sent.
This opens the associated program for local inspection; raw P counters still do
not establish a source-line execution association.

Association engine checkpoint: exact-byte staging and line-ending mismatch
rejection passed an independent standard-library check. Its source hash/readback
receipt is `/tmp/carvera-replay-program-engine-check.json`. Ruff and diff checks
passed. The real-loader integration regression is running; UI/native acceptance
of these new controls remains OPEN until its current-source result is inspected.

Camera custody source checkpoint: CameraFrame now retains the exact accepted
JPEG bytes alongside decoded RGB pixels, the server-reported capture timestamp
and local monotonic receipt time. An optional WebcamClient recording sink receives
that immutable frame and its source generation outside the client lock. Paused or
superseded fetches are withheld; sink exceptions do not suppress the live frame
or echo private exception details. The sink must enqueue quickly rather than
perform disk or encoding work on the camera worker. No additional camera request
or CNC command is introduced. This handoff is not yet connected to the run archive,
durable asset writer, camera replay or clock-uncertainty model.

Camera custody regressions cover original JPEG retention, callback lock ownership,
source generation, pause handling and sink-failure isolation. Syntax, Ruff and diff
checks passed. The focused camera suite passed all 16 tests (22.74 s) with plugin
autoload disabled and the timeout plugin explicitly loaded. Its receipt is
`/tmp/carvera-camera-custody-tests.log`; native/archive acceptance remains OPEN.
The earlier real-loader test's process sample
`/tmp/carvera-replay-program-process-sample.txt` showed native-library
loading during Python imports. That run later timed out in Kivy SDL2 initialization
before exercising the controls (11 core passes, 9 startup errors). The retained
retry disabled plugin autoload and explicitly loaded pytest-timeout; all 20
replay/program tests passed (231.67 s), including the real viewer handoff and
decoder-failure isolation. Output is `/tmp/carvera-replay-program-retry-tests.log`.

## Durable camera parts

CameraRunWriter saves accepted JPEGs to content-addressed files in an owned
session/part directory. A bounded queue decouples camera capture from disk work;
JPEG bytes are fsynced and independently read back before their receipt is
appended to a digest-chained JSONL manifest. Capture/server and receipt/client
times remain separate. Counts expose rejected/failed writes and queue losses.
Parts have a 256 MiB accepted-JPEG budget and 10,000-frame bound; reaching a limit
withholds further frames until the part is stopped. Limits are not a claim of
complete run coverage. Assets and partial journals are preserved on failures.

The writer drains on requested stop. A timeout leaves the same worker owned and
inspectable. App disposal detaches the sink and requests drain; the writer is
non-daemon so normal process exit waits for its outstanding writes. Forceful
termination may still leave a partial manifest, which is explicit on readback.
CameraRunReplay validates the manifest chain, schema, dimensions, ordering and
final accounting, then verifies asset size/hash before returning JPEG bytes.
Receipt-time seeking withholds images across source boundaries, retention gaps
and stale intervals; it does not infer exposure pose or cross-machine clock sync.

Run record now provides explicit Record camera frames / Stop camera recording
controls. Storage is beside the local profile store under recorded-runs/camera.
The part is bound to the active status-session UUID; a new status session is
withheld while its camera writer is active. Status readback is constant-size and
does not read the manifest on telemetry refresh. Recording is off by default.

Current combined source checkpoint: 42 tests passed (35.41 s) with one existing
locale warning, plus Ruff lint/format and diff checks. The workbench test starts
and stops an isolated real-JPEG archive, independently reads saved assets and
session identity, verifies worker drain and asserts no CNC command dispatch.
Receipt: `/tmp/carvera-camera-recording-workbench-tests.log`. The isolated profile
path prevents operator-store mutation. Native package acceptance, portable
camera-part export/import, archived-camera display and complete historical
calibration/tool/workholding bindings remain OPEN.

An optional purple archive-position marker is separate from the live and preview
poses. Exact event selection supplies same-packet MPos XYZ and C unit flags;
inches are converted to millimetres. Missing units, gaps, connection boundaries
and nonzero rotary angles hide it. It uses the current nominal scene registration,
not automatically restored historical setup. It neither seeks a purported executed
program line nor changes the live spindle/tool pose. Scene rebuilds automatically
refresh the selected marker against the current registration.

Binding/registration checkpoint: 18 recording and live/preview tests passed
(36.06 s), including exact-byte identity, immutable context, schema-1 compatibility,
previous-buffer retention, failed-start preservation, scene restoration with
unchanged live pose/mode, and marker refresh on scene rebuild. Ruff lint/format
and diff checks passed. Initial test-patch collection failure is retained in
`/tmp/carvera-bound-recording-tests.log`; final passing output is in
`/tmp/carvera-bound-recording-final-tests.log`. No installed or physical workflow
acceptance is claimed.

Recorded-marker checkpoint: 16 recording and live/preview tests passed (32.17 s)
with one existing locale deprecation warning; Ruff and diff checks passed.
Tests exercise independent marker seeking/clearing, packet unit conversion and
preservation of live/preview state without command dispatch. The initial shared
button argument startup failure and its process sample are retained in
`/tmp/carvera-recorded-marker-tests.log` and
`/tmp/carvera-recorded-marker-failed-exit.txt`.

Current source UI checkpoint: 10 focused integration/core tests passed in
12.24 s, including freeze, gap seeking, export/readback, corrupt import, existing
file preservation, worker failure recovery, empty archives and responsive render
captures. Ruff and diff checks passed. These are source tests, not installed
desktop acceptance.

OPEN: synchronized camera images
and custody, actual executed-program/setup attribution, complete historical
tool/workholding/registration assets, backend execution-versus-queue attribution,
override/alarm receipts, linked toolpath seeking, package/native acceptance and
physical workflow qualification. This is a transport/archive/replay checkpoint,
not a completed recorded-run workflow.

Source validation: 23 focused recording, observed-pose, spindle-parser and
receive-heartbeat tests passed (0.33 s). Ruff lint/format passed. Tests cover
roundtrip retention, corruption/duplicate-key rejection, packet/snapshot isolation,
gap/reconnect replay, shared packet timestamps, missing-field handling and capture
without command dispatch. This source checkpoint is isolated from DESKTOP140.
