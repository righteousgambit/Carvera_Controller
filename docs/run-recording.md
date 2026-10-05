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
passed. The real-loader integration regression passed in the retained 20-test retry
described below; installed/native acceptance of these controls remains OPEN.

Camera custody source checkpoint: CameraFrame now retains the exact accepted
JPEG bytes alongside decoded RGB pixels, the server-reported capture timestamp
and local monotonic receipt time. An optional WebcamClient recording sink receives
that immutable frame and its source generation outside the client lock. Paused or
superseded fetches are withheld; sink exceptions do not suppress the live frame
or echo private exception details. The sink must enqueue quickly rather than
perform disk or encoding work on the camera worker. No additional camera request
or CNC command is introduced. The handoff now connects to the durable camera writer and receipt-time replay
described below. Exposure timing and cross-machine clock uncertainty remain unqualified.

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
camera-part export/import and complete historical calibration/tool/workholding
bindings remain OPEN. Archived-camera source display is described below.

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

OPEN: exposure-synchronized camera images, portable camera custody, actual executed-program/setup attribution, complete historical
tool/workholding/registration assets, backend execution-versus-queue attribution,
override/alarm receipts, linked toolpath seeking, package/native acceptance and
physical workflow qualification. This is a transport/archive/replay checkpoint,
not a completed recorded-run workflow.

Source validation: 23 focused recording, observed-pose, spindle-parser and
receive-heartbeat tests passed (0.33 s). Ruff lint/format passed. Tests cover
roundtrip retention, corruption/duplicate-key rejection, packet/snapshot isolation,
gap/reconnect replay, shared packet timestamps, missing-field handling and capture
without command dispatch. This source checkpoint is isolated from DESKTOP140.

## Archived-camera display

The main camera pane can display a camera part associated with the selected
status recording. Import requires the selected frames.jsonl manifest and a
matching session UUID; failed imports preserve the preceding association. First,
Previous, Next, Last and slider seeks follow local monotonic receipt time. Camera
capture continues independently and Show live camera returns to its latest frame.
Archived images are explicitly labeled; they do not claim current machine state.

JPEG validation and decoding run off the UI thread. Rapid seeks coalesce to the
latest request and superseded results cannot paint an older image. Status gaps,
missing session association, stale receipts and asset/decode errors clear the
image rather than fall back to live content. Live camera registration overlays
and fitting are withheld while archived imagery is displayed because historical
calibration has not been retained.

Source regression coverage exercises timeline following, gap clearing, actual
texture display, wrong-file and wrong-session rejection, independent live capture,
return to live and superseded decoding without CNC command dispatch. This remains
a receipt-time replay workflow; exposure-pose synchronization, historical scene
assets, executed-line attribution, portable bundling and native acceptance are open.

Archived-display validation: 44 combined recording/pose/camera tests passed
(35.82 s), with one existing locale deprecation warning. Ruff lint/format and
diff checks passed. Wide and narrow source renders were visually reviewed;
controls reflow without clipping. Receipt: /tmp/carvera-camera-replay-final-tests.log.
No package install, controller dispatch or physical machining acceptance is claimed.

## Replay workbench concentration

The timeline and selected packet stay together in the primary view. Recording
files/buffers, historical scene/program association and camera capture/replay
are secondary collapsible sections. Their responsive bodies size to their content
rather than a fixed height, preserve loaded recordings and widget state, and
release keyboard ownership when collapsed. The camera section heading reports
recording-live, viewing-archive or idle even when its controls are collapsed.

The combined 44-test source suite passed (37.76 s) before the final camera-heading
status addition. Wide/narrow compact renders were reviewed; the narrow panel no
longer puts all secondary controls above the selected observation. Complete native
layout/responsiveness acceptance remains open.

Final current-source workbench validation: 7 integration tests passed (15.98 s),
including recording/archived/live heading states, section expansion/collapse,
recording identity preservation, camera replay, gap handling and superseded decode.
Ruff and diff checks passed. Receipt: /tmp/carvera-replay-sections-final-tests.log.
Compact and expanded narrow renders were reviewed; native package acceptance
remains OPEN.

## Portable camera parts

Export camera bundle saves a .cvcamera ZIP_STORED archive containing the exact
frames.jsonl and its referenced content-addressed JPEGs. Repeated frames share one
asset. Export refuses existing destinations, checks the selected manifest has not
changed, verifies source JPEGs and independently reads back the saved archive.
Import camera bundle validates the exact member set, digest chain, sizes and
JPEG hashes before writing; its session must match the selected status recording.
Encrypted/compressed entries, directories/symlinks, duplicates, unexpected paths,
missing assets and over-budget archives are rejected. The opened input descriptor
is retained throughout size validation and installation.

