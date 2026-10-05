# Controller evolution acceptance ledger

Requested scope: all 25 enhancements, including substantial workbench UI improvements.
An engine, a visible button, and an exercised machine workflow are separate gates.
No hardware qualification is claimed by this ledger. Latest source work is on
`feat/compact-recording-20261005` in the owned compact-recording worktree;
`feat/simulator-and-spindle-load` and the installed desktop are separate checkpoints.
The additional 25 workflow improvements are retained in
`controller-advanced-workflows.md`; they do not replace this scope.

| # | Capability | Implemented checkpoint | Remaining acceptance evidence |
|---|---|---|---|
| 1 | Contextual command palette | Search/ranking, availability recheck, keyboard popup and workbench entry | Native keyboard interaction, contextual action coverage and responsive visual review |
| 2 | Operation tree | CAM operations, line spans, tools, bounds, nominal timing, preview selection and revision-bound whole-operation path highlighting | Observed execution progress and installed/native interaction and layout acceptance |
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, Program-tab export/import preview | Native roundtrip including rest stock/camera registration, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Exact rendered-surface picking, stock/vise XY and Z handles, CAD-pivot vise Z rotation, declared-center stock Z rotation, independent grid/angle snapping, actual displayed cutter picking, async component framing and reviewed drafts with persistence/cancel safeguards | Native interaction acceptance, general tilted rotation, calibrated hole snapping, clipping/exploded view |
| 5 | Camera registration | Distortion/intrinsic engine, bounded pose fitting, residuals; camera-tab load/fit/save and raised-stock outline | Physical correspondences and intrinsic measurements, calibration-frame image custody, calibrated-picking UI |
| 6 | Live/Preview/Compare | One-packet observed pose; Preview/Live/Compare modes, independent markers and stale-data handling | Physical CAD registration, tool reconciliation and rotary pose integration |
| 7 | Tool passports | Sectioned revision-aware physical assemblies, dimension/CAD/drawing references, raw measurement attribution, physical holder preview and hash-bound facing/hole-stage recipe links | Measured holder/gauge geometry, qualified reach, complete asset validation and complete native workflow |
| 8 | Physical ATC inventory | Capability-bounded M889 parser, explicit query transport, bounded connection-scoped receipts and paginated configured-pocket/local-declaration review and nominal configured-target overlay and validated historical receipt exchange | Broader native viewport/orbit coverage and physical assembly/occupancy reconciliation |
| 9 | Two six-tool banks | Sequential usage planning, saved assembly selections, revision-bound preparation/measurement records, separate post-placement mapped receipts and fresh current-spindle TLO comparison | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification; preparation records do not enforce execution |
| 10 | Calibration bench | Unified assembly/tool-number evidence bench with repeatability statistics, revision/source-bound offset changes, post-placement receipt comparison and fresh current-spindle TLO; existing repeated calibration | Native bench acceptance, integrated measurement launch/transport, reference measurements and physical seating/offset qualification |
| 11 | Geometry probing | Existing probing workflows; exact nominal triangle/point/normal selection and ball-center approach/search/retract planning with projected scene review | Qualified reach/clearance, registered probe transport, measurement custody and measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export; retained nominal surface/setup association, workbench operator-entered receipts, signed limits/repeat statistics, reviewed portable exchange and CSV/HTML reports | Registered compensated machine receipt capture, richer fitting/tolerances, complete native workflow and physical qualification |
| 13 | Surface maps | Persistent samples and bounded interpolation/exclusions; workbench provenance entry, measured-point plot, height queries, import/export and measured upper facing target | Probe transport capture and physical sample qualification; unsampled curvature remains unknown |
| 14 | Boundary-aware facing | Workbench polygon/scene-stock boundary, loaded cutter reach checks, final target/process inputs, async local program preview and cutter-bound recipes | Native complete workflow and physical travel/clearance qualification |
| 15 | Hole/thread workflow | Workbench hole locations, imperial/metric threads, optional spot/bore/chamfer stages, explicit cutter/angle/reach checks, async single-form threadmill preview and recipes | Native workflow, multi-form tooth-stack geometry, verified tapping qualification and actual backend adapter |
| 16 | Observed recipes | RPM baseline/shadow monitor and reviewed facing/hole-stage recipes bound to assembly revision, nominal cutter fingerprint and exact file hash | Actual cutting engagement/outcome evidence, complete process history and physical process qualification |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded status recording, continuous receipt playback with explicit gap/boundary stops, event replay/archive marker, exact selected-program association, declared setup custody/restoration; session-bound JPEG recording, validated bundles and native camera import/display/return-live; historical scene/tool restoration source-tested | Native receipt playback and corrected setup capture/restoration, calibration-image custody, exposure/clock qualification, actual execution attribution, linked toolpath replay and complete recorded-run workflow |
| 19 | Collision checking | Workbench fixture/vise bounds, collision candidates and line navigation | Swept narrow phase/rotation, complete holders/machine structures and registration qualification |
| 20 | Stock removal | Canonical mm segments with bounded arcs; swept flat/ball/bull/drill/taper/chamfer/engraving/thread envelopes; rendered and persisted rest stock, workbench controls | Rotating-axis subdivision, true thread grooves, detailed holder/envelope metadata and native workflow validation |
| 21 | Recovery checkpoints | Canonical modal checkpoints, explicit verification inputs and conservative draft | Alarm/lost-position workflow, clearance/tool/WCS revalidation and qualified reentry |
| 22 | Multiple WCS | Coordinate backend; declared G54–G59 arrays, plans and full-array preview; source-tested multi-stock subtraction and frame-aware path/cutter playback with reversible file/historical restoration | Installed/native multi-stock calculation and playback, persisted results, probing/offset transactions and repeat execution/inspection |
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

