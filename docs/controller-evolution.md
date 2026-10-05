# Controller evolution acceptance ledger

Requested scope: all 25 enhancements, including substantial workbench UI improvements.
An engine, a visible button, and an exercised machine workflow are separate gates.
No hardware qualification is claimed by this ledger. Current source is on
`feat/simulator-and-spindle-load`; the installed desktop remains a separate artifact.
The additional 25 workflow improvements are retained in
`controller-advanced-workflows.md`; they do not replace this scope.

| # | Capability | Implemented checkpoint | Remaining acceptance evidence |
|---|---|---|---|
| 1 | Contextual command palette | Search/ranking, availability recheck, keyboard popup and workbench entry | Native keyboard interaction, contextual action coverage and responsive visual review |
| 2 | Operation tree | CAM operations, line spans, tools, bounds, nominal timing, selection seeks preview | Path highlighting, observed execution progress and native layout review |
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, Program-tab export/import preview | Native roundtrip including rest stock/camera registration, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Existing numeric stock/vise placement | Picking, translation/rotation handles, calibrated hole snapping, clipping/exploded view |
| 5 | Camera registration | Distortion/intrinsic engine, bounded pose fitting, residuals; camera-tab load/fit/save and raised-stock outline | Physical correspondences and intrinsic measurements, calibration-frame image custody, calibrated-picking UI |
| 6 | Live/Preview/Compare | One-packet observed pose; Preview/Live/Compare modes, independent markers and stale-data handling | Physical CAD registration, tool reconciliation and rotary pose integration |
| 7 | Tool passports | Sectioned revision-aware physical assemblies, dimension/CAD/drawing references, raw measurement attribution, physical holder preview and hash-bound facing/hole-stage recipe links | Measured holder/gauge geometry, qualified reach, complete asset validation and complete native workflow |
| 8 | Physical ATC inventory | Capability-bounded M889 parser and command plans | Actual dispatch/readback, slot overlay and observed-versus-declared reconciliation |
| 9 | Two six-tool banks | Sequential usage planning, saved assembly selections and revision-bound preparation/measurement records | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification; preparation records do not enforce execution |
| 10 | Calibration bench | Existing repeated calibration/history | Unified bench, supported offset measurement, seating trends and actual machine exercise |
| 11 | Geometry probing | Existing probing workflows | Scene geometry selection, approach/reach preview, measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export | Scene nominal association, tolerances/repeat evidence, workbench integration |
| 13 | Surface maps | Persistent samples and bounded interpolation/exclusions; workbench provenance entry, measured-point plot, height queries, import/export and measured upper facing target | Probe transport capture and physical sample qualification; unsampled curvature remains unknown |
| 14 | Boundary-aware facing | Workbench polygon/scene-stock boundary, loaded cutter reach checks, final target/process inputs, async local program preview and cutter-bound recipes | Native complete workflow and physical travel/clearance qualification |
| 15 | Hole/thread workflow | Workbench hole locations, imperial/metric threads, optional spot/bore/chamfer stages, explicit cutter/angle/reach checks, async single-form threadmill preview and recipes | Native workflow, multi-form tooth-stack geometry, verified tapping qualification and actual backend adapter |
| 16 | Observed recipes | RPM baseline/shadow monitor and reviewed facing/hole-stage recipes bound to assembly revision, nominal cutter fingerprint and exact file hash | Actual cutting engagement/outcome evidence, complete process history and physical process qualification |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded packet recording, event replay, archive marker, exact selected-program association, declared setup restoration; session-bound asynchronous JPEG custody with digest-chained manifests, gap accounting and async receipt-time display in the main camera pane | Portable camera bundling, exposure/clock uncertainty, actual executed-program/setup and queue/execution attribution, complete historical tooling/workholding/registration assets, linked toolpath replay and installed/native acceptance |
| 19 | Collision checking | Workbench fixture/vise bounds, collision candidates and line navigation | Swept narrow phase/rotation, complete holders/machine structures and registration qualification |
| 20 | Stock removal | Canonical mm segments with bounded arcs; swept flat/ball/bull/drill/taper/chamfer/engraving/thread envelopes; rendered and persisted rest stock, workbench controls | Rotating-axis subdivision, true thread grooves, detailed holder/envelope metadata and native workflow validation |
| 21 | Recovery checkpoints | Canonical modal checkpoints, explicit verification inputs and conservative draft | Alarm/lost-position workflow, clearance/tool/WCS revalidation and qualified reentry |
| 22 | Multiple WCS | Existing coordinate backend | Stock instances, probing/offset transactions, repeat-part planner |
| 23 | Rotary workspace | General rotary forward geometry and limits | Chuck/jaws/tailstock setup, G93 program playback, indexed/wrapped/simultaneous validation |
| 24 | Capability adapters/IO | Versioned actual/declaration evidence, bounded Carvera command plans, lifecycle receipts | Transport adapters, fresh observed evidence, peripheral UX and verified acknowledgements |
| 25 | General five-axis | Head/table forward chains, pivots, limits, tool/work transforms, bounded inverse solving and angle unwind | Singularity handling and seed/branch review UI, indexed 3+2 workflow, declared/observed TCP and actual capable backend |

