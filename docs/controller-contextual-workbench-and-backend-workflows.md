# Contextual workbench and advanced backend workflows

These 25 requirements retain the latest user-approved implementation scope.
All complete workflows are OPEN. They supplement earlier ledgers rather than
replace them. Source engines, native interaction, backend execution and physical
qualification require separate evidence. This ledger does not authorize physical
execution, machine configuration writes or automatic adaptation.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Selection-driven workbench | Object selection routes to the linked inspector and preserves context. |
| 2 | Named resizable layouts | Pane sizing, scene/camera framing and workbench section round trip in named presets. |
| 3 | Dimensional inputs | Shared unit/expression input, keyboard stepping and validation work throughout the native workbench. |
| 4 | Program revision differences | Tools, depths, frames, extents and operations compare between captured revisions before loading. |
| 5 | Coordinated selection trail | Back/forward restores selected operation, assembly, issue and source context with view framing. |
| 6 | Progressive expert detail | Compact summaries, everyday controls and expert disclosure preserve focus and responsiveness. |
| 7 | Coordinate-chain inspector | Machine, fixture, vise, stock, WCS and tip transforms expose values and measurement provenance. |
| 8 | Camera setup verification | Reference images, reviewed checks and calibration mismatch are retained and exercised. |
| 9 | Viewport tool assembly editing | Cutter, holder, collet and extension dimensions distinguish vendor geometry from measured stickout. |
| 10 | Tool choice comparison | Candidate reach, features, holder clearance, residual stock and changes are explained. |
| 11 | Physical magazine semantics | Fixed/random pockets, oversized exclusions, reserved pockets and sister tools reconcile through a supported backend. |
| 12 | Two-bank transaction | Remove/install/reconcile/measure/continue completes with qualified six-pocket hardware. |
| 13 | Physical cutter condition | Usage, material, measurements, replacements and inspections bind to individual cutter identities. |
| 14 | Geometry-launched probing | Selected features produce reviewed approach/contact/retract plans and retained measured results. |
| 15 | Measurement correction proposals | Feature errors, predicted effects, approval and backend readback remain distinct. |
| 16 | Synchronized run replay | Path, RPM, feeds, overrides, alarms and camera retain timing uncertainty and queued/executed identity. |
| 17 | Adaptive experiment workspace | Signal noise, response, delay and override experiments are measured per assembly and material. |
| 18 | Operation adaptation policies | Operation-specific objectives, permitted responses, bounds and stale-state behavior are exercised. |
| 19 | Backend-owned fast loop | Qualified local sampling/actuation exposes timing, limits, acknowledgments and desktop handoff. |
| 20 | Dynamics cycle analysis | Acceleration, short moves, rotary motion, changes and stops compare with observed timings. |
| 21 | Rotary setup assistant | Chuck/jaws/centerline/tailstock, indexed/continuous motion, travel and unwind plans are registered. |
| 22 | Joint and tip debugger | Joint solutions, tip motion, travel, topology and supported TCP state are inspectable. |
| 23 | Orientation quality map | Joint margins, singularities, holder clearance and orientation changes associate with candidate paths. |
| 24 | Auxiliary timing/interlocks | Named coolant, air, extraction, clamps, doors and pallets distinguish observed states and immediate/synchronized actions. |
| 25 | Commissioning/capability workspace | Configured, observed and exercised hardware, commands, geometry and telemetry remain distinct. |


## Task-focused Machine workbench checkpoint

Machine workbench content is now organized into Connect, Health, Kinematics,
Capabilities, Captures and Preferences. A single retained task is mounted in the
scroll host; hidden tasks keep their model/drafts while releasing keyboard and
menu focus. Measured caption widths determine tabs versus a compact dropdown,
keeping the navigation on one 34-pixel row. The task summary explains the active
workflow, with separate reading positions and stale restore rejection during
rapid navigation. Disposal cancels pending restoration and releases focus.

The workbench Connection action routes to Connect before revealing its controls.
All six tasks are discoverable in the command palette with terms for connection,
UI timing, five-axis joints, capability evidence and historical HAL comparison.
These are navigation actions, not controller commands. Existing connection,
maintenance and configuration guards remain in their original command paths.