Navigation timing source checkpoint: tab selection now retains bounded phase
timings for history, focus release, page activation and styling, plus separate
next-clock-turn and window-flip observations. Periodic UI refreshes retain their
own bounded totals and readiness/tool/simulation subphases. Machine connection
health displays the timings; the existing Spindle diagnostics export includes
both records and their limits. Capture performs no disk I/O or machine commands.
Failed and superseded selections cannot claim a later render observation.
The final source suite passed 21 tests (138.58 s, one existing locale warning),
including navigation history, focus preservation, event binding and export
readback. Ruff lint/format and diff checks passed. The first run's seven pure
passes and three Kivy tooltip/font startup timeouts are retained in
`/tmp/carvera-navigation-timing-tests.log`; passing output is in
`/tmp/carvera-navigation-timing-final-tests.log`. See `ui-responsiveness.md`.
DESKTOP140 predates this instrumentation; packaging/native workload measurement
and resolution of the reported stall remain open. No original requirement closes.

Combined recording/navigation source checkpoint (`02903ca`): integrated timing
retains camera-writer shutdown and measures active replay refresh separately.
The combined recording/setup/job/camera/navigation/export suite passed 84 tests
(95.65 s, one existing locale warning). Receipt:
`/tmp/carvera-recording-navigation-combined-tests.log`. Ruff lint/format and diff
checks passed. This remains a source checkpoint; neither recorded-run native
acceptance nor the tab-freeze requirement is closed.

Historical restoration source checkpoint: retained fixture/vise/tool assets now
restore into an explicitly labeled local preview, with archived-cutter selection
and reversible previous-scene restoration. Artifact preparation runs off the UI
thread and stale selections cannot publish. Exact original program bytes and
normalized inspector identity are validated separately. The final affected suite
passed 80 tests (67.30 s); wide/narrow renders were reviewed. See run-recording.md.

Retina dimension diagnostics exposed repeated test-window growth: framebuffer
pixels were being restored through a logical-size setter. Tests now retain
Window.system_size, and application close saves logical window dimensions
independently of widget dp scaling. This source correction does not prove the
reported tab stall resolved. Failed diagnostics remain preserved.

DESKTOP141 artifact verification passed at 2026-10-05T05:41:37Z: source revision
be8c6476735c0fee4077546ef517fbb92c803592, application checkpoint 02903ca, version
2.1.0-DESKTOP141. Independent source/staged/built checks reported no mismatches
(452/455/455 files); strict signature verification passed. Receipt:
/Users/wes/Downloads/carvera-desktop141-20261005/built-verification.json.
Later installed verification at 2026-10-05T06:06:44Z confirmed DESKTOP141,
455 installed files without mismatches and strict signatures. Receipt:
/Users/wes/Downloads/carvera-desktop141-20261005/artifact-verification.json.
Historical restoration and logical-size changes are later source work and are
not in this package. No original requirement is closed by these checkpoints.

DESKTOP142 artifact checkpoint: build process completed with exit zero. Independent
verification at 2026-10-05T07:12:54Z checked source revision
`88d31dd35209fcf970fd508e4bf302265225e3f4`, 455 source files and 458 staged/built
files without mismatches; strict signatures and version checks passed. Receipt:
`/Users/wes/Downloads/carvera-desktop142-20261005/built-verification.json`.
Installation was not attempted: the native computer-use bridge failed to start
both before and after a session reset. The existing installed controller was
not quit or replaced. The corrected setup binding, newer compact replay/camera
controls, async diagnostics export and mapped bank comparisons are later source.

DESKTOP143 now builds from a separate frozen checkout at `8a695a5`, including
those later changes. Its owned process is retained for subsequent terminal
readback and verification; starting the build does not establish a usable artifact,
installation, native responsiveness or physical workflow qualification.

DESKTOP143 artifact verification passed at 2026-10-05T07:43:29Z: source
`8a695a5b089683b40ac91bd47d4247fff5828f61`, 456 source files and 459 staged/built
files without mismatches, matching version and strict signatures. Receipt:
`/Users/wes/Downloads/carvera-desktop143-20261005/built-verification.json`.
Installation remains unattempted. Native access subsequently recovered; installed
DESKTOP141 displayed connected/Idle, fresh reported telemetry and Ubuntu camera.
That observation does not qualify the newer source or physical setup.

Direct scene interaction source checkpoint: exact indexed-triangle selection runs
off the UI thread and rejects stale scene/view results. Stock/vise handles create
XY or Z placement drafts with grid snapping, retaining the existing reviewed
apply/cancel and per-machine persistence path. Full homogeneous unprojection
replaces unsuitable affine matrix helpers. The focused interaction suite passed
22 tests (46.95s, one existing locale warning); existing setup-editor regressions
passed in the earlier combined run. Failed projection attempts and test-fixture
errors remain in `/tmp/carvera-scene-interaction-tests.log` and
`/tmp/carvera-scene-interaction-final-tests.log`. Both architecture contracts
passed (216 files, 936 dependencies). See scene-interaction.md for remaining scope.

Final scene/window-frame checkpoint: 23 focused tests passed (77.37s, one
existing locale warning), including a real rendered-stock handle drag into a
reviewed draft, cancellation and task visibility. Window-space overlay and touch
conversion now share the exact GL viewport origin; the earlier visual offset was
corrected. Screenshot `/tmp/carvera-scene-handle0004.png` was reviewed. Final
receipt: `/tmp/carvera-scene-window-frame-tests.log`. Ruff lint/format and both
architecture contracts passed. Compact interaction controls precede the component
inspector. Native installed acceptance and the remainder of requirement 4 stay open.