## Verification checkpoints

- New pure-engine tests cover archive corruption/traversal, modal parsing, bank planning,
  restrictive capability inference, command invocation rechecks, stock subtraction and kinematics.
- Import/export and operation navigation require native UI exercise before their UI gate closes.
- Collision candidates are conservative bounding volumes, not certified clearance.
- Voxel removal is approximate at the selected resolution; changing orientation requires subdivision.
- Firmware release capability metadata does not establish installed firmware or authorize a physical run.

Source checkpoint validation: 847 passed, 15 skipped in the broad suite; 7 focused UI/workflow tests passed after fixing the Console search alias. Ruff lint/format and both import architecture contracts passed. Skipped visual reference tests do not establish native visual acceptance. No new package install, controller command or physical run is claimed.

Second source checkpoint: canonical segment production, rendered stock removal, residual snapshots, camera calibration controls and fresh observed pose modes are integrated. Surface/hole generators remain engines awaiting workbench integration. 35 focused workbench tests and 41 package/camera workflow tests passed; final broad suite passed 916 tests with 15 skips; DESKTOP28 native proof pending.

Third source checkpoint integrates surface/facing and threaded-hole planners into Setup, a shared styled local artifact browser, and per-machine persistent Scene drafts (stock, preview work offset, vise placement, component choices/visibility). Profile restoration batches geometry into one final rendered scene. Integration metadata stores are isolated from operator data. DESKTOP28 was installed and observed connected/Idle with fresh telemetry, physical T1/TLO and live Ubuntu camera; Preview/Live selector and camera registration controls were exercised visually. DESKTOP29 packaging and native planner/restart checks remain pending. Final broad suite: 967 passed, 15 skipped, 7 warnings (182.37s); Ruff lint/format and both import architecture contracts passed. Skips do not establish visual acceptance. Initial scene-timeout run is retained as failed-attempt evidence.

DESKTOP29 native checkpoint: built from `25d13b81cd104ed33a3394d56c0ca965687e6906`,
strict signature verification passed, installed and restarted. Saved camera-estimated
stock, vise placement and enclosure visibility restored; controller connected/Idle,
T1/TLO 50.480 mm, fresh telemetry and live Ubuntu camera observed. Facing form and
recipe browser rendered. Receipt and screenshot are in
`/Users/wes/Downloads/carvera-desktop29-20261003/`. This does not qualify physical
stock registration, cutting, or a complete planner workflow with measured tooling.
Native review found stock translucency difficult to read, planner disclosure
scroll jumps and a missing first-use Jobs directory. Subsequent source fixes add
stock volume edges, put planners first in Setup, reveal their disclosure heading,
initialize the owned Jobs folder and restore saved measurement controls. Focused
regressions: 36 passed. Broad suite: 971 passed, 15 skipped, 7 warnings in 139.72s;
Ruff lint/format and both architecture contracts passed. Packaging/native
acceptance of these fixes remains open.