Full-app mounted checks exercise 360/650/1100-pixel layouts, focus release,
retained advanced state, scroll restoration, rapid switching, palette routes,
connection reveal and absence of execution commands. The related connection,
palette and capability regression passes 15 checks, with one environment SSL
warning. The final render pass passes all three widths; actual Connect/Health
renders were inspected. Full Ruff/format and both architecture contracts pass;
three changed UI modules pass focused package-baseline typing. Native installed
interaction, packaging of this source and the broader 350-requirement overhaul
remain OPEN. This checkpoint does not close camera registration, synchronized
capture or advanced backend/physical qualification.

Final full-app navigation/kinematic review/command regression: **66 passed**, one
known environment SSL warning, 51.49 seconds. The earlier failed navigation test
and logs remain retained; the scroll-restoration race was corrected and the final
run uses the corrected source. The installed application has not been replaced
by this source checkpoint.


## Setup task workbench and cross-platform navigation correction

Setup now separates Tools, Datum, Surface, Holes and Repeat using the retained
responsive task deck. Existing controls and command guards are preserved; surface,
hole and repeat planners keep their local drafts and expanded state. Cutter
comparison routes to Tools. Restoring a reviewed facing or hole recipe selects
Surface or Holes before expanding the relevant form. All five tasks are searchable
in the action palette; switching does not upload or execute a program.

Hosted run 37465237309 for `e8cbb6d9034cd816196d504ff921f99b3eecd9a7`
failed three newly added navigation tests, while 2,743 tests passed and 17 skipped.
The failed raw log is retained. Two failures exposed scroll restoration occurring
before Linux layouts settled; the third used a Mac-specific screenshot path.
Restore now waits for pending child layouts/textures, resets residual scroll
motion and rejects superseded generation callbacks. Test artifacts use the
portable pytest temporary directory. Explicit result reveals cancel saved-position
restoration; long cutter lists and planning disclosure/recipe restores retain their
intended target. A retained-passport test explicitly selects Overview to avoid
assuming state left by prior recipe tests. No product state reset was introduced.

The corrected combined full-app regression passes **53 checks**, one known local
SSL warning, 44.56 seconds. It covers Machine and Setup task navigation, preserved
drafts, focus release, direct palette routes, long-magazine reveal, surface/hole
recipe restoration, repeat plans, connection navigation and no unexpected machine
commands. Eight changed UI modules pass focused package-baseline typing; full
Ruff/format and both architecture contracts pass. Source Datum/Tools renders were
inspected at narrow/wide widths. Installed interaction and exact-source hosted CI
remain independent OPEN gates. Camera registration, synchronized capture and all
remaining requirements in the full 350-item program remain OPEN and active.

The existing desktop workspace, kinematic review and command regression also
passes **63 checks**, one environment warning, 45.27 seconds, on this source.


## Task-aware Back/Forward history checkpoint

The shared bounded session history now captures the active task and reading
position for Program, Setup, Machine and Spindle workbenches. Task changes use
before/after hooks so departure framing/reading position is retained before the
new task arrives. Task name is part of history identity; changing only a reading
position updates the current entry rather than manufacturing a new visit. History
labels identify the task. Existing program/setup-context checks still reject a
revisit after identity changes without silently rebinding the old entry.

Task names and finite normalized reading positions validate before changing page,
selection, pose or history index. Restoration suppresses arrival callbacks, restores
the specific task, and waits for pending layout/texture work before applying its
reading position and resetting scroll motion. A later selection, history reset,
rapid traversal or workspace disposal invalidates pending delivery. Departure
while a restore is pending preserves its target position rather than overwriting
it with a transient layout value. A closed navigation object rejects traversal.
Restoring a non-Operations Program task invalidates an earlier inspect-line reveal,
so delayed work cannot take the operator from Simulation back to Operations.

The initial combined task/selection regression passes 36 checks. Seven final
focused checks additionally cover Setup/Machine/Spindle Back/Forward loops without
new history entries, invalid task/boolean/nonfinite/out-of-range positions,
reading-position and stale-restore behavior, and a loaded program returning to
Simulation/View & playback with its inspected line retained. Four changed UI
modules pass focused package-baseline typing; full Ruff/format and architecture
contracts pass. These are source/full-app fixture receipts; installed interaction,
exact-source hosted CI and all remaining 350-item acceptance requirements remain
OPEN. Current scratch capacity remains below the retained 3.5 GiB package reserve;
no new build, installed-app replacement or machine actuation was performed.

