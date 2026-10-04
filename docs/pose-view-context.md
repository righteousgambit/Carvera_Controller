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