DESKTOP134 checkpoint (source `03e651d`): installed manifest/signatures and
DESKTOP133 recovery verified. Native hole-stage recipe linking exercised explicit
stage selection, required provenance, save and independent event/hash readback.
Missing loaded pilot-drill restoration was rejected. Operator data was restored
and the app returned to Live with fresh reported telemetry/camera. Successful
native restoration with every required cutter loaded and physical workflow
qualification remain open; none of the original 25 requirements closes here.
See `tool-assembly-history.md` for the bounded acceptance receipt and gaps.

DESKTOP134 positive restoration checkpoint: compatible declared pilot drill and
single-form threadmill profiles were loaded through the native toolset library;
restoration populated the hole planner (1/4-20, G54, `10 20 8 6`) and reported
matched cutter geometry. Generating the preview then closed the UI with an
`AttributeError` because `Makera.loading_file` was not initialized before its
first load. The failure log and shutdown process sample are retained in
`/Users/wes/Downloads/carvera-desktop134-positive-20261004/`. Operator stores and
configuration were restored and verified. Source now initializes loading state
and reveals the hole-planner heading after disclosure layout. The strengthened
integration suite exercises the real local viewer handoff; 29 tests passed,
including generated drill/thread stages without machine commands. Ruff and
format checks passed. Packaging and native generation acceptance remain open.

DESKTOP135 checkpoint (source `de0afa7`): installed source manifest and strict
signature verification passed. Native recipe restoration and local drill/thread
generation succeeded without the first-load crash. The operation tree exposed
17 unresolved threadmill motion lines: generated arcs did not declare their
center mode. Source now emits G91.1 on a separate block followed by G90 before
any motion. The inspected official and community Robot.cpp handlers treat G91.1
as relative endpoint mode and always use incremental IJK centers; the following
absolute block is therefore required. This is source compatibility evidence,
not installed firmware or cutting qualification. Regression checks require all
generated arc lines to produce canonical segments while retaining unknown
initial approaches. Native acceptance of the corrected arc preview remains open.

DESKTOP136 native checkpoint (source `e31f1fb`): package, installed manifest and
strict signatures passed; DESKTOP135 recovery retained. Native local program
inspection and preview loaded the corrected 1/4-20 sample. Selected threadmill
operation shows 22 resolved motion lines and zero unresolved (previously 17
unresolved); its remaining warning is unknown dwell-unit timing. Screenshot,
program/hash, pinned firmware sources and receipts are retained in
`/Users/wes/Downloads/carvera-desktop136-20261004/`. Eight operator stores and
configuration were restored after preview. This closes the generated arc-mode
defect only; physical tooling, registration, cutting and the full hole/thread
workflow remain open.

Simulation tool readiness now lists all missing/incomplete required cutter
profiles before calculation, disables calculation until dimensions are supplied,
and routes each numbered issue to tool comparison. Program/scope/profile-keyed
caching avoids scanning all motion segments on repeated telemetry refreshes;
the UI check performs no CAD disk I/O. Calculation still verifies asset bytes
and builds full registered envelopes. An end-to-end generator/interpreter/tool
model/material-removal regression covers explicit drill and threadmill profiles;
true thread grooves remain unresolved by the outside-diameter model. Native
acceptance of the new readiness controls remains open.

DESKTOP137 native readiness checkpoint (source `8cc391d`): installed manifest
and strict signatures passed with DESKTOP136 retained as recovery. Native
simulation review listed both missing cutters, routed T3 to tool comparison,
then reduced issues from two to one to zero as drill-only and complete preview
toolsets were loaded. Calculation remained disabled until both required profiles
were ready. Screenshots and `native-acceptance.json` are retained in
`/Users/wes/Downloads/carvera-desktop137-20261004/`. Eight operator stores and
configuration were restored before relaunch; the stores still matched afterward.
The app returned to Live with fresh reported Idle/T1/TLO telemetry and Ubuntu
camera. No program upload or motion was performed. This closes cutter-readiness
UI acceptance only; stock/path frame review, full native material removal, true
thread geometry and physical workflow qualification remain open.