Vise rotation source checkpoint: 28 combined tests passed, with actual projected
ring gestures about the registered CAD pivot and reviewed apply/cancel/save.
Twelve pure checks passed after normalizing angular vectors for overflow safety.
The compact Scene panel now exposes independent translation/angle snap controls.
The source render was reviewed; both import contracts passed. Receipts and
remaining scope are in scene-interaction.md. DESKTOP144 is building from frozen
`4aa016989ab2303f7fac15e945f7b7d7e1a9646f` and does not include this later rotation
work. No original requirement closes at this source checkpoint.


Displayed cutter/frame source checkpoint: actual shader-transformed cutter/holder
triangles participate in selection with machine CAD shown or hidden. Clip-range
selection and geometry/view identity checks reject stale results, including a tool
replacement using the same number. Frame selected computes bounds off the UI thread
and preserves a camera adjustment or task change made during the request. The
combined interaction suite passed 35 tests (173.86s); the later task-context guard
has a focused regression receipt in `/tmp/carvera-framing-context-tests.log`.
See scene-interaction.md. These changes are later than DESKTOP144's frozen source;
installed acceptance and the remainder of requirement 4 remain open.


Final review added a Scene-task guard to asynchronous framing. Its focused test
process is still live but has not reached collection: sampling shows Python startup
blocked in a filesystem directory read. Receipt log:
`/tmp/carvera-framing-context-tests.log`; process sample:
`/tmp/carvera-framing-startup-sample.txt`. This added regression remains OPEN;
the earlier 35-test result does not prove the later guard. Local Ruff lint/format,
diff checks and both architecture contracts passed after the guard was added.
DESKTOP144's original build remains live in code signing; no replacement build or
installation was started. A fresh native observation still showed DESKTOP141,
Idle, fresh reported telemetry and camera. No machine commands were issued.


Final scene context/identity source acceptance: four focused tests passed (92.36s)
and exited zero, closing the added task-change framing regression. The cutter
inspector describes the displayed mesh identity and flags a different pending tool,
rather than attributing the requested tool's dimensions to old geometry. Receipt:
`/tmp/carvera-frame-inspector-final-tests.log`. The earlier fixture timeout and
cleanup failure remain preserved. Ruff and both architecture contracts passed.
Stock/general rotation and installed scene interaction acceptance remain open.


Oriented-stock backend checkpoint: fixed Z rotation/pivot now carry through cell
centers, sweep range selection, continuous material removal, rest-stock vertex and
normal rendering, clone/target comparison and schema-2 rest-stock snapshots. The
combined engine/preview suite passed 41 tests (1.32s); both import contracts and
Ruff checks passed. Receipt: `/tmp/carvera-oriented-stock-render-final-tests.log`.
Scene declarations/editor/persistence, job/recording setup binding and facing/path
integration have not yet adopted the parameter. Requirements 4 and 20 remain open.


Declared stock orientation integration: center-pivot program-Z rotation now flows
through the Scene editor/schema-2 save/restart, declared stock mesh/wireframe,
simulation context/calculation/rest-stock reconciliation, portable job declarations,
recording bindings, historical geometry and copied facing footprint. Legacy Scene
schema 1 defaults to zero and is migrated only on save. Geometry, persistence,
custody and reviewed editor source tests passed; see scene-interaction.md for exact
receipts. AABB engagement review remains conservative. Direct rotation gestures,
tilted frames and installed/native workflow acceptance remain open.


Direct stock rotation gesture source checkpoint: the projected ring uses the declared
stock center even with asymmetric rest geometry. Snapped release opens a reviewed
stock-angle draft; Apply persists, Cancel preserves setup, retained drafts are not
overwritten and no controller commands are sent. The combined interaction suite
passed 40 tests (179.40s); the additional residual-pivot/retained-draft check passed
(15.09s). The source render was reviewed; Ruff and both import contracts passed.
Receipts are in scene-interaction.md. Installed acceptance and the rest of requirement
4 remain open; the original DESKTOP144 build was not restarted or replaced.

Nominal surface-reference and measurement source checkpoint: retained source
triangle/point/normal references reject stale geometry/setup/cutter/pose. Unit-aware
surface review calculates ball-center approach, contact, search limit and retract,
with explicit winding reversal and normal/axis travel. A projected scene line hides
with its group/task and is discarded on changed setup/geometry/pose. Signed
local-plane deviation requires an explicitly supplied registered compensated
ball-center position; no firmware trigger is silently substituted. No transport,
offset or datum mutation exists in this planner. The combined engine/interaction
suite passed 53 tests (206.48s, one existing locale warning), before final layout
and overlay-visibility refinements. Receipt: `/tmp/carvera-surface-measurement-tests.log`.
Two final review tests passed (18.05s), followed by two narrow-window checks
(15.33s); wide/narrow source renders were reviewed. Ruff and both architecture
contracts passed. Installed/native acceptance remains separate. See scene-interaction.md.
Requirements 4, 11 and 12 remain open.

DESKTOP144 artifact verification passed at 2026-10-05T09:15:13Z: frozen source
`4aa016989ab2303f7fac15e945f7b7d7e1a9646f`, 461 source and 464 staged/built files
without mismatches, matching version and strict signatures. Receipt:
`/Users/wes/Downloads/carvera-desktop144-20261005/built-verification.json`.
Installation was not attempted; DESKTOP141 remains installed. Later rotation and
nominal surface-measurement work are absent from DESKTOP144.

