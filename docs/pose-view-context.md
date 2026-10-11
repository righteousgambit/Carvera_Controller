# Operation inspection and machine view context

The workbench has a compact view-status row visible in every section. It names
Preview, Live or Compare independently of machine execution state. In Preview
and Compare it identifies the selected operation and source line. The machine
pane caption also names its visualization mode without adding controls to the
media surface.

Selecting an operation, explicitly inspecting a source line, scrubbing playback,
starting local animation or jumping to its start/end enters Preview. A selected
Compare mode remains Compare. Status-driven line updates do not switch modes.
The view selector and rendered mode stay synchronized.

Return to live uses only a fresh one-packet pose from the current connection.
Disconnected, absent, stale or future-dated packets cannot enable this action.
Returning stops local playback and its dynamic path display while retaining the
inspection selection and preview distance. It does not stop CNC execution,
hold feed, upload a program or issue motion. The Live selector can still show a
frozen view when observations are unavailable; that state is explicitly labeled.

Operation rows now distinguish title from tool/time/source-range metadata and
show their warning count. Source ranges and nominal durations remain parser
results, not measured cycle times or proof of executed motion.

This improves source/runtime view ownership. It does not qualify CAD registration,
physical tool assemblies, work offsets, collision detection, machine pose accuracy
or backend execution. Installed-app validation of this change remains a separate
gate from integration tests and rendered source UI.

## Installed DESKTOP98 checkpoint

On October 4, 2026, DESKTOP98 from source
`76039c4e2474393143d722cdede5bf24f851c317` passed native operation-card,
Live-to-Preview inspection, preserved Compare selection, disconnected/frozen
Live labeling and fresh-pose Return to live checks. The operator configuration
and profile stores were restored exactly from their pre-test backup before
relaunch. The restored app reported Workshop Carvera at 192.168.0.79, Idle,
physical T1, TLO 50.480 mm, zero spindle/feed, fresh telemetry and live camera.
These observations prove view ownership and connection behavior, not physical
model alignment or machining qualification. No upload, run or motion was issued.

Manifest readback matched 427 repository files and 430 staged, built and
installed files; strict signature checks passed for build, installed app and
retained DESKTOP97 recovery. Receipts and native screenshots:
`/Users/wes/Downloads/carvera-desktop98-20261004/native-receipt.json`,
`operator-restoration.json` and `native-restored-connected.png`.

## Empty operation workspace

Source-inspection tools appear only after operation analysis succeeds. Clearing
the program or a failed load removes these controls and closes tool-bank details;
stale asynchronous results cannot reveal them. Tool-bank preparation remains
disabled until operations are available. This source improvement requires its
own package/native acceptance after DESKTOP98.

Source regression checkpoint: 19 pose-context, selection-navigation and program-task
integration checks passed in 183.34 seconds; Ruff lint/format and diff checks
passed. One existing locale deprecation warning remains. The new empty-state
render is at `/Users/wes/Downloads/carvera-operation-empty-20261004/tests/`
with its log at `tests.log` in the parent directory.

## Installed DESKTOP99 checkpoint

On October 4, 2026, DESKTOP99 from
`a1518fda8fbd22f5cd785f3d9945f2e65a78abcc` passed native empty Operations,
loaded operation cards, singular warning label and selected-source inspection
checks. Source navigation/search/inspection are absent in the empty pane and
return after successful analysis. The demo remained a disconnected local preview.

After exact restoration of operator configuration and profile stores, the app
reconnected to Workshop Carvera in Idle with T1, TLO 50.480 mm, zero spindle/feed,
fresh telemetry and live camera. Return to live used a fresh reported pose.
No program upload/run or machine motion was issued. All 427 source and 430
staged/built/installed manifest entries matched, with strict signatures passing
for build, install and retained DESKTOP98 recovery. Native evidence and readback:
`/Users/wes/Downloads/carvera-desktop99-20261004/native-receipt.json` and
`artifact-verification.json`. This closes this empty-state installed checkpoint,
not the broader operation workspace, physical registration or execution scopes.

## Selected backend reports

Program-view arrival also recalculates the task viewport using the current
header and available height. A retained hidden-screen layout cannot keep an
oversized task area that shrinks when the context header is collapsed.

When the workbench selects a private backend, live machine pose, RPM/feed/tool
metrics, position readouts, setup telemetry and tool comparison use the same
lease-bound read-only report source. Reading cached telemetry sends no RPC and
never populates the GUI controller's variables or enables its command guards.
The selected profile must match the endpoint and reported C1/CA1 model. Replaced
child/connection identities, unresolved outcomes, binary transfers, stopped
clients and combined child/cache receipt ages over 0.8 seconds retire that source.
There is no fallback to an older GUI pose.

Complete one-packet normalized XYZ, work position, rotation, rotary position and
WCS are required for the live scene. Missing pose fields leave independently
reported RPM/feed available but clear the live marker and Return to live action.
Live mode retains its last rendered position with an unavailable caption. The
status caption grows with narrow workbench widths. CAD table/head translation
remains nominal and unqualified; reported coordinates do not calibrate geometry.

A reported tool number selects only an already declared tool profile. It does
not identify the installed cutter geometry. The backend's raw tool offset stays
labeled **firmware units/reference**, separate from millimeter library lengths
and historical measurements. No conversion or calibration inference is made.

Camera references captured with this source retain its exact child session and
connection identity as optional exchange metadata. Legacy GUI references remain
readable; they cannot silently activate a backend overlay. A replacement lease
invalidates overlay use and pending lens/calibration callbacks. Camera timing
remains host receipt evidence with exposure synchronization unqualified.

Source/native regression uses an actual private child and a loopback status
server, with poisoned GUI variables to verify source isolation. This gate does
not establish installed-app behavior, physical alignment, machining, exposure
synchronization, or full backend migration.