Imports install into a fresh owned directory and verify the installed manifest
and assets. Existing recordings remain untouched; failed imports preserve the
selected replay. If installation fails after validation, its owned partial part
is preserved for inspection. Bundle operations run on the artifact worker. Camera
bundles travel with a separate .cvrun status archive; a single combined portable
job with program, historical tool/workholding/calibration assets remains open.

Source bundle/replay checkpoint: 52 tests passed (38.98 s) with one existing locale
warning; includes real-JPEG workbench export/import, replay and no-command assertions.
Ruff lint/format and diff checks passed. The expanded narrow layout was reviewed.
Receipt: /tmp/carvera-camera-bundle-tests.log. Native package acceptance remains open.

After retaining the opened source descriptor, all 13 camera-engine tests passed
(52.09 s including external-volume startup; one timeout-config warning because
the timeout plugin was not loaded for this pure-engine run). Receipt:
/tmp/carvera-camera-bundle-final-engine-tests.log. An independent standard-library
roundtrip and wrong-session check also passed against the exact current engine
hash in /tmp/carvera-camera-bundle-engine-receipt.json.

## Combined recorded-run bundles

The Recording files & buffers section now offers Open full run / Export full run
and an explicit Open included program action. A .cvsession stores digest-bound
status.cvrun, the exact selected decoded text program, and an optional nested
.cvcamera. The status archive retains the declared stock/work offset and local
selection scope. Unbound records and mismatched program/camera identities cannot
be promoted to a combined run. Each member has its exact size and SHA-256; imports
validate those values, the status session, selected-program identity and nested
camera session/assets before installation into a fresh owned run folder. Existing
files are preserved. Camera members are streamed through the seekable outer ZIP
member rather than expanded into a second temporary camera archive.

Import changes only local replay selection. It neither opens the included program
automatically nor applies setup, tools, machine WCS or commands. The explicit
program action uses the existing verified content-addressed preview loader. Camera
presence/absence is reported and selecting another status session clears the old
program/camera association. Export uses the included program when available, or
requires the current local selection to match the retained identity.

This is a combined portable run of selected program, status, declared stock/offset
and camera evidence. Historical tools/holders, machine/fixture/vise assets and
calibration are still missing; the bundle does not prove actual executed-file
identity or synchronized exposure pose. Those original requirements remain open.

Validation: initial combined suite 60 passed (40.11 s); after stale-association
and nested foreign-session regressions, 29 focused engine/workbench tests passed
(16.31 s), each with one existing locale warning. Receipts:
/tmp/carvera-full-run-bundle-tests.log and /tmp/carvera-full-run-final-tests.log.
Ruff lint/format and diff checks passed. Installed/native acceptance is open.

Optional-camera UI regression initially failed because a no-image import retained
the preceding camera description. The correction explicitly reports camera absence
and preserves live capture; its focused roundtrip passed (1 test, 10.65 s, one
existing locale warning). Failure receipt: /tmp/carvera-full-run-optional-camera-tests.log;
passing current-source receipt: /tmp/carvera-full-run-optional-camera-retry-tests.log.
Ruff lint/format and diff checks passed on the final source.

## Setup assets retained at recording start

Start with setup assets captures selected declarations without program/CAD disk
reads on the UI thread. The artifact worker binds the exact program, saves a
portable .cvjob setup snapshot, reads it back and validates nominal stock/offset
and declared geometry hashes before creating the new active session. Failed
preparation preserves both the active record and previous buffer; its owned
failed snapshot remains available for inspection. Existing lightweight recordings
still use schema 2; schema 3 adds an exact setup-archive size/SHA-256 and explicit
declared-setup scope. Schema 1/2 remain readable, and configuration identity cannot
be silently downgraded into schema 2.

The snapshot captures selected machine/toolset profiles, loaded tool definitions
in millimetres, available physical-assembly revision binding, component CAD, vise
placement and registration correspondences when present. Only selected toolset or
assembly-linked cutter profiles are retained. Asset references become portable
content-addressed references through the existing job-package validation. Stock
alignment remains the original declaration; it is not upgraded to measured proof.
A missing CAD source or changed selected cutter geometry withholds activation.
This does not include a calibration-frame image, observed ATC inventory, rest stock
or measured physical holder reach, nor does it prove the selected machine CAD
still matches previously rendered geometry when its source file changed.