Stock/path alignment source checkpoint: simulation now reviews continuous +Z
cutting envelopes against declared stock before calculation, reports possible
engagement or a complete miss, and exposes stock bounds in program millimetres
with a direct Scene placement/work-offset review action. The review runs off
the UI thread, is cached by program/scope/tools/stock, cancels superseded work
and rejects older results. Rapid travel is excluded; tooltip position alone
does not substitute for the cutting envelope. Air-cutting previews remain
available. This is conservative geometry guidance, not material-removal,
clearance or physical-registration acceptance. Packaging and native acceptance
of these controls remain open; DESKTOP137 remains the installed build.

DESKTOP138 native checkpoint (source `cc1b62f`): installed manifest and strict
signatures passed, with DESKTOP137 retained as recovery. Native stock/path review
reported a complete miss against saved stock, opened Scene review, and then
reported possible engagement on 97 of 98 cutting segments against a temporary
10 × 10 × 8 mm stock volume. At 1 mm grid resolution the local drill/thread
preview reported 236 mm³ removed, 564 mm³ remaining and 66 conservative clearance
candidates. Three unresolved approach/travel lines (5, 11, 12) were excluded;
thread grooves and holder clearance remain unresolved. Native rest-stock save
was exercised; independent decompression verified the occupancy hash and all
800 cells, with 564 occupied. Receipts and screenshots are retained in
`/Users/wes/Downloads/carvera-desktop138-20261004/`. Operator stores/configuration
were restored; all eight stores still matched after relaunch, and Live viewing
returned with fresh reported Idle/T1/TLO and camera. No upload or motion occurred.
This closes the bounded native stock-alignment/calculation/save checkpoint, not
the full simulation requirement or physical qualification.

Native review exposed two usability defects: computed results stayed below the
viewport, and saving rest stock replaced the computed summary. Source now reveals
results after layout when the operator is still in the same task, preserves the
summary with a separate save receipt, and uses readable stock-bound text instead
of a missing arrow glyph. Installed acceptance of these source changes is open.

Result/save UX regression passed the real workbench calculation, saved snapshot
reconstruction, preserved summary and no-machine-command assertions (1 passed,
1 existing locale warning; 13.25 s). Ruff lint/format and diff checks passed.
The external-volume startup timeout and initial JSON list/tuple assertion failure
are retained alongside the final passing log in the DESKTOP138 evidence folder.
The source UI fixes await packaging/native acceptance.

DESKTOP139 native checkpoint (application source `9baf389`, navigation regression
revision `0f403c2`): installed manifest and strict signatures passed, with
DESKTOP138 preserved as recovery. Computation revealed the result summary in the
visible report area; native rest-stock saving preserved that summary and displayed
a separate save receipt. Independent decompression verified 800 cells, 564
occupied and 236 removed, the occupancy digest and the loaded program hash. Three
source scenarios passed: remaining on Simulation, moving to Operations and moving
to Scene while calculation finishes. Completion did not steal the selected task.
Receipts and screenshots are retained in
`/Users/wes/Downloads/carvera-desktop139-20261004/`. Normal operator stores and
configuration were restored; all eight stores matched after relaunch. Live viewing
returned with fresh reported Idle/T1/TLO 50.480 mm and Ubuntu camera. No upload or
motion occurred. This closes result-reveal/save-summary UX acceptance only; full
material removal, holder clearance, thread grooves, physical qualification and
the original 25 complete workflows remain open.

Tab-switch focus checkpoint: outgoing keyboard ownership is released through
Kivy's keyboard-owner registry and ancestor chain, avoiding a walk over every
control in the old page. Persistent toolbar focus remains active and field drafts
are preserved. Three focused navigation regressions passed (17.55 s); Ruff
lint/format passed. The first attempt's window-parent loop, subsequent storage
read stall and process samples are retained in the DESKTOP139 evidence folder
and `/tmp/carvera-focus-stall.txt`. This removes an avoidable traversal; it does
not establish the cause or resolution of the reported multi-second stall.
Packaging and native responsiveness acceptance of the focus change remain open.