Retained surface inspection source checkpoint: Scene planning now saves immutable
nominal/setup declarations; Setup opens retained feature/receipt history, signed
normal limits and repeat statistics. Raw triggers and missing registration or
compensation references remain unevaluated. Local records identify operator-entered
evidence and the explicit coordinate frame; the content hash is not calibration or
physical-registration proof. First-load/save/reload run off the UI thread, duplicate
gestures are bounded, closed views do not reopen and feature changes clear inputs.
The combined suite passed 34 tests (97.13s); three later reload/UI checks passed
(22.71s). See surface-inspection.md for receipts, scope and remaining work.
Installed/native acceptance, transport/measurement qualification and requirements
11/12 remain open. DESKTOP141 remains installed.

Inspection exchange/report source checkpoint: exact JSON-normalized feature/receipt
bundles, readback-hashed exports, signed-plane CSV and printable HTML reports are
integrated into the records view. Selected/all-feature export and reviewed import
were exercised in source UI tests. Import rechecks reviewed source bytes, rejects
identity conflicts and merges independent receipts idempotently without changing
machine setup/offsets. The final combined suite passed 38 tests (23.64s), with later
report-column and all-feature scope checks. Offline print QA corrected stacked
metrics and appendix/table ordering; both final pages were reviewed. Browser
local-file navigation was blocked, so browser rendering remains unverified.
See surface-inspection.md for exact receipts. Installed/native and physical
acceptance remain open; the original 25 complete workflows are not closed.


DESKTOP145 installed/native scene checkpoint: source `33de5ab` was independently
verified and installed at 2026-10-05T10:26:29Z (469 installed files, no manifest
mismatches; built/installed/recovery strict signatures passed). Native component
picking selected stock triangle 10 with +Z winding normal. Surface measurement
review displayed nominal surface, ball-center, approach/retract and search-limit
coordinates; local preview and Frame selected were exercised, leaving Scene hid
the overlay, and Fit view restored full machine framing. All nine operator-store
baseline entries still matched after review. Reported Idle/T1/TLO 50.480 mm, zero
RPM/feed, fresh telemetry and live camera were observed. Receipt:
`/Volumes/Wes Storage/Archives/Downloads/carvera-desktop145-20261005/native-scene-measurement-acceptance.json`.
No explicit motion/upload/offset/calibration/tool-change command was issued. This
closes this bounded picking/planning/framing UI checkpoint; native rotation/drag,
retained inspection exchange, measured registration and physical probing remain
open. Later operation highlighting (`3bf0ff5`) is absent from DESKTOP145.


ATC coordinate-readback source checkpoint: explicit M889 dispatch and bounded
header/Tool/ok collection now integrate with a lazy six-row Setup panel. Local
assignments, configuration coordinates and unknown physical contents remain
distinct. Reconnect, timeout, stale/busy state, failed transport and ambiguous
response checks passed. Final workspace/receive/navigation/pocket suite: 48 passed
(60.89 s); narrow/wide source renders reviewed. See atc-inventory.md for exact
receipts and limits. Installed/native query, slot overlay and physical tool/pocket
reconciliation remain open; requirement 8 is not closed.


ATC/scene source verification follow-up: retained receipt exchange passed 52
engine/transport tests and two narrow/wide historical UI checks. The complete
scene/panel run passed 34 test bodies with one test-mock teardown error; its
corrected exact visibility/cache regression passed separately, including finite
empty-bounds framing. Failed logs remain retained. Source now prevents periodic
visibility synchronization from triggering scene edits and fits cached rendered
bounds. Native ATC receipt/overlay acceptance and the reported tab freeze remain
OPEN. See atc-inventory.md and ui-responsiveness.md for exact receipts.


DESKTOP148 installed/native ATC checkpoint: frozen source
`787841a5ad304e83c01cc174753aee7e5ce98520`, version 2.1.0-DESKTOP148,
474 packaged/installed controller files without mismatches and strict signatures
verified. DESKTOP147 failed native startup on a missing packaging namespace;
it was preserved and DESKTOP145 was restored before fixing the dependency,
regenerating/checking the lockfile and rebuilding. DESKTOP145 recovery remains
available. Native connection to C1/2.1.0c at 192.168.0.79:2222 succeeded. Explicit
ATC readback returned seven configured positions (T0 through T6); native save,
independent hash/semantic validation, historical import and T6 pagination passed.
A reconnect invalidated current inventory without turning the saved record into
live evidence. All nine operator-store baseline entries still matched. Receipt:
/private/tmp/carvera-desktop148-20261005/native-atc-receipt-acceptance.json.
No motion, upload, tool change, offset or calibration was issued. Native target
overlay, physical rack registration/occupancy, camera-forward recovery and the
reported tab freeze remain OPEN. No original complete requirement closes.

Later source `ed05921` reveals connection controls directly from the header action
and reveals the configured-position panel when opened. A rendered regression
passed (18.26 s), verifying visible Connect profile controls, no machine commands
and cancellation of the reveal after changing tasks. Receipt:
/tmp/carvera-connection-navigation-final-tests.log. These entry-point improvements
are not in DESKTOP148 and require installed/native acceptance.