Combined .cvsession bundles can now include the exact setup.cvjob. Its digest and
program/stock binding are checked before import. Its bytes are independently
read back on installation, and the retained path is associated with that run for
future exports. Imported setup assets are retained but not automatically applied
to the scene, tool library or camera. Complete historical scene/tool restoration
and calibration-image/exposure qualification remain open.

Validation: 62 combined recording/job/camera/workbench tests passed (16.68 s);
31 final recording/setup/workbench tests passed (18.09 s), each with one existing
locale warning. Tests cover original-byte custody after source mutation, schema-3
roundtrip, configuration inclusion, changed geometry/nominal setup rejection,
UI declaration capture without file I/O, new-session activation only after
readback, failed-capture preservation and no CNC command dispatch. Receipts:
/tmp/carvera-recorded-setup-tests.log and /tmp/carvera-recorded-setup-final-tests.log.
Ruff and diff checks passed. Native package and physical acceptance remain open.

## Historical scene and tool restoration

Load recorded scene & tools explicitly prepares the retained setup archive on the
artifact worker. It verifies the archive identity, exact selected program bytes
and normalized inspector identity separately, installs retained assets in a fresh
owned preview directory, validates tool dimensions/CAD digests and builds scene
and cutter geometry before UI publication. Changed selection, scale or machine
activity withholds publication. Recorded stock alignment is treated as unverified.

The preview restores nominal machine/fixture/vise geometry, placement, stock and
archived cutter/holder definitions. An archived-cutter selector follows the program
or displays an explicitly selected retained tool. The profile badge identifies
recorded setup preview; full file digests are available in a nested disclosure,
while the primary context displays explicitly labeled SHA-256 prefixes.

Restore previous scene prepares geometry for the current program scale on the
worker and restores the original scene/tool metadata. Failed publication attempts
to restore the preceding scene; failure does not discard the retained previous
state. Neither action changes persistent profiles, machine WCS, connection/camera
settings, physical assembly identity or tool inventory. New setup-bound recording
and job capture are withheld until previous-scene restoration exits this preview.

Historical camera calibration is not applied. Measured holder reach, rest stock,
actual executed-file attribution and exposure-pose synchronization remain open.
The new source is not included in DESKTOP141. Native acceptance remains OPEN.

The final affected suite passed 80 tests (67.30 s, one existing locale warning),
including actual retained fixture/tool assets, original-source mutation, LF/CRLF
programs, archived-cutter selection, prior-scene restoration and assertions of no
configuration writes or CNC dispatch. Wide/narrow source renders were reviewed.
Receipt: /tmp/carvera-historical-scene-retina-final-tests.log. Earlier framebuffer
attachment failures and dimension diagnostics are preserved in
/tmp/carvera-historical-scene-broad-diagnostic-tests.log.

## Native setup-binding dimension correction

DESKTOP141 native Start with setup assets rejected the current declared setup with
"Setup snapshot stock/offset differs" and preserved the preceding recording.
The UI declaration capture retains tuple stock dimensions, while portable job
stock uses JSON lists. The binding comparison already normalized origin/offset,
but omitted size. Source now compares size in the same list representation while
retaining exact dimensional and alignment checks; differing dimensions remain
rejected. This changes neither physical registration nor machine configuration.

An independent standard-library exercise saved/read back a setup archive from
native tuple dimensions, validated its recording digest and rejected a changed
stock size before publication. Receipt:
`/tmp/carvera-native-dimensions-engine-receipt.json` (exact source SHA-256 included).
The added pytest regression and compact-layout tests are still running; their
current process samples show dependency/library loading rather than acceptance.
This correction is not in DESKTOP141 or the frozen DESKTOP142 build. Native
setup-bound recording remains OPEN until a corrected package is exercised.

Compact-observation source checkpoint: freezing a native recording exposed a
layout problem where all raw packet rows displaced the file/camera controls.
The primary view now retains a short observation (event/state, same-packet tool
and actual RPM report); full receive clocks, units, coordinates and counters are
in a separate initially collapsed disclosure. Missing tool/RPM fields remain
unknown and commanded RPM is not substituted for actual RPM. Empty records and
gaps clear the observation. The wide/narrow regression exercises disclosure
height, raw-data retention, missing fields, gaps and return to live. Lint,
formatting and syntax checks passed; runtime regression/render acceptance is
still pending on the existing test process. No installed UI acceptance is claimed.