Final task/history/Program/Setup/Machine/whole-workspace regression passes
**85 checks**, one known local SSL warning, 101.11 seconds. The hosted quality
hooks for prior source `0e30f52e9e6d292d5ce5f85673deae09bf147bd1` pass;
run 37468341272 tests remain in progress and are not claimed green. Latest task
history source requires its own hosted receipt. The full objective remains active.

## Full-pane compact profile browser checkpoint

Embedded machine/tool libraries below 760 dp now switch between a full-pane saved
profile browser and the retained editor. Selecting a saved profile or creating a
new one returns to editing; Back to editor restores the current draft. Search,
filters, sorting and 30-row paging remain available. Resizing to a wide layout
restores the side-by-side browser/editor without discarding drafts. Hidden editor
inputs release keyboard focus. The compact New action leaves space for search.

The profile/browser/draft/chrome/workspace regression passes 14 checks in 47.21
seconds. Two additional final checks at 360 and 650 dp cover wide/narrow resizing,
selection, paging through 35 cutters, unchanged stored bytes and no controller
commands (18.51 seconds). Source renders were inspected at both widths. The
illustrated-editor fixture explicitly fixes popup geometry so native backing-scale
changes cannot silently turn its intended compact check into a wide layout.
Ruff, formatting, focused module typing and architecture contracts pass.
Installed interaction and exact-source hosted CI remain OPEN. This checkpoint
advances the broader overhaul without closing the remaining controller requirements.

## Named workspace presentation layouts

Machine / Preferences and the command palette now expose a named layout library.
The palette opens a dialog without changing the originating workbench section,
so saving from Setup / Datum retains that context. Presets round trip the media
column share (25–75%), camera visibility, machine-view framing, active workbench
task and its reading position. Existing aspect-ratio sizing remains responsible
for both image panes. No geometry, physical tool state, offsets, connections or
execution state are restored. The 50/50 arrangement remains the default.

The bounded library validates names, unique records, finite values, viewport state,
50-record/256-KiB limits and task references. Writes are atomic and read back;
malformed libraries remain retained and block overwriting. Invalid task/size
restoration is rejected before presentation changes. Current camera framing is
full-frame contain; camera pan/zoom framing is still OPEN, as are drag resizing,
portable preset exchange and installed named-layout verification. This is an
implementation checkpoint for requirement 2, not its complete acceptance receipt.

Local storage validation passes 13 checks. The combined named-layout/task/history/
command regression passes 17 checks in 30.89 seconds, with one known local SSL
warning; focused typing passes six changed modules and architecture contracts
remain intact. The compact layout render was inspected; a persistent percentage
label was then added so the populated size field remains identifiable.

## DESKTOP220 installed navigation checkpoint

Frozen source `eedafd8445094fef6339c7f224f2c70e02f02843` built as DESKTOP220.
Independent archive verification initially refused the bundled 23-MB ARIALUNI font
because the verifier imposed a 20-MB member bound. The corrected verifier allows
32 MiB per member while additionally enforcing 128 MiB total and 5,000 source
members; all path/regular-member/duplicate/hash/signature checks remain intact.
Twelve verifier checks pass, including the real font and each archive budget.
The original failed verification log is retained.

Corrected independent verification at 2026-10-06T13:40:13.587831Z proves all
514 packaged source members match frozen archive SHA-256
`fe1e886f6ef8067d4ee18fa698ca8c7e7c15a10a5f3c33e5db5ca03a4cc2571f`,
with no mismatches and a strict signature. Installation readback at
2026-10-06T13:41:46.622284Z verifies the same 514 files/signature and retains
DESKTOP218 as a recovery application. Native CUA readback confirms DESKTOP220,
Program / Operations, Machine / Connect → Health, Setup / Tools and Back returning
to Machine / Health. Reported Idle C1 telemetry was 0.22 s old and camera 0.1 s old;
six captured operator JSON files remained unchanged. Health also reports a largest
UI interval of 2.48 s since launch, leaving broader responsiveness qualification
OPEN. No machine actuation was performed.