DESKTOP149 checkpoint: asynchronous artifact-path validation/selection and the
connection/ATC entry-point reveals are installed from 14498f8. Eleven focused
picker/navigation tests passed; installed manifest/signatures and native import/
entry-point behavior were verified. Native ATC target show/page/hide also worked,
but full-machine labels overlap and remain pending UI refinement. A connection-loss
popup recurred during path entry and automatically recovered; neither the tab
freeze nor broader native performance is closed. Camera remains unavailable.
All nine operator-store baseline entries matched. Receipt:
/private/tmp/carvera-desktop149-20261005/native-picker-navigation-acceptance.json.
No physical action/qualification or complete original requirement closes here.

DESKTOP150 installed/native checkpoint: source 968205698f6e9a7afe6e18839b37cd6cfdf1af4d,
474 installed controller files without mismatches and strict signatures passed;
DESKTOP149 recovery preserved. The full-machine ATC caption-overlap defect was
corrected and reviewed natively: T0-T5 captions are separated with anchored
leaders, T6 pagination and hide work. Four focused layout/rendered tests passed
(19.45 s, one SSL runtime warning); all nine operator-store entries matched.
Receipt: /private/tmp/carvera-desktop150-20261005/native-atc-caption-acceptance.json.
The app was left Live with fresh reported Idle telemetry, overlay hidden and
camera unavailable. Short-pane/orbit breadth and physical registration/occupancy
remain OPEN; no original complete requirement closes. The receive-path blocking
storage audit is recorded in ui-responsiveness.md for the next implementation.


Telemetry persistence responsiveness checkpoint: the receive-thread blocking
storage path is replaced by a bounded background writer, with gap/loss/error and
shutdown observations displayed/exported in Spindle diagnostics. The final
affected suite passed 34 tests (15.57 s), including deliberately stalled storage
while status parsing and a UI-clock age read proceed. See ui-responsiveness.md for
receipts and durability limits. This is source validation; the native intermittent
freeze and all original complete requirements remain open.


DESKTOP151 installed/native telemetry checkpoint: frozen source
8d533eea02a7dd91ea587b61a27dadc8e7444827; installed at
2026-10-05T14:04:06.293880Z, 475 files without manifest mismatches and strict
signatures passed. DESKTOP150 recovery is retained. Native Spindle review displayed
background storage counts; native export to internal storage completed and independent
JSON/log readback verified the persistence snapshot and connection generations.
All nine operator-store baseline entries still matched. Receipt:
/private/tmp/carvera-desktop151-20261005/native-telemetry-acceptance.json.

The native responsiveness defect is not resolved: opening the export picker timed
out twice before recovering; path paste again triggered connection loss and automatic
reconnection. The saved observation stream contains a 73.671468959-second maximum
arrival gap in the retained initial readback. Zero log-queue losses does not mean
zero missed machine packets. During the stall, sample 75986 shows the main rendering
thread and other Python threads waiting in PyEval_RestoreThread, with one Python
thread inside lstat. This is a concrete process-wide blocking lead, not proven
attribution to a particular Python source call. Process sample:
/private/tmp/carvera-desktop151-20261005/native-export-process-sample.txt.
Next: qualify the exact blocking path and isolate filesystem work from the process
where needed; a thread alone cannot protect against an operation holding the GIL.
Do not suppress the received-status timeout. The app was left Live/Idle with fresh
reported status, no program selected and camera unavailable. No motion, upload,
tool change, offsets or calibration were issued. No original requirement closes.


Isolated artifact-browser source checkpoint: folder resolution/listing, Jobs creation
and selection existence checks now run in a separate metadata-only process. Source
and frozen worker entry points dispatch before Kivy/controller imports. Requests
have a four-second deadline and cancel on changed navigation/dismissal; the parent
retains at most two helper slots, including kernel-blocked children that cannot yet
be reaped. Timeout/error messages keep selection disabled and permit another
location. Existing one-active/one-latest scheduling and stale-selection guards remain.

A RecycleView replaces the 250-widget cutoff with reusable visible rows, preserving
all matching entries, folder-first sorting and selected filenames. Text is left
aligned and shortened to fit. The 1,500-entry rendered regression reaches the last
entry, filters back to the first, verifies rebinding and rejects selection after
dismissal. Final combined suite: 23 passed (27.72 s, one SSL warning); later frozen
stream/bootstrap adaptation: seven engine/bootstrap tests passed (2.05 s). Receipts:
/tmp/carvera-isolated-picker-final-tests.log and
/tmp/carvera-isolated-picker-bootstrap-tests.log. Initial scheduled-metadata test
interference and missing RecycleView layout binding failures remain retained.

This contains a class of process-wide filesystem stalls; it does not prove the
precise source of DESKTOP151's lstat/GIL sample or resolve all native tab freezes.
Frozen helper output, installed folder timeout/retry, native recycled-row behavior
and connected tab responsiveness require separate verification.

DESKTOP152 installed checkpoint: eba45ca, 476 installed files without manifest
mismatches and strict signatures passed at 2026-10-05T14:17:27Z. Frozen metadata
helper pipe roundtrip passed. Native export picker opened and displayed 254 entries,
but scrollbar input caused an uncaught focus exception: ordinary ScrollView.scroll_to
expects a ClockEvent where RecycleLayout exposes a method. The app entered Python
finalization and remained live; process/exception evidence is retained in
/private/tmp/carvera-desktop152-20261005/. No native picker acceptance is claimed.

Recycled-row focus correction: the artifact viewport now reveals attached rows
without ordinary Layout trigger internals. Rows have centered text and a nine-dp
bar with content/bar scrolling. The strengthened regression reproduced the exact
native AttributeError before the correction; after correction, actual pointer
selection, scrollbar drag, focus, filtering/rebinding and post-dismissal protection
passed in the 1,500-entry list. Combined picker/focus/filesystem checks: 28 passed,
one existing SSL warning, 25.48 seconds. Before/after logs:
/tmp/carvera-recycled-focus-before.log and /tmp/carvera-recycled-focus-after.log.
Installed acceptance and overall responsiveness remain open.

DESKTOP153 installed/native picker checkpoint: frozen b3e3fc8bbaa75a535e4ddb4cba719ca74413accc,
476 installed files without mismatches and strict signatures passed at
2026-10-05T14:28:14.976856Z. Failed DESKTOP152 is preserved; DESKTOP151 recovery
remains available. Native scrollbar dragging reached the bottom of the 254-entry
external Downloads listing, focused row selection worked, internal-folder navigation
worked and two diagnostics exports completed with independent JSON/hash readback.
All nine operator-store entries still matched. The current native log contains
neither the recycled-focus exception nor a connection-loss event.
Receipt: /private/tmp/carvera-desktop153-20261005/native-picker-acceptance.json.

Connected empty-program Scene/Position/Setup/Console/Machine/Camera/Program/Spindle
navigation callbacks measured 1.18-1.88 ms, next-clock observations 9.67-84.50 ms,
and window-flip notifications 7.42-75.56 ms. The final 300-arrival diagnostics window
had zero gaps above its 0.5-second threshold and maximum interval 0.311 seconds.
These measurements exclude input dispatch and display presentation and do not
qualify loaded programs, camera/replay workloads or the complete tab-freeze issue.
Startup again timed out the UI bridge; the initial Job frame notification was
3.43 seconds after its callback. Startup sample is retained in the same folder.
Camera remains unavailable. No upload, motion, tool change, offset or calibration
was issued. This closes the bounded recycled-row focus/scroll/save regression;
all original complete requirements remain open.

Deferred-probing startup source checkpoint: the probing workbench is now created
on first request, with immediate settings readiness, current jog-mode controls,
retained edits and keyboard-jog restoration. 53 integration and 83 probing/config
checks passed; see ui-responsiveness.md for receipts and profiling limitations.
A test-isolation incident changed the operator's saved single-axis probe diameter
to 4.25 mm; the previous value is unknown and must be reviewed before probing.
The hard-coded settings path is corrected to respect KIVY_HOME and explicitly
isolated by the test fixture. No physical action occurred. Native/package
acceptance and all original 25 full requirements remain open.

DESKTOP155 installed checkpoint: frozen source
83781d67a8c0bfa181b38ac6dbeb88feab36d2d9, 476 installed files with no manifest
mismatches and strict signatures passed at 2026-10-05T14:59:24Z. DESKTOP154 recovery
is preserved. Same-process startup recovered after UI-bridge timeout; explicit
saved-profile reconnect, fresh reported Idle telemetry, Live mode, Scene and Setup
navigation were observed. Camera remains unavailable. All 18 entries in the expanded
post-incident operator-store baseline matched; this does not restore/prove the
unknown original probe diameter. Native first-use probing with a probe installed
remains open. The log contains a caught missing-MDI-history configuration traceback,
no AttributeError and no connection-loss event. Receipt:
/private/tmp/carvera-desktop155-20261005/native-startup-navigation-acceptance.json.
No motion/upload/tool change/calibration/offset action was issued. Startup and
complete responsiveness acceptance remain open; no original requirement closes.

Scene restoration reuse source checkpoint: machine-owned fixture/vise components
reuse the loaded assembly only after current bounded bytes and resolved asset
path match. Successful startup profile restoration no longer seeds the scene twice.
24 affected tests passed; all real CAD vertices/indices/canonical metadata matched.
See ui-responsiveness.md for receipts and limits. Native startup, background CAD
preparation and full responsiveness acceptance remain open.

DESKTOP156 installed/native restoration checkpoint: frozen source
b8c68f0fda0f95a46fce1f5a1fb70eecb48f4f19, 476 installed files without manifest
mismatches and strict signatures passed at 2026-10-05T15:08:23Z; DESKTOP155 recovery
retained. This launch returned through the UI bridge without a timeout (12.73 s,
including automation overhead). Saved machine, Saunders plate, Mod Vise and stock
rendered. Explicit saved-profile connection completed configuration readback;
Live/Scene navigation and fresh reported Idle telemetry were observed. All 18
post-incident operator-store entries matched. Camera remains unavailable; unknown
original probe D remains unresolved. Receipt:
/private/tmp/carvera-desktop156-20261005/native-scene-restoration-acceptance.json.
No physical action was issued. Background CAD preparation, comprehensive native
performance and all original complete requirements remain open.

Background machine-profile source checkpoint: startup and library selection
prepare CAD on one worker with one latest pending request. Current scene is
retained during preparation; publication rejects superseded generations, disposed
owners and changed scene/recording context. Library feedback distinguishes
preparing, loaded and rejected states. 52 broad affected tests and a later
10-test lifecycle run passed; see ui-responsiveness.md for receipts/limits.
No machine commands were issued. GPU publication and initial default loading
remain synchronous; installed/native acceptance and all 25 full workflows remain open.


DESKTOP157 installed/native profile checkpoint: frozen source 20dbf18, 476
installed files without mismatches and strict signatures passed; DESKTOP156
recovery retained. Saved assembly/scene restoration and native library selection
succeeded; explicit reconnect completed and Live/Scene showed fresh reported Idle
telemetry. Initial startup UI-bridge timeout still occurred and recovered in the
same process. All 18 post-incident operator stores matched, camera unavailable,
unknown original probe D unresolved. Receipt:
/private/tmp/carvera-desktop157-20261005/native-profile-acceptance.json.
No physical action or complete original requirement closes.