Receipts: `/private/tmp/carvera-desktop220-native-navigation-20261006.json` and
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop220-20261006/` containing
build-request, frozen archive, build log, built-verification and artifact-verification.
Hosted run 37470425616 for that exact installed source passes. Named layout source
is newer and is not included in DESKTOP220. The full 350-requirement program,
camera registration, synchronized capture and physical/backend qualification remain
OPEN and active.

Hosted run 37473355316 for named-layout source `ab0ed644ff111a6efaba84cf010f3cd59ec6a61b`
failed nine strict machine-layer typing checks. The earlier focused typing command
was weaker than that gate. LayoutRecord now types every persisted field and all
storage/validation boundaries; the corrected module passes explicit strict mypy.
The failed hosted log remains retained. Exact corrected-source CI remains OPEN.

## Direct pane sizing and portable presentation presets

The media/workbench boundary now has a focusable drag divider. Left/Right adjust
one percentage point, Shift adjusts five, and Home or double click returns to
50/50. Dragging clamps to 25–75%; numeric sizing and named-layout restoration use
the same sizing owner. Media cards now stay within their column even at its
narrowest size instead of enforcing a 180-dp width that could overflow it.

Layout import/export uses the existing file browser with `.cvlayout` files. The
same bounded schema reader serves both the local library and portable files.
Exports create a new file exclusively, independently read it back and return its
SHA-256; that digest proves byte consistency, not provenance. Imports validate all
records first, merge new names, accept identical existing records and reject
conflicting names without changing the stored library or applying a layout.
Unknown task references are still rejected before restoring presentation.
Camera pan/zoom framing and installed qualification of these changes remain OPEN.

The first wider regression exposed a retained history distance being applied after
preview geometry had been cleared. Source program inspection and viewer geometry
can legitimately be at different stages. History now captures distance only when
geometry exists, validates task state before a distance query and rejects retained
seek targets when geometry is unavailable. The failed six-check run is retained;
no fixture reset was used to hide the stale state. A dedicated empty-geometry
regression asserts rejection before page/task/index/seek changes.

Final workspace/layout/task-history/storage regression passes **74 checks**, one
known local SSL warning, 53.55 seconds. Earlier divider/exchange checks pass 19
checks. The changed storage module and scoped strict machine layer pass typing
(99 source files with imports silent); three changed UI modules pass baseline
focused typing. A separate unscoped strict attempt reports 476 errors in imported
addon modules and remains a distinct retained failure, not a hosted-green claim.
Full Ruff/format and architecture contracts pass (273 files, 1,445 dependencies,
two kept contracts). Corrected-source hosted CI and installed verification remain
independent OPEN gates. The complete controller objective stays active.

## DESKTOP221 installed presentation checkpoint

DESKTOP221 from `1d7859e38599968ac523cafd087f4a8a140abb81` was installed
and independently verified at 2026-10-06 14:00:57 UTC: 517 packaged source
files match the frozen archive, no mismatches, strict signature exit 0.
DESKTOP220 remains a recovery app. Six existing operator JSON files were
unchanged immediately after installation. Native inspection verified the
layout palette opening from Job/Operations, saving `Machining 50-50`, numeric
resizing to 40%, and restoring 50/50. The new workspace-layouts JSON was
independently read back. Native receipt is retained at
`/private/tmp/carvera-desktop221-native-layouts-20261006.json`.

The camera was live, but controller connection failed and telemetry was
unavailable; this does not close machine connection or physical qualification.
A native divider drag reached the 3D viewer and rotated its model. The source
now consumes both ordinary and grabbed dispatches for the same captured touch.
A regression exercises ordinary dispatch with `grab_current=None`. The layout
dialog now wraps its fixed-height controls in a vertical scroll viewport,
aligning them at the top and allowing compact windows to scroll. Four focused
checks pass (17.91 seconds, known SSL warning); installed qualification of these
two follow-up corrections remains OPEN because DESKTOP221 predates them.
The broader controller objective, camera registration, synchronized capture,
and camera pan/zoom framing remain OPEN.

## Camera framing source checkpoint

The camera stage now supports bounded 1–8x cursor-anchored zoom, drag pan,
double-click fit, and workbench zoom/fit buttons. A clipped viewport draws the
original shared frame texture; viewing never resamples or alters recorded camera
receipts. Source-pixel overlay projection and inverse point picking use the same
framing transform, reject letterbox/outside picks, and preserve registration
coordinates. Ordinary and grabbed movement dispatches apply each pan delta once.
Frozen registration reference views remain noninteractive.

Named layouts include camera zoom and normalized center. Existing schema-1
presets without camera framing load with full-frame defaults; invalid framing is
rejected before save or restore. Legacy files are retained until an authorized
save. Portable exports include validated framing.

Validation: 76 camera/storage/layout/workspace regression checks pass in 50.27
seconds; the final layout round-trip addition passes four focused checks in 14.47
seconds. One known SSL warning remains. A rendered regression checks that a 4x
image and its overlay stay inside the pane, adjacent pixels remain untouched and
source texture identity is retained; its PNG was visually inspected. Full Ruff
and format pass, scoped camera UI typing and strict layout storage typing pass.
The new viewport uses a stencil surface instead of Image's contain-only canvas;
the scaling assertion now checks the actual draw rectangle. The 50/50 assertion
checks usable column widths excluding borders and divider space. Failed attempts
and native DESKTOP221 evidence remain retained. Installed framing/drag acceptance
and the complete 350-requirement overhaul remain OPEN pending further evidence.

## DESKTOP222 installed camera framing checkpoint

DESKTOP222 from `8c2f6f37293e89eb34541d43cf81a6e9bced71f7` was independently
verified and installed at 2026-10-06 14:21:48 UTC: all 517 packaged source files
match the frozen archive, no mismatches, strict signature exit 0. DESKTOP221 is
retained as the recovery application. Build and installation receipts are in
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop222-20261006/`.
All seven operator JSON files were unchanged immediately after installation.