Subsequent source batches profile publication into one final rendered scene,
retaining hidden state and restoring visibility on failure. Twelve lifecycle
checks and 44 affected scene/workspace/profile-draft checks passed; native package
acceptance remains pending.
See ui-responsiveness.md. Overall responsiveness and all 25 full workflows
remain open.


DESKTOP158 installed/native publication checkpoint: source
5e5ee511db46d0eecb933f8bfc5d6f5176661f5a, installed at
2026-10-05T15:25:16Z; 476 files without mismatches and strict signatures passed.
DESKTOP157 recovery retained. Native Use machine profile reported Loaded and
rendered the saved machine, plate, vise and stock. Explicit reconnect completed;
Live/Scene and fresh reported Idle telemetry were observed. Same-process startup
again recovered after a UI-bridge timeout; the UI reported a 3.57 s largest
interval since launch, without attribution or input/presentation timing proof.
All 18 post-incident operator-store entries matched. Camera remains unavailable,
unknown original probe D remains unresolved, and the caught missing mdi_history
configuration traceback remains. Receipt:
/private/tmp/carvera-desktop158-20261005/native-profile-publication-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. This closes the
bounded installed profile-publication regression only; default CAD loading,
final GPU construction, comprehensive responsiveness and all 25 full workflows
remain open.


Deferred default-CAD source checkpoint: viewer construction performs no default
asset I/O; scheduled background preparation retains the schematic and rejects
changed owners/base profile/setup. Saved profile selection and workspace disposal
cancel/invalidate default publication. Blank CAD selections retain default
fallback semantics. Twenty lifecycle checks passed; see ui-responsiveness.md for
receipts. Forty-four affected regression checks passed; packaging/native startup and
complete responsiveness acceptance remain open. All original 25 full requirements remain open.


DESKTOP159 installed/native startup checkpoint: frozen source
de5f15bbefdca0ce4ffd4c0d2b087248945936c8, installed at
2026-10-05T15:33:16Z with 476 files without mismatches and strict signatures
passed; DESKTOP158 recovery retained. Saved custom assembly restored; native
profile-library selection reported Loaded and preserved machine/plate/vise/stock.
Fresh reported Idle telemetry and Live/Scene were observed. Initial UI-bridge
timeout still occurred and recovered in the same process; no startup speed
claim is made. Native default-only startup and transient loading-caption visual
acceptance remain open. All 18 post-incident operator stores matched. Camera
unavailable, unknown original probe D unresolved, caught missing mdi_history
traceback remains; no AttributeError or connection-loss event in the current log.
Receipt: /private/tmp/carvera-desktop159-20261005/native-default-preparation-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. Default CAD I/O is
removed from viewer construction; final GPU construction, other startup work
and comprehensive responsiveness remain open. All 25 full workflows remain open.


Profiled CAD-bounds source checkpoint: loaded groups are immutable indexed
snapshots with exact bounds prepared during loading, removing repeated CAD scans
from scene publication. Mutable geometry remains fully revalidated. All real
asset coordinates/indices/canonical metadata and complete scene bounds match the
previous implementation. 34 validation and 49 affected engine checks passed;
rendered/package/native acceptance pending. See ui-responsiveness.md for source
profiling, native sample and exact comparison receipts. No complete original
requirement or overall responsiveness gate closes.

The rendered scene/profile/default-preparation/interaction suite passed 50 tests
(64.62 s, one existing SSL warning). Receipt:
/private/tmp/carvera-geometry-snapshot-rendered-tests.log. Ruff/format/diff passed.
All 18 post-incident operator-store entries matched. Native package acceptance
and comprehensive responsiveness remain open.


DESKTOP160 installed/native bounds checkpoint: frozen source
e3909b717090764055582a0a05b35f3b62b72e76, installed at
2026-10-05T15:44:40Z; 477 files without manifest mismatches and strict
signatures passed. DESKTOP159 recovery retained. Native profile selection
reported Loaded; saved machine, Saunders plate, Mod Vise and stock rendered.
Live/Scene displayed fresh reported Idle, T1/TLO 50.480 and zero RPM/feed.
Startup again timed out the UI bridge and recovered in the same launch;
no comprehensive responsiveness claim is made. All 18 post-incident operator
store entries matched, camera remains unavailable and original probe D remains
unknown. Current log contains no AttributeError or connection-loss event.
Receipt: /private/tmp/carvera-desktop160-20261005/native-bounds-acceptance.json.
No upload/motion/tool change/offset/calibration was issued. This closes bounded
installed immutable-CAD publication acceptance only; overall responsiveness
and every original complete requirement remain open.


Camera recovery/diagnostics checkpoint: no local listener at the saved
127.0.0.1:18091 snapshot URL; camera Ubuntu peer 100.93.125.40 is online in
current Tailscale state. Read-only remote service inspection is waiting on the
existing account SSH authentication check opened in Chrome (session 5164).
No forwarding process or remote service change has been started.
Source camera failures now distinguish refused local forward/service, refused
remote port, timeout, DNS, TLS and HTTP access/path/service failures without
echoing request or exception details. Existing decoder messages are allowlisted.
20 camera regressions passed; Ruff/format/diff checks passed. Logs:
/tmp/carvera-camera-diagnostics-tests.log and
/tmp/carvera-camera-diagnostics-isolated-tests.log. A startup filesystem-stat
stall sample is retained in /tmp/carvera-camera-tests-sample.txt; the original
run eventually completed. New diagnostics are not installed; DESKTOP160 remains
the installed build. Camera live recovery and all full requirements remain open.