Native CUA inspection verified button zoom, drag pan, saving camera framing,
restoring the Camera inspection preset, restoring the older full-frame machining
preset, and the corrected top-aligned layout dialog. Independent JSON readback
shows the camera preset at zoom 1.25, normalized center (0.4625234096925572, 0.5).
Only workspace-layouts.json changed during the intentional save; the other six
operator JSON files remain unchanged. Native receipt:
`/private/tmp/carvera-desktop222-native-framing-20261006.json`.

Final native observation shows Idle C1 with telemetry 0.06 seconds old and live
camera 0.2 seconds old. A transient connection failure was observed earlier;
connection stability remains OPEN. No physical commands were sent. Native wheel
zoom, divider dragging and initial divider grip paint remain OPEN. Camera
registration, synchronized capture, backend/physical workflow qualification and
the full 350-requirement controller overhaul remain OPEN. Hosted run 37474499272
passed for `1d7859e`; run 37477670424 for the framing source remains in progress
at this checkpoint. These are separate source, installed and hosted gates.

## Stage pointer and keyboard ergonomics source checkpoint

The divider now highlights its full hit area on hover or keyboard focus. The
camera stage participates in focus navigation and draws a visible focus border;
+ / = zoom in, - zooms out, and 0 / Home fits the full frame. Shifted plus is
accepted; control/command combinations remain available to application shortcuts.
Frozen registration reference views remain outside focus navigation. Workbench
help exposes these commands without adding controls over the imagery.

A new integration check uses the production Window mouse provider, not direct
widget method calls. It verifies divider dragging changes the column share,
leaves 3D rotation/pan/zoom untouched, routes camera wheel events in both
directions and sends no machine commands. The first attempt lost its synthetic
texture to the live refresh timer; the retained failed log led to isolating only
the camera refresh in the fixture. 47 camera/layout/reference/empty-state and
pointer checks pass (18.11 seconds; known SSL warning), full Ruff and format pass,
and both architecture contracts pass (273 files, 1,446 dependencies). Scoped UI
typing uses a Python 3.10 target because the installed current mypy no longer
supports the project's 3.9 configuration; this does not prove Python 3.9 typing.

DESKTOP222 native divider and wheel attempts still did not demonstrate their
intended response. The Window-provider check is stronger source evidence but
cannot replace that installed gate. The short initial divider paint, installed
interaction, camera registration, synchronized capture and full controller
objective remain OPEN. The changes above require a new package and native check.

## Calibration export picker identity checkpoint

Calibration save now retains the reviewed input identity, owner identity and
registration object before opening its asynchronous file picker. The selected
path callback checks all three again, including the current fit identity, before
starting any I/O. Changed correspondences, camera source, connection generation
or replaced registration are rejected with an explicit no-file-written message.
An unchanged reviewed request still starts export. Twenty-two reference workflow
checks pass (12 seconds, known SSL warning), including each mutation and the
unchanged positive control. Full Ruff/format pass. This follow-up comes after the
DESKTOP223 frozen source `bcd956ba2d8b280e4a858a5e94c3621a3d10a467`; it is not
included in that package and requires separate installed qualification. Registration
accuracy, exposure synchronization and physical qualification remain OPEN.

## DESKTOP223 installed checkpoint and release-focus correction