Command palette coverage/keyboard checkpoint: DESKTOP160 native Cmd+K opened
the palette, typed camera search filtered results, arrows changed selection
and Enter opened Camera. Native arrow selection exposed short result lists
falling to the bottom because row rebuilding preceded layout. Source now
reveals after layout, keeps fitting result lists at the top and uses the
shared DesktopScrollView. Eight additional actions route directly to Operations,
Simulation, Run record, Job package, View/playback and Live/Preview/Compare pose.
These route local controls only; they do not generate/upload/run a program.
Three pure command checks and one rendered keyboard/lifecycle/no-command check
passed; existing SSL warning remains. Receipts:
/tmp/carvera-palette-coverage-tests.log and /tmp/carvera-palette-rendered-tests.log.
New action coverage and scrolling fixes are not installed; native responsiveness
and complete contextual coverage acceptance remain open. Camera recovery still
waits on the existing Tailscale authentication check. No original requirement closes.


DESKTOP161 installed/native palette and camera checkpoint: frozen source
9ea6362bce66e1fd4ba458d45bc2434aee8cd719, installed at
2026-10-05T15:58:19Z; 477 files matched and strict signatures passed.
DESKTOP160 recovery retained. Native camera search/Down selection retained
short rows at the top; portable archive/Enter opened Job package; live machine
pose/Enter set Live view. The local camera refusal recovery message rendered.
Explicit saved-profile reconnect reported fresh Idle telemetry; machine, plate,
vise and stock rendered. All 18 post-incident operator-store entries matched.
Startup bridge timeout recovered in the same launch; no overall responsiveness
claim. Current log contains no AttributeError or connection-loss event.
Receipt: /private/tmp/carvera-desktop161-20261005/native-palette-camera-acceptance.json.
Initial packaging failed on missing msgfmt in non-login PATH; failed log retained,
then the same frozen source built with installed compiler PATH explicitly supplied.
Camera recovery still requires existing Tailscale authentication; original probe D
remains unknown. No upload/motion/tool change/offset/calibration was issued.
Bounded palette reveal/navigation and local-camera-error acceptance close;
complete contextual coverage, comprehensive responsiveness and all 25 requirements
remain open.


Repeat-array visualization source checkpoint: all declared stock instances render
in their machine frame with shared table motion and stock visibility. The active
stock retains independent editing and rest-stock geometry; other nominal instances
are explicitly display-only. Input/profile/single-stock changes clear the array;
historical preview/return retains the declaration and selected instance. Declared
arrays cannot acquire confirmed physical alignment through viewer configuration.
22 unit/rendered checks passed; 49 affected checks passed in a combined run that
exposed two derived-buffer restoration comparisons. Both historical cases and the
array workflow passed after correcting retained-state ownership (three passed).
See repeat-parts.md for logs and remaining scope. Package/native acceptance, full
WCS-aware simulation, offset transactions and every original complete requirement
remain open. No physical action occurred.


DESKTOP162 installed/native repeat-array checkpoint: frozen source
56923aad0700c250e9d8c9f5fe881632eaa5b66e, installed at
2026-10-05T16:17:38Z; all 479 manifest files matched and strict signatures passed.
DESKTOP161 recovery retained. Native Setup built a two-row/three-column G54–G59
array, previewed Part 1 then Part 6, and hid the other instances while preserving
the active stock. No plan was saved. Restart restored the saved machine, Saunders
plate, Mod Vise and stock; final Live view showed fresh reported Idle/T1/TLO 50.480,
zero RPM/feed and Ubuntu camera frames. All 18 post-incident store entries matched.
Receipt: /private/tmp/carvera-desktop162-20261005/native-repeat-array-acceptance.json.
The pending Tailscale check completed; remote camera HTTP 200 was verified and a
localhost-only forward restored. Standard SSH rejected a stale known-host key; it
was not bypassed. The Tailscale wrapper independently verifies the node key advertised
by its coordination server. Forward session 74745 is live; automatic forward
lifecycle management remains open. Startup again timed out the UI bridge before
recovering in the same process; full responsiveness remains unresolved. Native
review also found excessive planner height and result placement below the viewport.
Native plan save/restore, native archived-array restoration, WCS-aware multi-stock
simulation and physical qualification remain open. No upload/motion/tool change/
offset/calibration was issued. No original complete requirement closes.

DESKTOP163 installed/native planner checkpoint: frozen source
8bdeaad4ca42d62f509c71a6536ea56b963e540e, installed 2026-10-05T16:37:50Z;
480 files matched and strict signatures passed. DESKTOP162 recovery retained.
Native Array layout / Review controls, two-part build/preview, automatic review
transition and missing-program simulation guard were exercised. Restart restored
the saved actual-scene draft; Live displayed fresh reported Idle/T1/TLO 50.480,
zero RPM/feed and camera frames. All 18 post-incident operator stores matched;
no repeat plan was saved. Receipt:
/private/tmp/carvera-desktop163-20261005/native-repeat-review-acceptance.json.
First launch observation timed out and recovered; comprehensive responsiveness
remains open. A misleading old active-stock warning was corrected subsequently
in source (rendered regression passed); that wording correction is not installed.
Native calculation with loaded program/tools, persisted multi-stock results,
frame-aware playback and registered machine workflow remain open. Architecture
contracts were not rerun because importlinter is absent from this isolated runtime.
No motion/upload/tool change/offset/calibration occurred. No original complete
requirement closes.