DESKTOP223 (`bcd956ba2d8b280e4a858a5e94c3621a3d10a467`) completed packaging
at 2026-10-06 14:43:34 UTC: 7,932 archived members matched and strict signature
verification passed. Independent source verification matched 517 controller files;
installation verified at 14:44:43 UTC. DESKTOP222 is retained as recovery. All
seven operator JSON files were unchanged after installation and native inspection.
Receipts are in the DESKTOP223 retained build root and
`/private/tmp/carvera-desktop223-native-input-20261006.json`.

Native inspection shows Idle with fresh telemetry/live camera and a full divider
hover highlight after click. The initial short paint corrects after focus/hover,
but drag response remains unqualified. Keyboard resize and camera keyboard zoom
failed after mouse release. Both custom down handlers omitted Kivy's documented
ignored-touch bookkeeping; the global post-release focus handler then cleared
keyboard focus. A production Window-provider negative control against prior
source reproduces the focus assertion failure. Both handlers now retain the
selected focus through release. The test dispatches through the acquired keyboard
binding, verifies divider resizing and camera zoom/fit, and verifies focus transfers
between the two surfaces without machine commands. Divider paint uses base
geometry and schedules a first-layout repaint. Native initial-paint acceptance
remains OPEN until the next installed check.

The expanded stage/layout/camera/reference suite passes 52 checks (15.86 seconds,
known SSL warning). Full Ruff/format and both architecture contracts pass. Scoped
UI typing passes with the installed mypy's Python-3.9-configuration warning
retained. These corrections and the calibration picker guard postdate DESKTOP223;
they require separate package/install/native verification. Native drag/wheel,
registration accuracy, synchronized capture, backend and physical qualification,
and the full 350-requirement program remain OPEN.

## DESKTOP224 installed focus and framing checkpoint

DESKTOP224 packages source `7564c05d3b4c940de6020e92877bcd34adec0f72`,
including the release-focus correction and calibration export picker guard.
The archive SHA-256 is
`257713aae919fdb9a16aa0ab5126fa14054c07692424ada2aa9a9c1f2693c794`.
Independent verification matched 517 controller files with no mismatches and
passed strict signature verification. Installation verified at
2026-10-06 14:51:49 UTC, retaining DESKTOP223 as recovery. Build and installation
receipts are under `/Users/wes/.codex/artifacts/carvera-desktop224-20261006`.

Native inspection closes initial full-height divider painting and keyboard focus
retention after pointer release. Clicking the divider then Shift+Left resizes the
media column; Home restores 50/50. Clicking the camera then = visibly zooms the
image with a focus border; 0 restores the full frame. The final presentation is
50/50 with full camera framing. All seven operator JSON files remain unchanged
after installation and native inspection. The controller reports Idle, spindle
and feed zero, with fresh telemetry and live camera. No machine commands were
sent. Native observation receipt:
`/private/tmp/carvera-desktop224-native-focus-20261006.json`.

Native drag and wheel attempts still show no visible response and remain OPEN;
the passing production Window-provider tests do not substitute for that gate.
The export picker guard is now installed, but native mutation rejection remains
OPEN. Registration accuracy, synchronized capture, actual advanced backend and
physical workflow qualification, and the full 350-requirement objective remain
OPEN. Hosted run 37480121627 passed for the preceding `bcd956b` source; run
37482232506 for installed source `7564c05` is in progress at this checkpoint.

## Program action hierarchy source checkpoint

The idle Program workbench now has one primary file-picker action and a compact
preparation row. Pause/abort controls appear while a program is playing; their
existing execution guards remain intact. Pause labels the review action
"Review & resume". Global feed hold and STOP remain in the persistent machine
header. The setup strip retains evidence and context-specific guidance, but
does not repeat "Choose program" on an empty Program page. Switching to Scene
restores that guidance immediately, without waiting for the periodic refresh.

Context changes retain drafts and release keyboard focus from removed controls.
Unchanged refreshes do not rebuild/reparent the action row. Twenty-nine Program,
readiness and layout integration checks pass, including active/idle wrapping,
paused/resumed context, focus release and no machine-command dispatch. Full Ruff
and format pass. Scoped typing passes with the current mypy Python-3.9 warning;
the first typing attempt used an interpreter without mypy and is retained as
failed environment evidence. The first combined test run exposed delayed strip
visibility and a shared-fixture program dependency; immediate visibility and
explicit evidence-test program isolation resolve both. Installed qualification
requires a new build. Native wheel/drag, registration, synchronization, actual
backend/physical qualification and the full 350 requirements remain OPEN.
