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
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, worker-prepared import preview, late-result ownership guard, exact calibration-image and pose custody | Native roundtrip including rest stock/calibration assets, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Exact rendered-surface picking, stock/vise XY and Z handles, CAD-pivot vise Z rotation, declared-center stock Z rotation, independent grid/angle snapping, actual displayed cutter picking, async component framing and reviewed drafts with persistence/cancel safeguards | Native interaction acceptance, general tilted rotation, calibrated hole snapping, clipping/exploded view |
| 5 | Camera registration | Distortion/intrinsic engine, bounded pose fitting, residuals; frozen reference image/pose custody, point picking, sectioned workbench, schema-2 exchange and raised-stock outline | Physical correspondences and intrinsic measurements, native point-picking and fitted-file exchange acceptance, exposure synchronization |
| 6 | Live/Preview/Compare | One-packet observed pose; Preview/Live/Compare modes, independent markers and stale-data handling | Physical CAD registration, tool reconciliation and rotary pose integration |
| 7 | Tool passports | Sectioned revision-aware physical assemblies, dimension/CAD/drawing references, raw measurement attribution, physical holder preview and hash-bound facing/hole-stage recipe links | Measured holder/gauge geometry, qualified reach, complete asset validation and complete native workflow |
| 8 | Physical ATC inventory | Capability-bounded M889 parser, explicit query transport, bounded connection-scoped receipts and paginated configured-pocket/local-declaration review and nominal configured-target overlay and validated historical receipt exchange | Broader native viewport/orbit coverage and physical assembly/occupancy reconciliation |
| 9 | Two six-tool banks | Sequential usage planning, saved assembly selections, revision-bound preparation/measurement records, separate post-placement mapped receipts and fresh current-spindle TLO comparison | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification; preparation records do not enforce execution |
| 10 | Calibration bench | Unified assembly/tool-number evidence bench with repeatability statistics, revision/source-bound offset changes, post-placement receipt comparison and fresh current-spindle TLO; existing repeated calibration | Native bench acceptance, integrated measurement launch/transport, reference measurements and physical seating/offset qualification |
| 11 | Geometry probing | Existing probing workflows; exact nominal triangle/point/normal selection and ball-center approach/search/retract planning with projected scene review | Qualified reach/clearance, registered probe transport, measurement custody and measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export; retained nominal surface/setup association, workbench operator-entered receipts, signed limits/repeat statistics, reviewed portable exchange, CSV/HTML reports and searchable paged receipt/deviation history and reviewed atomic TSV/CSV batch entry | Registered compensated machine receipt capture, richer fitting/tolerances, complete native workflow and physical qualification |
| 13 | Surface maps | Persistent samples and bounded interpolation/exclusions; workbench provenance entry, measured-point plot, height queries, import/export and measured upper facing target | Probe transport capture and physical sample qualification; unsampled curvature remains unknown |
| 14 | Boundary-aware facing | Workbench polygon/scene-stock boundary, loaded cutter reach checks, final target/process inputs, async local program preview and cutter-bound recipes | Native complete workflow and physical travel/clearance qualification |
| 15 | Hole/thread workflow | Workbench hole locations, imperial/metric threads, optional spot/bore/chamfer stages, explicit cutter/angle/reach checks, async single-form and explicit multi-form tooth-stack previews and recipes | Native complete workflow, manufacturer tooth reference/clearance and thread-fit qualification, verified tapping qualification and actual backend adapter |
| 16 | Observed recipes | RPM baseline/shadow monitor and reviewed facing/hole-stage recipes bound to assembly revision, nominal cutter fingerprint and exact file hash | Actual cutting engagement/outcome evidence, complete process history and physical process qualification |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded status recording, continuous receipt playback with explicit gap/boundary stops, event replay/archive marker, exact selected-program association, declared setup custody/restoration; session-bound JPEG recording, validated bundles and native camera import/display/return-live; historical scene/tool restoration source-tested | Native receipt playback and corrected setup capture/restoration including retained calibration images, exposure/clock qualification, actual execution attribution, linked toolpath replay and complete recorded-run workflow |
| 19 | Collision checking | Workbench fixture/vise bounds, collision candidates and line navigation | Swept narrow phase/rotation, complete holders/machine structures and registration qualification |
| 20 | Stock removal | Canonical mm segments with bounded arcs; swept flat/ball/bull/drill/taper/chamfer/engraving/thread envelopes; rendered and persisted rest stock, workbench controls | Rotating-axis subdivision, true thread grooves, detailed holder/envelope metadata and native workflow validation |
| 21 | Recovery checkpoints | Canonical modal checkpoints, explicit verification inputs and conservative draft | Alarm/lost-position workflow, clearance/tool/WCS revalidation and qualified reentry |
| 22 | Multiple WCS | Coordinate backend; declared G54–G59 arrays, plans and full-array preview; source-tested multi-stock subtraction, persisted per-part occupancy and frame-aware path/cutter playback with reversible file/historical restoration | Probing/offset transactions, continuing machining from restored multi-stock results and repeat execution/inspection |
| 23 | Rotary workspace | General rotary forward geometry and limits | Chuck/jaws/tailstock setup, G93 program playback, indexed/wrapped/simultaneous validation |
| 24 | Capability adapters/IO | Versioned actual/declaration evidence, bounded Carvera command plans, lifecycle receipts | Transport adapters, fresh observed evidence, peripheral UX and verified acknowledgements |
| 25 | General five-axis | Head/table forward chains, pivots, limits, tool/work transforms, bounded inverse solving and angle unwind; cancellable declared-profile import and multi-seed workbench review with selected joint/limit/equivalent-angle results and local rank diagnostic; ordered joint-transition sampling, selectable rank trace, interior dependent-direction and full-turn review; fixed-orientation indexed work-point mapping, selectable point inspection and explicit route handoff | Native complete branch/path/indexed-review acceptance, between-sample singularity handling, physically qualified indexed 3+2 workflow, declared/observed TCP and actual capable backend |

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


DESKTOP164 native declared-playback checkpoint: frozen source
`cb14960e057a0956b085cfad7cdded7396a62a19`, installed at
2026-10-05T16:49:28Z; 481 files matched and strict signatures passed.
Native two-part G54/G55 preview enabled declared-frame path/cutter playback,
excluded one unresolved initial line, moved the displayed cutter to the second
stock, reached line 13 and restored original file playback. Restart discarded
the unsaved array/program and restored the saved plate, vise and stock. Final
Live showed fresh reported Idle/T1/TLO 50.480, zero RPM/feed and camera frames.
Receipt: /private/tmp/carvera-desktop164-20261005/native-repeat-playback-acceptance.json.
Seventeen post-incident operator-store entries matched; program-places.json
changed through the intentional local-file inspection. Original probe diameter
remains unknown. No upload/motion/tool change/offset/calibration was issued.
Native multi-stock calculation/persistence and physical qualification remain open.
Connection loss/reconnect coincided with picker navigation; Return to Live
observation later took 23.55 seconds. Comprehensive responsiveness is not closed.

Native review found contradictory playback state text: the action reported
declared-WCS mode while the stock note retained its old single-frame warning.
Source now derives the stock note from the actual viewer state on enable/restore.
Two rendered repeat-part/playback regressions passed (44.64 s, existing SSL warning),
including exact original path restoration and no-machine-command assertions;
Ruff/format/diff checks passed. Log: /tmp/carvera-repeat-playback-status-tests.log.
This correction is later source and is not installed in DESKTOP164.
No original complete requirement closes.


Multi-stock persistence/compact review source checkpoint: array calculations now
retain per-part compressed occupancy in addition to rendered geometry. Results &
files saves/loads a bounded .cvstocks bundle with exact program/array/profile/tool/
workholding/CAD context, occupancy integrity, placement/volume/resolution checks
and shared voxel/face limits. Assets are freshly hashed off the UI thread. Atomic
saving preserves previous files on pre-publication cancellation. Loading builds
all stocks before publication and rejects changed context or late cancellation.
Collision candidates/summary quantities persist; detailed contact geometry is
explicitly unavailable after load. Active-part viewing does not invalidate results.
Array layout, Review & simulate and Results & files separate controls from reports;
preview actions share a compact row and calculation reveals results only when the
operator remains on the review task.

Affected engine/rendered/historical checks passed 45 tests (31.38 s, existing SSL
warning); final strengthened archive/publication checks passed 11 tests (18.67 s),
including changed/cancelled load publication and previous-file preservation.
Logs: /tmp/carvera-repeat-result-final-corrected-tests.log and
/tmp/carvera-repeat-result-publication-tests.log. Ruff/format/diff checks passed.
The original report-equality assertion was corrected to reflect explicitly omitted
detailed contacts; its failure remains in /tmp/carvera-repeat-result-unit-tests.log.
The initial broad invocation named a missing test file and ran no tests; that
receipt remains in /tmp/carvera-repeat-result-final-tests.log. Operator readback:
/tmp/carvera-repeat-result-operator-readback.json; the program-places change already
recorded during DESKTOP164 native file inspection remains the only changed entry.
Original probe diameter remains unknown. DESKTOP164 is still installed; this
checkpoint awaits packaging/native result exchange and layout acceptance. Physical
workflows and all original complete requirements remain open.


DESKTOP165 native multi-stock checkpoint: frozen source
`4ece4660367789e03f3a875d637abf9092295292`, installed at
2026-10-05T17:06:46Z; 482 manifest files matched and strict signatures passed.
Native two-part G54/G55 calculation at 1 mm resolution reported 41 mm³ removed
and 15,959 mm³ remaining per stock. Save and matching-load retained both reports,
rendered stocks and explicit missing-detailed-contact qualification. Independent
bundle and occupancy verification confirmed 16,000 binary cells per stock and
15,959 occupied cells, exact placements and hashes. Receipt:
/private/tmp/carvera-desktop165-20261005/native-repeat-result-acceptance.json.
The temporary simulation-only tool profile was removed by restoring exact original
profile bytes while closed. Restart restored the saved actual scene; Live showed
fresh reported Idle/T1/TLO 50.480, zero RPM/feed and camera frames. Seventeen store
entries matched; the recent-program entry changed intentionally. Original probe
diameter remains unknown. No upload/motion/tool change/offset/calibration occurred.
The picker initially entered Downloads; cancellation left helpers stopping and
briefly rejected the local result folder. Retrying the same folder recovered.
Full responsiveness remains open. This closes bounded native multi-stock
calculation/save/load acceptance, not physical registration or the original full
multiple-WCS requirement.

Artifact-browser follow-up: accepted folders are reused within the session per
artifact suffix set, shared by save/load. Invalid callbacks and mere navigation
do not replace the last accepted folder. The rendered picker suite passed all
12 tests (16.88 s, existing SSL warning), including accepted-folder reuse,
artifact-type separation and rejected-callback preservation. First-use fallback
now explicitly isolates its session state in the test; the original failure is
retained in /tmp/carvera-picker-accepted-folder-tests.log. Final receipt:
/tmp/carvera-picker-accepted-folder-final-tests.log. Ruff/format/diff checks passed.
This source change is later than DESKTOP165 and awaits installed/native acceptance;
it reduces repeated visits to unrelated storage but does not close overall
responsiveness or filesystem-helper lifecycle recovery.


DESKTOP166 installed/native picker checkpoint: frozen source
`1f3722979b346f109a5e58f9db0f7d049400ce90`, installed at
2026-10-05T17:20:08Z; 482 manifest files matched and strict signatures passed.
Native profile export to the owned receipt folder succeeded; Import opened that
accepted folder immediately with the exported file visible. Import was cancelled.
Independent exported JSON matched the current profiles; all 18 operator-store
entries matched the pre-update baseline. Native Downloads-to-local-folder
navigation recovered without manual retry in this run. Live showed fresh reported
Idle/T1/TLO 50.480, zero RPM/feed and camera frames. Receipt:
/private/tmp/carvera-desktop166-20261005/native-picker-acceptance.json.
DESKTOP165 recovery retained. The initial build invoked the wrong runtime and
exited because PyInstaller was missing; the corrected isolated dependency runtime
built successfully. Both logs are retained. No upload/motion/tool change/offset/
calibration occurred. Accepted-folder reuse native acceptance closes; pathological
blocked-storage recovery, persistent folder preferences and broader responsiveness
remain open. No original complete requirement closes.


DESKTOP167 native shared-header checkpoint: frozen source
`52e09b85c75bcfe7928db060856681e680aa4ed5`, installed at
2026-10-05T17:28:17Z; 482 manifest files matched and strict signatures passed.
Native standard-width review confirmed nine top tabs in one row, status/profile
metadata and connection/hold/STOP on one row, readable setup evidence and more
visible Setup controls. Narrow layout remains rendered-test evidence only.
Receipt: /private/tmp/carvera-desktop167-20261005/native-header-acceptance.json.
The same build recovered from a filesystem-open stall without restart; its sample
is retained. All 18 operator-store entries matched; Live showed fresh reported
Idle/T1/TLO 50.480, zero RPM/feed and camera frames. DESKTOP166 recovery retained.
Setup and Return-to-Live combined native input/AX/screenshot calls took 57.13 and
60.89 seconds respectively. These durations do not isolate app/input/observation
latency; full responsiveness remains unresolved. Next diagnostic separates those
phases and inspects application navigation timings. No upload/motion/tool change/
offset/calibration occurred. Layout acceptance closes at standard width only;
no original complete requirement closes.


DESKTOP167 responsiveness diagnosis: native diagnostics exported and independently
read at 2026-10-05T17:36:24Z. Setup callback was 1.17 ms, next clock turn 467.71 ms
and flip notification 455.51 ms; Monitor callback was 1.25 ms, clock turn 41.53 ms
and flip 37.35 ms. The retained 60 recent refreshes peaked at 5.74 ms, but 2,210
older refreshes had been evicted. Separately measured Scene native calls took
0.52 s input, 1.17 s accessibility and 0.81 s screenshot. This does not explain
previous combined minute-long calls or prove input dispatch/presentation latency.
The picker timed out on Downloads and initially on the owned folder; same-folder
retry recovered. A transient controller reconnect also recovered in the same
process. Native export receipt, JSON and process sample are retained in
/private/tmp/carvera-desktop167-20261005/; navigation-diagnosis-receipt.json
records the exact export digest and confirms all 18 operator stores matched.
No upload/motion/tool change/offset/calibration occurred.

Source follow-up preserves the slowest callback, clock-turn and flip observations
independently of recent-record eviction, plus the longest callback-start interval
with adjacent identities. Retention remains bounded; exports are independent
copies. Failed callbacks remain explicitly failed without invented render proof.
The Machine timing note now uses the session maximum refresh instead of the
recent ring maximum. Start intervals are cadence evidence, not causal evidence;
navigation intervals include operator idle time. Engine, rendered navigation and
async-export checks passed 17 tests (18.06 s, existing SSL warning), including a
five-second refresh exported after ring eviction. Ruff/format/diff checks passed.
Log: /tmp/carvera-retained-slow-timings-final-tests.log. This source change awaits
packaging/native acceptance; installed DESKTOP167 predates it. Overall freeze
resolution and all original complete requirements remain open.


DESKTOP168 native timing-retention checkpoint: source
`9dbc1fa4d67e2a7f4beaa202d364663595338088`, installed at
2026-10-05T17:40:33Z; all 482 manifest files matched and strict signatures passed.
DESKTOP167 recovery retained. The first native observation timed out during
startup; the same running process was subsequently observed without restart.
Native diagnostics export independently confirmed a 23.01 ms maximum refresh
(sequence 1) persisted after 553 records were evicted, outside the 60 recent
records. It also retained a 4.44 s startup refresh-start interval and 5.61 s
initial flip notification. These identify diagnostic intervals, not their cause
or screen presentation. Source-controlled slow-refresh export and failure
semantics passed the prior 17-test affected suite. Native Setup/Spindle switches
and export succeeded; folder navigation needed no retry in this run. Live showed
reported Idle, T1/TLO 50.480, zero RPM/feed and fresh camera/telemetry. All 18
operator-store entries matched. Receipts:
/private/tmp/carvera-desktop168-20261005/artifact-verification.json and
/private/tmp/carvera-desktop168-20261005/native-timing-acceptance.json.
This closes native session-maximum export acceptance only; root-cause diagnosis,
full responsiveness and all original complete requirements remain open.


UI stall-capture source checkpoint: an independent background monitor samples the
UI thread after a one-second missed heartbeat. It retains at most 20 episodes,
three samples per episode and 32 stack locations per sample, with recovery time,
heartbeat gap and last page context. Capture stores source basenames/functions/
line numbers only; no source reads, local values or full paths. Recovered-during-
sampling races are rejected; disposal cancels the heartbeat and signals worker
shutdown without joining on the UI thread. Signal diagnostics exports these
bounded observations. OS suspension, debugger pauses and GIL starvation remain
explicit alternative explanations; sampled locations do not prove root cause.
Engine/thread/export/rendered navigation checks passed 20 tests (14.84 s,
existing SSL warning); Ruff/format/diff passed. Log:
/tmp/carvera-ui-stall-capture-final-tests.log. Packaging/native capture acceptance
and overall freeze resolution remain open. DESKTOP168 remains installed.


DESKTOP169 native stall checkpoint: source
`48f2f819960ee8727076c44430b081dd6f1bd5cb`, installed at
2026-10-05T17:47:21Z; all 483 manifest files matched and strict signatures passed.
DESKTOP168 recovery retained. Existing Workshop Carvera profile was explicitly
connected; Live returned with fresh reported Idle, zero RPM and camera/telemetry.
Native diagnostics captured five recovered heartbeat episodes without artificial
machine actions. Startup samples were in Kivy drawing/buffer flipping (1.98,
1.26 and 1.14 s gaps). Two file-browser paste episodes were sampled in
clipboard_sdl2.get via TextInput.paste, with recovered heartbeat gaps 12.66 and
9.69 s. These locate a clipboard-related UI freeze; they do not establish the
cause of every prior tab delay. The background monitor may itself be delayed by
the GIL. Native export/readback verified bounded samples and recovery timestamps.
All 18 operator stores matched. Receipts and exact export digest:
/private/tmp/carvera-desktop169-20261005/native-stall-acceptance.json.
No upload/motion/tool change/offset/calibration occurred. Clipboard isolation and
native paste/cancellation/selection/undo acceptance are the next actionable fix;
startup rendering and overall responsiveness remain open. Native bounded stall
capture/export/recovery closes only this diagnostic checkpoint.

Async clipboard source checkpoint: modern workspace Fields on macOS use a
background pbpaste helper instead of SDL clipboard reads on the UI thread.
Reads have a two-second deadline, 1 MiB byte cap and two-helper concurrency cap;
helpers retain their slot until reaped. Text/cursor/selection/focus/attachment/
editable changes cancel or reject stale completions. Replacement uses existing
TextInput selection and insertion primitives, retaining normal filtering and
undo behavior; pending/error borders provide feedback. Non-macOS providers are
unchanged. Clipboard contents never enter diagnostics. Focused helper, blocked
read/clock, cancellation/supersession, selection/undo and existing keyboard tests
passed 24 tests (21.19 s, existing SSL warning). Log:
/tmp/carvera-async-paste-final-tests.log. Ruff/format/diff checks passed.
Installed native paste acceptance, startup rendering and overall responsiveness
remain open; this does not close any of the original 25 full requirements.

DESKTOP170 native paste checkpoint: source
`0e6f81ded724f4b7696425bf7b9d7dd8b9038159`, installed at
2026-10-05T17:59:33Z; all 484 files matched and strict signatures passed.
DESKTOP169 recovery retained. Native directory and filename paste were visually
read back; undo restored the empty filename field; diagnostics saved and read
back successfully. This session retained only two startup heartbeat episodes
(3.83 s resource/image lookup and 1.70 s profile scene construction), both recovered
before file-picker testing. No clipboard-stack episode was recorded during the
three native paste interactions. Input wrapper durations include input/tool
latency and do not measure isolated app response or prove every freeze resolved.
All 18 operator stores matched; Live returned with fresh reported Idle, telemetry
and camera. No upload/motion/tool change/offset/calibration occurred. Receipt:
/private/tmp/carvera-desktop170-20261005/native-paste-acceptance.json.
This closes the native directory/filename paste and undo checkpoint only.
Comprehensive clipboard behavior, error-message presentation, legacy fields,
startup rendering/scene construction and overall responsiveness remain open.

Prepared workholding checkpoint: loaded assemblies retain at most two immutable
workholding placements with prevalidated bounds. Neutral placement reuses loaded
CAD; worker preparation transforms selected or saved vise placement before profile
publication. Cache hits never wait for another placement's transform. Each render
constructs one scene per distinct assembly, instead of recomputing the same
machine/fixture/vise assembly up to three times. Stock geometry remains separately
constructed and never enters the placement cache. Focused geometry, async profile,
saved setup and historical scene checks passed 65 tests (24.43 s, existing SSL
warning). Log: /tmp/carvera-placement-preparation-final-tests.log.
The installed Saunders/Mod Vise asset source benchmark used the actual saved
placement: 30,012 workholding vertices, 0.150 s cold preparation and 0.022 ms mean
warm scene construction over 100 calls. This is source timing, not native UI
latency. Receipt: /private/tmp/carvera-placement-performance-20261005.json.
Native acceptance and overall responsiveness remain open; GPU construction,
uncached interactive placements and resource/image lookup can still block.

Render-buffer preparation checkpoint: immutable CAD snapshots retain at most two
exact work-offset/scale triangle-buffer frames. Buffers preserve indexed order,
normals, colours and unsigned-short limits; finite frame/overflow checks reject
invalid render coordinates. Cache hits do not wait for another frame's conversion.
Default and selected machine-profile workers warm these pure buffers before UI
publication. Renderer copies cached immutable buffers for GPU inputs rather than
re-translating every CAD vertex; mutable stock/schematic geometry retains its
existing path. Snapshot deepcopy/pickle preserve immutable geometry and omit
transient cache state. Profile publication rejects a changed program scale.
An exercised clearance-to-motion test found the operation card could be inserted
before its toolbar was attached; selection now attaches that toolbar first.
Final affected geometry/profile/default-load/inspection/section tests passed
81 tests (22.00 s, existing SSL warning), after the retained initial navigation
failure. Logs: /tmp/carvera-render-buffer-tests.log and
/tmp/carvera-render-buffer-final-tests.log. Ruff/format/diff checks passed.
Actual 370,746-vertex CAD source benchmark: 0.830 s cold worker preparation,
0.016 ms warm group lookup and 10.73 ms including mutable GPU-input copies over
100 runs. GPU construction and native latency are excluded. Receipt:
/private/tmp/carvera-render-buffer-performance-20261005.json.
This checkpoint is source-tested only. DESKTOP171 remains the separate c7a90f0
build waiting on external-volume signing writes; no second build was started.
Component import, uncached interactive placement, GPU construction, startup
image/resource work and comprehensive native responsiveness remain open.

Asynchronous component-selection checkpoint: fixture and vise CAD selection,
import and external saved-component restoration prepare profiles and render
buffers on independent background lanes. Each lane retains one active and one
latest pending request; replaced requests do not publish. Scene/profile/selection/
placement/scale changes reject late results, and disposal closes publication.
Loaded machine-owned components restore directly from the already prepared
assembly. External restoration waits until saved numeric geometry is restored
before preparing its frame. The current geometry remains visible while loading;
independent pending/error feedback prevents one completed component from hiding
another pending component or failure. No CNC commands are sent by this workflow.
Affected tests passed 26 tests (17.29 s, existing SSL warning), including blocked
worker/UI clock, bounded coalescing, independent lanes, stale results, import
registration, saved numeric restoration and retained pending/error feedback.
Log: /tmp/carvera-component-loading-final-acceptance-tests.log.
Ruff lint/format and diff checks passed. Import-linter is unavailable in this
runtime, so its architecture contracts were not rerun for this checkpoint.
This remains source-tested: GPU construction, native CAD import/selection and
overall tab responsiveness require installed verification. DESKTOP171 uses the
earlier c7a90f0 source and is not evidence for these changes. All original 25
complete workflows remain open.

Immutable CAD mesh-retention checkpoint: scene rebuilds retain each unchanged
immutable machine/fixture/vise mesh by snapshot identity, exact work-offset/scale
frame and visibility. Replacing a component rebuilds its group; hiding/showing,
removing/reintroducing or changing its render frame invalidates that group.
Mutable stock/rest stock remains uncached. Retained keys are bounded by scene
groups, and identity comparison avoids equality/hash traversal of vertex streams.
Absent geometry groups clear their instructions without clearing live/preview
marker contexts. Observed markers retain their meshes in unchanged frames and
reproject when work offset/scale changes. Uniforms and inspection geometry still
refresh independently of mesh construction.
Actual Kivy mesh-identity/coordinate tests and affected component, section,
recording, scene-persistence and pose-context checks passed 44 tests (38.70 s,
existing SSL warning). Log: /tmp/carvera-gpu-mesh-reuse-acceptance-tests.log.
Initial failures are retained in /tmp/carvera-gpu-mesh-reuse-tests.log: a new
coordinate assertion assumed zero work offset, and the local viewer fixture left
deferred default CAD loaders to start during later integration clock pumping.
The fixture now explicitly cancels those unneeded loaders and declares its
coordinate frame. Ruff lint/format and diff checks passed. Installed/native
responsiveness remains open; this does not measure native GPU latency or close
any original full capability.

Retained-build relocation completed at 2026-10-05T18:34:06Z. Owned build roots
160–163 were copied to /Volumes/Wes Storage/CarveraBuilds/retained-builds,
independently hash/mode/link/directory verified, and their original paths retained
as symlinks. Receipt: /private/tmp/carvera-build-relocation-20261005.json.
DESKTOP171 advanced past PyInstaller signing to the build script's final signing
process (PID 94415); build PID 84711 and exec session 18059 remain live. Receipt:
/private/tmp/carvera-desktop171-final-signing-wait-20261005.json.
No duplicate build, package installation or CNC command occurred in this checkpoint.

Reviewed setup preparation checkpoint: stock/origin and vise Apply requests warm
all distinct selected CAD assemblies and placement/render buffers on background
workers before the existing reviewed local transaction publishes geometry or saves.
Workspace-owned bounded lanes retain one active and one latest pending request
per editor kind. Repeated activation does not create another worker. Pending
feedback disables Apply while Cancel, Keep draft and Reload remain available.
Closing/reloading invalidates publication; changed raw fields, baseline geometry,
profile/component identity, render scale or disposed ownership reject results.
Preparation failures retain the active scene and editable draft. Existing optimistic
saved-file checks and rollback semantics remain in the publication transaction.
Completed surface selections now retain their viewport identity so resizing cannot
revive an old measurement reference merely because immutable CAD meshes were reused.
Final setup/gesture/drawing/rollback and blocked-worker rejection tests passed
60 tests (84.37 s, existing SSL warning); 11 focused asynchronous cases also passed.
Log: /tmp/carvera-setup-preparation-final-tests.log. The initial failure log remains
/tmp/carvera-setup-preparation-tests.log: an obsolete drawing caption expectation
and a missing completed-pick viewport guard. Ruff lint/format/diff checks passed.
Native preparation, GPU construction and comprehensive responsiveness remain open.

DESKTOP171 build session 18059 completed with exit 0. Its frozen source remains
c7a90f09ef7119ec7c4f8f6d84067f8e5dfe9d7b; it excludes subsequent source changes.
Artifact verifier session 19706/PID 99455 remains live waiting on an external-volume
read. No installation occurred before successful independent artifact verification.
DESKTOP170 native pre-install export at 2026-10-05T18:46:44Z retained fresh reported
Idle, RPM/feed 0 and camera updates, but telemetry persistence had stopped with
ENOSPC: 8,583 written, one failed and 3,784 rejected records at export. Export:
/private/tmp/carvera-desktop170-20261005/native-before-desktop171.json.
All 18 tracked operator stores still match their baseline hashes. Failed persistence
and the missing run segment remain open; fresh live telemetry does not recover it.
Next recording action is explicit persistence recovery with a retained gap record.
No upload, motion, tool change, offset change or calibration occurred here. The
original 25 complete capabilities remain open.

Explicit recording-recovery checkpoint: the Spindle diagnostics panel can start
one asynchronous new recording segment after a drained writer failure. Recovery
creates a unique segment exclusively, flushes and independently reads back its
gap record before the controller publishes the replacement writer. Publication
rechecks connection generation and writer ownership and queues the final loss
boundary before subsequent samples. Failed/partial files, failed recovery attempts
and earlier loss counts remain visible and exportable. Repeated activation cannot
spawn duplicate pending recoveries; connection changes and shutdown reject late
publication. No transport command, monitor reset or reconstruction of missing
telemetry occurs. Responsive controls expose pending, failed and resumed states.

Recovery/log/UI/receive regression checks passed 27 tests (18.41 s, existing SSL
warning): /tmp/carvera-telemetry-recovery-acceptance-tests.log. Adaptive monitor
and telemetry-quality regressions passed 27 tests (1.88 s):
/tmp/carvera-telemetry-recovery-monitor-tests.log. Ruff lint/format and diff checks
passed. The earlier combined failure remains in
/tmp/carvera-telemetry-recovery-final-tests.log: the steady-state receive test left
the automatic configuration download enabled while pumping the UI clock. The
fixture now explicitly marks configuration loaded, retaining all receive-lock,
storage-count and no-transport assertions. Recovery remains source-tested;
installed recovery interaction and complete recorded-run acceptance are open.

DESKTOP171 independently verified all 484 manifest files and strict signatures at
2026-10-05T18:52:14Z, then installed with the same checks at 18:59:48Z.
Source remains c7a90f09ef7119ec7c4f8f6d84067f8e5dfe9d7b and excludes later
rendering, setup and recording-recovery changes. Receipts are built-verification.json
and artifact-verification.json in
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop171-20261005.
DESKTOP170 remains at /Applications/Carvera Controller Community DESKTOP170 recovery.app.
Pre-install native export at 18:59:24Z reported Idle, RPM/feed zero and retained
8,583 written, 7,117 rejected and one failed record. Its missing telemetry remains
unrecoverable: /private/tmp/carvera-desktop170-20261005/native-pre-install-refresh.json.
Native DESKTOP171 acceptance is separate from verified installation.

DESKTOP171 native receipt at 2026-10-05T19:01:37Z independently retained connected
Idle, RPM/feed zero, 416 written/zero rejected/zero failed telemetry records and
the live Ubuntu camera. All 18 tracked operator stores still match their baseline.
Receipt: /private/tmp/carvera-desktop171-native-acceptance-20261005.json; raw native
export: /private/tmp/carvera-desktop170-20261005/native-desktop171-acceptance.json.
Three startup UI-heartbeat gaps of 1.22, 2.89 and 2.89 seconds remain observed;
one tested Job-to-Monitor navigation had a 1.22 ms callback and 39 ms window flip.
These limited observations do not establish comprehensive responsiveness.
DESKTOP172 build session 99180 uses frozen committed source
7b069cd4f5f8144bc76338c522914449d1713740 in
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop172-20261005.
Its new recording recovery and later rendering/setup changes require independent
artifact verification, installation and native exercise. The full 25-item scope
remains open; no new physical machining qualification is claimed.

Release-note startup checkpoint: native DESKTOP171 stall samples included hidden
TextInput layout in check_ctl_version. Controller/firmware update detection now
retains full notes without assigning them to a rendered TextInput until the Updates
dialog opens. A styled read-only viewer provides previous/next controls and page
counts; each page is bounded to 2,048 characters and 40 newline boundaries, including
oversized individual lines. Lossless pagination preserves Unicode, CRLF and every
source character. Dismissal clears rendered text/focus, and refreshing clears stale
notes and both version-check flags. Version labels use available horizontal space.
Full notes remain accessible rather than being truncated to a preview.
20 pagination, dialog, update-version and receive-heartbeat checks passed (13.59 s,
existing SSL warning): /tmp/carvera-release-notes-acceptance-tests.log.
Initial 10 checks passed in /tmp/carvera-release-notes-tests.log. Ruff lint/format
and diff checks passed. Native startup improvement and complete Updates UX remain
unverified; DESKTOP172 predates this source change.

DESKTOP172 build session 99180 finished with exit zero; independent verification
at 2026-10-05T19:05:10Z matched 486 files and strict signatures. Installation at
19:05:50Z repeated those checks and retained DESKTOP171 as a recovery application.
Source is 7b069cd4f5f8144bc76338c522914449d1713740. Native process 30194 displayed
DESKTOP172, the live Ubuntu camera, fresh reported pose and workbench/profile
navigation. Its persisted record at 19:08:48Z reported Idle, RPM/feed zero and
sequence 687 with zero earlier rejects/failures; all 18 tracked operator stores
remain unchanged. Receipt: /private/tmp/carvera-desktop172-native-observation-20261005.json.
Retained native navigation export and recording-recovery error-path exercise are
still open: scroll automation did not reach diagnostic controls, and a wheel
attempt changed scene zoom. This observation does not close responsiveness.
DESKTOP173 uses frozen b707847600d08329235883a3067afdb592f68ea9 and contains
the bounded release-note viewer; its build, artifact and native gates are separate.

Spindle workbench ergonomics checkpoint: live RPM/droop/proposal metrics remain
visible above three compact Signal, Diagnostics and Baseline sections. Each section
has its own scroll position; section switching sends no controller command.
Diagnostics export and recording-recovery controls now appear immediately after
the heading, before verbose quality metrics. The command palette opens each
section directly and offers local diagnostics export with a fresh duplicate-export
availability check. Plot construction during refresh is limited to visible Signal.
Adaptive snapshots expose the retained fault separately from the latest sample;
fresh packets do not clear it. The UI distinguishes current complete telemetry
health from a latched fault and suppresses the proposed-feed value for faults or
an off monitor. The reset action is labeled Reset monitor to reflect its effect.
No adaptive actuation or fault-clearing policy changed.

Monitor, diagnostics, receive, palette and adaptive regressions passed 37 tests
(15.85 s, existing SSL warning): /tmp/carvera-monitor-sections-acceptance-tests.log.
The initial 35-test log remains /tmp/carvera-monitor-sections-tests.log. Final
styling checks passed four cases (12.59 s):
/tmp/carvera-monitor-sections-styling-tests.log. Native layout/scrolling, keyboard
export and complete adaptive supervision remain open.

DESKTOP173 build session 15762 completed with exit zero. Independent verification
at 2026-10-05T19:11:53Z matched all 488 manifest files and strict signatures;
receipt: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop173-20261005/built-verification.json.
Its source remains b707847600d08329235883a3067afdb592f68ea9, excluding the
spindle-section changes. It is retained as a verified artifact; DESKTOP172 remains
installed while a combined newer package is prepared for native verification.

Global recording-health checkpoint: a compact footer action appears for a failed
telemetry writer, current rejected/failed records or retained earlier losses. It
distinguishes Telemetry log stopped from Telemetry gap and opens Monitor →
Diagnostics from any workbench page. Healthy/not-started recording has no visible
alert. Opening it never retries persistence, clears losses or sends CNC commands.
22 alert, spindle, diagnostics and receive checks passed (14.74 s, existing SSL
warning): /tmp/carvera-recording-alert-tests.log. Ruff lint/format and diff checks
passed. The installed footer interaction remains unverified; DESKTOP174 predates
this change. Complete recording recovery and all 25 full workflows remain open.

DESKTOP174 installed/native checkpoint (2026-10-05): frozen source
10ab103f65625bbdaf3b2e98293f9f754517f678 independently verified 488 files and
strict signatures, then installed at 19:20:23Z retaining DESKTOP172 for recovery.
Native Signal, Diagnostics and Baseline navigation and Command-K search/Return
invocation of diagnostics export were exercised. The exported receipt at
19:21:30Z retained a connected controller, 234 written telemetry records, zero
rejects/failures and unchanged hashes for all 18 tracked operator stores.
Native receipt: /private/tmp/carvera-desktop174-native-acceptance-20261005.json;
raw export: /private/tmp/carvera-desktop170-20261005/native-desktop174-acceptance.json.
Job-to-Monitor callback was 1.19 ms and window-flip notification 18.04 ms, but
startup heartbeat gaps of 2.56, 1.47 and 1.83 seconds remain observed. A latched
stale-telemetry monitor fault remained visible despite fresh packets; no feed
proposal was shown. No reset, adaptive actuation, motion, upload, tool change,
offset change or calibration was invoked. This closes the narrow installed
section-navigation and keyboard-export checks, not comprehensive responsiveness,
recording recovery error-path acceptance or any original full workflow.
The global recording-health footer at 2363de0 is newer than this installed build.

DESKTOP174 follow-up tab receipt at 19:26:27Z exercised all eight main workbench
tabs. Callback durations were 1.17–2.18 ms and window-flip notifications
6.26–75.16 ms, with no additional recorded heartbeat stalls beyond the three
startup episodes. Recording retained 1,521 written/zero rejected/zero failed
records. Raw receipt: /private/tmp/carvera-desktop170-20261005/native-desktop174-tabs.json.
This unloaded navigation sample does not qualify loaded-program workloads or
actual input-to-presentation latency. Broad local checks initially found 14
failures among 1,596 cases; older test doubles lacked added highlighting,
playback-refresh and diagnostics interfaces. Updated doubles preserve original
workflow assertions; all 42 affected-file cases passed. Full rerun remains pending.

PR checkpoint regression rerun: all 1,596 unit and focused monitor/telemetry/receive/
release-note integration cases passed in 107.45 seconds using Homebrew Python 3.9
and the installed package's HIDAPI library. Log:
/private/tmp/carvera-pr-checkpoint-tests-final-20261005.log. Full repository Ruff
lint and diff checks pass. Prior failed collection and 14-failure broad-run logs
remain retained. Draft fork PR #27 contains accumulated work; hosted CI and full
native/physical acceptance remain separate gates.

Camera calibration-reference checkpoint: the camera workbench captures an exact
immutable JPEG and separately received fresh machine pose, retaining source hash,
camera/connection generation and timestamps without storing the camera URL.
A contained frozen preview supports known XYZ point entry and pixel picking with
correspondence crosses; the main camera stays live. Fits use this reference rather
than the latest camera frame. Changed fields, camera/connection or machine-profile
ownership discard late results. Input changes require refitting before save and
withhold the draft overlay.
Schema-2 .cvcal files retain the JPEG hash, numeric correspondences, intrinsics and
reference pose; bounded decode validates dimensions, timestamps and identity.
Read/write/fit work is asynchronous and one-at-a-time. Exclusive export preserves
earlier files and independently reads back the written bytes; partial failures
remain retained. Schema-1 files remain readable but have no reference image and
their overlay is withheld. Exposure synchronization, intrinsic measurements and
physical correspondence qualification remain open.
59 camera archive/projection/overlay/client/reference and recorded-run regressions
passed in 24.86 seconds (existing SSL warning). Log:
/private/tmp/carvera-camera-reference-qualified-source-tests-20261005.log. Ruff
lint/format and diff checks pass. Installed DESKTOP174 predates this checkpoint;
native capture/picking/file roundtrip and portable-job/run calibration-image
association remain open. No original complete workflow closes here.

Calibration export readback is bounded to the bytes written plus one, so a
concurrent file enlargement cannot cause an unbounded read. Archive regressions
pass 12 cases after this change; this readback refinement is newer than the frozen
DESKTOP175 source 77bd48b24876f843de1a3fcf5afa26e293612eb9.

Portable calibration custody checkpoint: job and recorded-run setup archives now
retain a hash-checked .cvcal asset containing the exact reference JPEG, pose and
correspondences. UI capture snapshots declarations; encoding/validation occurs in
the archive worker. Imports validate calibration before asset installation, replace
the complete calibration panel state, and clear old imagery when the imported
setup has no reference. Legacy numeric registrations remain readable. Corrupt
inner image hashes are rejected even if the enclosing archive hash was recomputed.
77 focused portable-job, recording-setup and camera regressions passed in 23.13
seconds; log /private/tmp/carvera-portable-camera-tests-20261005.log. This source
checkpoint is newer than installed DESKTOP175.

DESKTOP175 package/install verification: frozen source
77bd48b24876f843de1a3fcf5afa26e293612eb9; 489 manifest files matched with strict
signature checks passing. Built verification receipt at 2026-10-05T19:40:04Z and
installed verification receipt at 19:40:41Z are retained under
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop175-20261005/. DESKTOP174 remains
as the recovery app. Native app title confirms DESKTOP175; direct connection to
the saved Carvera profile reports Idle with fresh telemetry, while the Ubuntu
camera stays live. Native reference capture retained frame 251 at 1280 x 720 and
observed table Y -195.285 mm. Exposure synchronization remains explicitly
unqualified. Pixel picking, native fitted-file roundtrip and physical calibration
acceptance remain open; no motion or adaptive actuation was invoked.

Camera workbench ergonomics/import responsiveness checkpoint: Source, Reference
and Fit & exchange occupy persistent sections with independent scrolling and
always-visible status. Switching releases hidden field focus and retains the
reference, point edits and intrinsic prior. Command-K can open each camera
section directly without configuring the camera or sending CNC commands.
Portable-job workers now validate fixture CAD, construct tool/stock declarations,
decode bounded rest-stock snapshots and write the installed program before UI
publication. A generation and machine/profile/program ownership guard withholds
late imports after newer requests or changed selections. Importing a job without
retained rest stock clears the previous residual result. Machine-profile
publication/GPU scene construction remain UI work and are not fully responsiveness
qualified. 55 combined camera/import/archive/recording/monitor regressions passed
in 11.26 seconds; six import-publication cases passed in 0.49 seconds after adding
successful publication coverage. Logs:
/private/tmp/carvera-camera-import-checkpoint-20261005.log and
/private/tmp/carvera-job-import-publication-tests-20261005.log. Full Ruff and diff
checks pass. These source changes are newer than installed DESKTOP175; native
section layout and loaded-import latency remain open.

Imported machine-profile preparation follow-up: the import worker now prepares
the retained machine CAD against a captured previous CAD reference. UI publication
accepts the prepared profile without loading its geometry again. A blocked-worker
regression proves Kivy clock callbacks continue while CAD preparation waits and
only the prepared object is passed to publication after release. All 22 async
profile/import regressions passed; log
/private/tmp/carvera-prepared-profile-acceptance-20261005.log. Ruff and diff checks
pass. This follow-up is newer than frozen DESKTOP176 source
05563a4a9c1b2075db00b8706f0cf2b7739aaaad. GPU publication and complete imported
scene transactionality remain separate open gates.

DESKTOP176 verification/install receipt: frozen source
05563a4a9c1b2075db00b8706f0cf2b7739aaaad; independent verification at
2026-10-05T19:51:30Z matched 489 manifest files with strict signature exit 0.
Installation readback at 19:51:52Z matched the same manifest/signature, preserving
DESKTOP175 as recovery. Receipts are under
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop176-20261005/. Native app title
confirms DESKTOP176, the three camera sections are visible, camera remains live
and reconnection reports Idle with fresh telemetry. Native reference-page review
found the image height still pushes controls below the fold at the installed
display scale. Source now reserves viewport room for the controls while preserving
contained image aspect; 14 camera regressions pass, including resized-viewport
coverage. Log /private/tmp/carvera-camera-height-tests-20261005.log. This correction
is newer than DESKTOP176 and is not native-qualified yet.

Hosted quality gate at eb85b70d2c8f9986a5b398be8e88ff50d86cba06 failed in run
37365934876: package-baseline mypy has 16 errors across seven files and strict
machine-layer mypy has 1,030 errors across 64 files. Ruff lint/format and
architectural import boundaries passed. Raw failure log is retained at
/private/tmp/carvera-pr27-quality-failure-20261005.log. Type-check completion is
open; local regression passes do not close hosted CI.

Type-repair checkpoint: quantity unit maps and arithmetic, variadic scene-group
relationships, inverse-time XYZ travel, program-comparison bounds, command
callback binding and archive name/calibration narrowing now have explicit types
or unambiguous bindings. Archive names are validated before object construction.
Release-note paging, generic navigation history, camera receipt-reader protocols,
program comparison and quantities pass strict checking in a five-module run with
imported-module diagnostics silent (mypy 1.20.2 on Python 3.11). This focused run
does not close full-package or hosted type checking. Local full-package checking
also reports 148 errors in imported addon modules; the earlier hosted baseline
had 16 errors, so environment/scope differences remain to reconcile. Exact logs:
/private/tmp/carvera-mypy-repaired-modules-final-20261005.log and
/private/tmp/carvera-mypy-baseline-after-types-20261005.log. Archive identity/type
regressions pass 22 cases after the final validation change; log
/private/tmp/carvera-job-identity-type-tests-20261005.log.

Orientation HUD regression: scene-edit overlays draw in canvas.after, so raising
the cube above only main-canvas geometry was insufficient. The cube now draws
last in canvas.after and is re-raised after the scene overlay is attached; removal
checks both layers to prevent duplicates. The strengthened program-rebuild
assertions check foreground ordering and a single HUD instance. All 179 combined
type-repair, command/navigation, program picker, scene-interaction and ATC overlay
regressions passed in 52.09 seconds (existing SSL warning); log
/private/tmp/carvera-type-and-hud-repair-tests-20261005.log. Earlier failed
orientation-layer receipts remain retained. Ruff, touched-file formatting and
diff checks pass. Installed DESKTOP176 predates these HUD/type repairs and the
viewport-aware camera-height correction. Native acceptance remains open.

Strict contract checkpoint: UI timing exports now use typed records, observations
and snapshots, preserving callback/flip/presentation distinctions. Window sizing
uses narrow configuration/window protocols. Scene selection/placement math now
uses mesh protocols, XYZ surface-hit contracts and typed rendered-tool snapshots;
2D and homogeneous helper vectors retain their arbitrary-dimensional semantics.
These three modules pass focused strict checking with imported diagnostics silent
(mypy 1.20.2/Python 3.11). Timing/window/monitor regressions pass 23 cases in 12.90
seconds; scene selection/placement/ATC-overlay regressions pass 47 in 30.99 seconds.
Logs: /private/tmp/carvera-timing-type-regressions-20261005.log and
/private/tmp/carvera-scene-type-regressions-20261005.log. Full local strict checking
still reports 1,491 errors across 76 files, including imported addons; exact log
/private/tmp/carvera-mypy-strict-scene-timing-checkpoint-20261005.log. Full type CI
remains open. These contracts are newer than frozen DESKTOP177 source a925005.


DESKTOP177 installed/native checkpoint: frozen source
`a92500599fed600b553b4ebcc038e22cb561c67b`. Independent built verification at
2026-10-05T20:06:18Z and installed readback at 20:08:05Z each matched 489 manifest
files with strict signature exit 0. DESKTOP176 is retained as recovery. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop177-20261005/built-verification.json
and artifact-verification.json. Native title confirms DESKTOP177; direct saved
profile reconnection reports Idle with fresh telemetry and live Ubuntu camera.
At 2340 x 1608, Reference image, capture, known XYZ and pixel-pick controls fit
without scrolling. Capture freezes frame 79 at 1280 x 720; Reference survives
Fit & exchange navigation, the main camera continues live, and a pixel click
with blank XYZ is rejected visibly. No measured correspondence or fitted physical
calibration is claimed. Package includes portable calibration, worker-prepared
imports and the foreground HUD correction; complete native loaded-job/HUD
interaction remains open. Timing/window/scene contracts at d420459 and subsequent
source repairs are newer than this installed artifact.

Native diagnostic export at 2026-10-05T20:09:50Z was independently read back from
/private/tmp/carvera-desktop170-20261005/native-desktop177-acceptance.json, SHA256
b3a2166d55b11c1405ce3ecb99fbcb9154851aef19b9c88bab9869f2a04bc763.
Export reports 324 written telemetry records, no rejects/failures, and an irregular
arrival window with one 0.994-second receive gap. Ordinary Job-to-Machine and
Machine-to-Camera callbacks were 1.90/1.11 ms and window-flip notifications
40.47/17.82 ms. Startup had a 3.376-second flip notification delay. These are
local notification observations, not input-to-presentation or machine latency
qualification. All 18 tracked operator-store hashes match the saved baseline.
No motion, upload, tool change, offset change or adaptive actuation was invoked.


Camera/joint/bounds type checkpoint: camera-fitting residual callbacks and Huber
loss now have explicit numerical contracts. Inverse-time joint demand returns,
limit flags and cancellation callbacks are typed. Indexed geometry bounds and
immutable snapshot fields use exact XYZ pairs, and scene inspection accepts the
shared indexed-mesh protocol. Existing arithmetic/validation behavior is retained.
Three machine modules pass focused strict checking with imported diagnostics
silent; 50 camera, inverse-time, scene-bounds and native-inspector regressions pass
in 16.01 seconds (existing SSL warning). Logs:
/private/tmp/carvera-camera-joint-bounds-types-final-20261005.log and
/private/tmp/carvera-camera-joint-bounds-regressions-final-20261005.log. The first
attempt used an incorrect protocol import name; the collection/type failures are
retained in the corresponding non-final logs. Full Ruff and touched-file format
checks pass. Full-package/hosted type checking and physical qualification remain
open. This source checkpoint is newer than installed DESKTOP177.


Hosted d420459 checkpoint: run 37367558768 completed at
2026-10-05T20:11:53Z. Package-baseline mypy, Ruff lint/format and import-linter
passed; strict machine-layer mypy remains failing with 905 errors across 56 files
(84 checked source files). Full quality and downstream test steps remain open.
Raw receipt: /private/tmp/carvera-pr27-quality-d420459-failure-20261005.log.
This closes the hosted baseline type repair only for d420459, not strict typing
or the newer camera/joint/bounds source checkpoint.


Profile/custody/capability checkpoint: library snapshots now distinguish their
schema and profile collections, local persistence/change tokens are typed, and
tool-definition conversion supplies named dimensional arguments. Tool history
uses typed store/event containers and a raw-calibration receipt protocol; exact
number validation retains original int/float values and stale-review rejection.
Observed XYZ poses and UI stall snapshots now have exact coordinate/record types.
Five modules pass focused strict checks with imported diagnostics silent; full
local strict checking still reports 1,304 errors in 68 files (84 checked files,
including imported addon diagnostics), down from the prior local 1,491/76 scope.
Baseline local checking remains at the previously observed 148 imported-addon
errors. Logs: /private/tmp/carvera-profile-custody-types-20261005.log,
/private/tmp/carvera-pose-stall-capability-types-final-20261005.log,
/private/tmp/carvera-profile-custody-full-strict-20261005.log and
/private/tmp/carvera-profile-custody-baseline-20261005.log. This does not close CI.

Capability exchange now rejects coercive execution flags such as string "false",
noninteger revisions/slots, malformed arrays, nonfinite/boolean numeric evidence
and invalid axis limits. Exact false remains offline even with a declared supported
feature; exchange never invokes transport. Focused profile/custody/bench/import
regressions passed 93 cases; capability/pose/stall regressions passed 54. The broad
unit suite plus profile/bench/async-profile/capability integrations passed 1,646
cases in 58.90 seconds. Logs are under /private/tmp/carvera-profile-custody-regressions-
20261005.log, carvera-capability-exchange-regressions-20261005.log and
carvera-profile-capability-broad-regressions-20261005.log.

Workbench header now keeps setup evidence in Program, Scene, Setup and Setup
Evidence. Camera/Machine/Spindle/Console/Position regain that space while preserving
connection/hold/stop and Live/Preview context. Navigation releases focus from the
removed strip and restores one instance above the inspector content. All 56
workspace/camera-reference integrations pass in 34.84 seconds, covering restored
ordering, increased inspector height, retained views and zero command sends. The
run has the existing SSL warning and retained Kivy destructor diagnostics during
teardown. Log: /private/tmp/carvera-contextual-header-regressions-20261005.log.
Full Ruff and touched-file format/diff checks pass. These changes are newer than
installed DESKTOP177; native contextual-header acceptance remains open.


DESKTOP178 package/native checkpoint (2026-10-05T20:31Z): frozen source
`e979cfaabf8babf793cac44c17875a5fa2e1dabc` built and installed as
2.1.0-DESKTOP178. Independent built verification at 20:27:18Z and installed
verification at 20:27:40Z each matched all 489 manifest files with zero mismatches
and passed signature verification. DESKTOP177 remains available as recovery.
Receipts: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop178-20261005/
{built-verification,artifact-verification,native-acceptance}.json.
Native CUA review at 2340x1608 reconnected the saved profile: configuration
loading completed, Idle and fresh telemetry were observed, with live camera
frames and no remote file selected. Setup restores its evidence strip once;
Machine and Camera omit it, reclaiming 88 screen pixels. Reference capture, XYZ
and pick controls fit without scrolling. All 18 tracked operator-store hashes
remain unchanged. No motion, upload, tool change, offset change or adaptive
actuation was invoked. This closes this package/install and contextual-header
review scope; measured registration, full responsiveness and the original 25
end-to-end requirements remain open. Source CI run 37369178168 was queued at
readback; full strict CI is not closed.


Camera exchange/review source checkpoint: calibration/reference payloads, exact
XYZ poses and decoded results are typed. Imported timestamps and table positions
require finite exact numeric values; boolean/string/overflow values are rejected
before destination creation. A present malformed image record no longer silently
becomes absent. Nullable unqualified capture/pose evidence and schema-1 legacy
exchange remain supported. Fit & exchange now shows bound frame, correspondence
count and current/refit-needed state; Save is unavailable during work or with
stale/missing registration. Failed import preserves the prior reviewed image,
registration and points. Focused camera/file/job/overlay/recorded-setup checks:
93 passed in 13.62s with the existing SSL warning. Full Ruff lint/format pass;
calibration exchange passes focused strict typing with imported diagnostics
silent. Native review of this newer UI remains open; DESKTOP178 is installed.
Logs: /private/tmp/carvera-calibration-review-final-20261005.log.
Hosted b95d2f8 run 37370204211 completed: baseline mypy, Ruff lint/format and
import-linter pass; strict machine mypy fails with 724 errors in 48 files (84
checked), down from the earlier 905/56 checkpoint. CI is still open; downstream
tests did not run. Raw receipt: /private/tmp/carvera-pr27-quality-b95d2f8-failure-
20261005.log.


DESKTOP179 package/native checkpoint: built and installed from application source
`89f57433d1277786b3aef866447eee3808e0c29f`. Both independent manifest/signature
checks matched 489 files with zero mismatches; installed verification timestamp
2026-10-05T20:41:55Z. DESKTOP178 is retained as recovery. Native review at
2340x1608 reconnected the saved profile and observed Idle, fresh telemetry and
live camera with no remote file selected. Fit review transitioned from no image
to scratch frame 97 (1280x720, zero correspondences); Save stayed unavailable
until fitting. Loading the boolean-timestamp test file displayed a controlled
validation error, and the frozen reference image/frame/pose remained intact.
All 18 tracked operator-store hashes match baseline. No machine motion, upload,
tool change, offset change or adaptive actuation was invoked. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop179-20261005/
{built-verification,artifact-verification,native-acceptance,build-runtime}.json.
This closes the bounded native summary/rejected-import scope; valid fitted-file
roundtrip and physical image/datum qualification remain open. Broad unit plus
camera-reference regressions passed 1,688 tests in 37.17s. Full local strict
typing reports 1,288 errors in 67 files, including imported-addon diagnostics;
it is still failing and not equivalent to hosted scope. Log:
/private/tmp/carvera-calibration-full-strict-20261005.log.
The first packaging attempt selected an interpreter without PyInstaller and
terminated before packaging; its log is retained. Corrected packaging uses
/usr/bin/python3 with /private/tmp/carvera-receipt-ui-deps-20261005. Build tooling
now checks PyInstaller/Kivy/PIL availability and identifies the interpreter
before staging files. All seven build-preflight tests pass. This tooling change
follows the frozen application source and does not change installed app code.


Job telemetry source checkpoint: work position, reported tool/length offset and
spindle/feed now use separate two-line fields in an adaptive grid. The prior
shortened multi-line label collapsed all three records into one crowded line.
Narrow panes stack the fields, wider panes retain two or three columns, and
disconnected state replaces old numeric values with unavailable/preview text.
Reflow/texture-height checks cover 360/650/1000dp widths without command sends.
Workspace and assembly-preview checks passed 50 cases in 43.18s with the existing
SSL warning; capability inspector/map checks passed 10 cases in 2.75s. Assembly
resolution and current-session capability observation/row records have typed
contracts; both modules pass focused strict checks with imported diagnostics
silent. Full Ruff lint/format pass. Native status-layout acceptance remains open
until a package includes these changes. Logs: /private/tmp/carvera-job-telemetry-
assembly-corrected-20261005.log and carvera-capability-row-types-20261005.log.
Hosted d361e18 run 37371584115 passed baseline mypy, Ruff and import-linter;
strict machine mypy failed with 708 errors in 47 files (84 checked). Full CI and
downstream hosted tests remain open. Raw log: /private/tmp/carvera-pr27-quality-
d361e18-failure-20261005.log.


DESKTOP180 package/native checkpoint: application source
`5191373b269f018cb669476fc946fa3a3b9d5264`; independently built and installed
manifest/signature checks matched 489 files with zero mismatches. Installed
verification timestamp: 2026-10-05T20:59:37Z. DESKTOP179 remains as recovery.
Native CUA review at 2340x1608 observed automatic saved-profile reconnect, Idle,
Live/fresh reported pose, 0 RPM/feed and the Ubuntu camera. Position and reported
tool/TLO appear in separate two-line fields; spindle/feed wraps to the next grid
row without clipping. No program or remote file was selected. All 18 tracked
operator-store hashes match baseline; no actuation was invoked. This closes the
bounded native telemetry-layout review only. Loaded-job responsiveness, full
workflow and physical qualification remain open. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop180-20261005/
{built-verification,artifact-verification,native-acceptance,build-request}.json.
The first build preflight refused the system temporary volume's 0.64 GiB free
space against its 1 GiB reserve. The corrected build used a temporary directory
on the build volume and passed; no reserve was weakened or files deleted.
Both attempt logs are retained in /private/tmp/carvera-desktop180-build-
{20261005,external-temp-20261005}.log.
Broad current-source unit plus workspace/assembly/capability integration checks
passed 1,726 tests in 83.02s. Full local strict typing still fails with 1,277
errors in 65 files, including imported-addon diagnostics (84 files checked),
and is not equivalent to the hosted scope. Logs:
/private/tmp/carvera-job-telemetry-broad-20261005.log and
/private/tmp/carvera-job-telemetry-full-strict-20261005.log.


Loaded-job context refresh now uses a preparation-time resolved-motion tool/line
index rather than scanning all segments on every UI refresh. Exact inclusive
operation queries, unknown tools, replacement and tool/setup invalidation have
source and rendered regressions. The affected 47-test suite and broad 1,684-test
unit/geometry-change/tab suite pass. A 300,000-segment source context/digest
benchmark retained identical results while median work fell from 11.483 to
0.094 ms; this does not prove native latency. ProgramOperations now passes
focused strict typing; full local/hosted strict remain failing. Package/native
loaded-job acceptance remains open. Details: docs/ui-responsiveness.md.


DESKTOP181 packaged, independently verified and installed from application
source 8033087bbd75c428a34a0aad8b81ffdafc65c55d. Native local 6,000-move
preview loading, operation selection, missing-tool readiness and five workspace
screens passed bounded review without CNC transport/actuation. The 18 operator
stores matched; normal relaunch is Live/Idle with fresh camera/telemetry and no
program selected. DESKTOP180 recovery remains local; DESKTOP179 recovery and
the failed no-space staging attempt are verified/preserved on the build volume.
Details and unresolved responsiveness/installer gates: docs/ui-responsiveness.md.


Five-axis source checkpoint: the Machine workbench now has bounded JSON geometry
import, unit-aware targets, one-to-eight seeded branch comparisons, cooperative
cancellation and highlighted result selection. Joint limits, equivalent rotary
endpoints and a tangent-projected local rank diagnostic are explicit. Input edits
and panel closure discard pending results; imported-file and canonical profile
fingerprints remain separate. Broad unit/tab/capability/branch regressions passed
1,709 tests; the new machine review module passes focused strict typing and full
Ruff checks pass. Installed DESKTOP181 predates this increment; native panel and
advanced backend/physical qualification remain open. Schema and limits:
`docs/kinematic-profile-schema.md`. The preceding documentation-head hosted run
37375157315 is terminal failure at strict machine typing (684 errors, 44 files);
baseline/lint/architecture passed and hosted tests did not run.

Final declared-branch/narrow-layout/hole regression suite: 73 passed in 21.48s
(existing LibreSSL/urllib3 warning). A rendered root-window test exposed a
self-parent traversal hang; planning/hole disclosures and shared scroll reveal
now guard ancestor cycles. Full local strict typing remains failing at 1,262
errors in 64 files, including imported-addon diagnostics (85 files checked);
configuration has not been weakened. Failed/interrupted layout attempts and
corrected checks are retained under /private/tmp/carvera-kinematic-review-*.log.

Final branch/shared-reveal/program-task regressions passed 18 tests in 21.10s,
including a self-parent window regression. The installed version file was
independently read back as 2.1.0-DESKTOP181; the new source is not yet installed.


DESKTOP182 package/native checkpoint: built and installed from
`8a1759c26ef913c278c08e64d8c3ab9afa3b299c`; independent hashes/signature
verification matched 491 source files, zero mismatches. Installed timestamp:
2026-10-05T21:44:32.909200Z. DESKTOP181 is retained as recovery. The new
installer checks source/version/identity/signature, free copied-file capacity plus
1 GiB reserve before copying, staging and installed hashes/signatures, and
controlled-failure restoration while retaining failed artifacts. Its 12 focused
regressions pass; power loss and a second rollback filesystem failure are not
guaranteed. Procedure: `docs/verified-macos-updates.md`.
Native CUA review at 2340x1608 and 1864x1306 observed panel expansion,
0.5 in -> 12.7 mm, two local seed solves, selected result details, a valid
declared head/table import with fingerprints, and rejection of a TCP-support
assertion preserving that profile. All 18 operator stores matched before/after;
no restoration or CNC actuation was invoked. Normal relaunch is Live/Idle with
fresh reported pose/camera, 0 RPM/feed and no program/remote file selected.
Receipt root: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop182-20261005/
{built-verification,artifact-verification,native-acceptance,build-request}.json.
Native review exposed chain glyphs, an initial empty-results gap, coinciding
seed solutions and a narrow navigation row with a lone Profiles button.
Source fixes for the first three pass 74 focused tests: ASCII chain separators,
zero initial results height, seed labels/coincidence warning, paired rotary
seeds and a trunnion-style B-then-C table example with five independent local
task directions when tilted. These follow-up fixes are not yet packaged; narrow
navigation density and instrumented native latency remain open. Full advanced
workflow and physical/backend qualification remain open. Hosted run 37376791085
on 8a1759c is terminal failure at strict machine typing (684 errors, 44 files);
baseline/lint/architecture pass and downstream hosted tests did not run.


Camera capture/recording contract checkpoint (2026-10-05): accepted-frame,
worker status, retained header/frame, replay association and bundle receipt
contracts are explicit. Snapshot HTTP response/opening and camera observer
contracts remain independent of CNC and Kivy. Replay validates identities and
field types before accepting typed retained data; malformed session identities
now produce a controlled ValueError rather than incidental UUID attribute errors.
Twelve valid-digest-chain malformed-field cases supplement the existing custody,
queue-loss, source-gap, bundle and workbench tests. The combined batch passed
85 tests; focused strict checks pass for camera_run and webcam. Full local
strict scope still fails with 1,181 errors in 62 files (85 source files checked),
down from the prior 1,262/64 local checkpoint. Full local baseline still reports
148 errors in 19 files including imported addons; hosted scope is separate.
No ignore/configuration changes were introduced. These source checks do not
close native recording or physical camera registration acceptance.


DESKTOP183 is installed from d9c1b414792c63f376133ea3b18d8649b94fb239;
manifest/signature and bounded native navigation/local-seed review receipts are
recorded in docs/ui-responsiveness.md. The hosted d9c1b41 quality run
37379584024 is terminal with 603 strict errors in 42 files, down from 684/44;
downstream hosted tests did not run. Full local and hosted scopes remain
separate. The native short-window Program finding has a source overflow followup
that is not yet installed; the overall 25-requirement scope remains open.


Status recording/replay contract and keyboard checkpoint (2026-10-05):
run_recording now declares program/setup/configuration bindings, retained packet,
gap/connection-boundary events, summaries and replay associations. Archive data
is typed only after existing runtime validation. Invalid non-mapping packets and
non-byte archive input produce controlled failures without changing retained
observations. The camera navigation protocol consumes the actual validated
recording payload and accepts CameraRunReplay through a positional receipt-clock
contract; a focused caller check verifies the concrete pair.

The Run record timeline is keyboard focusable with an accent focus outline:
Left/Right step, Home/End select first/last, and Space toggles receipt playback.
Seeking pauses playback. Shared focus handling disables keyboard jogging, reveals
the focused control and releases hidden focus. Modal dialogs block timeline keys;
key releases are consumed for activated controls. These are local archive controls.
The combined status/camera/archive/workbench batch passed 74 tests in 20.49s
(existing LibreSSL warning), including keyboard/modal/task-switch isolation and
malformed-input preservation. Both changed machine modules and their concrete
camera/status caller pass focused strict typing. Full Ruff/format/diff checks
pass. Full local strict typing remains open: 1,134 errors in 61 files (85 checked),
down from 1,181/62. No checks were weakened. The preceding hosted run 37380792179
at aceceb67 failed strict machine typing with 603 errors in 42 files; downstream
tests did not run. This checkpoint and the Program overflow fix are source-only;
installed DESKTOP183 remains at d9c1b41. Native keyboard/replay acceptance and the
full 25-requirement/advanced-backend/physical qualification gates remain open.


Declared joint-transition checkpoint (2026-10-05): two to eight ordered joint
waypoints are sampled with explicit linear/rotary spacing and a 2001-sample
budget. Full turns remain as entered. Local rank diagnostics identify dependent
interior postures even when endpoints have full rank. The workbench adds a
collapsible transition section, unit-aware sample-step editors, selectable rank
trace, keyboard-operable sample actions, per-joint travel/margins and tip/axis
readback. Locally solved endpoints can be explicitly copied into waypoint rows.
Dense diagnostic ticks use one mesh, not one drawing instruction per sample.
The final branch/path/workbench batch passed 45 tests in 15.05s; focused strict
typing and both architecture contracts pass. Full Ruff/format/diff pass. Full
local strict scope still reports 1,134 errors in 61 files (86 source files
checked); the new module adds no diagnostics. Hosted d217532 run 37381472794
failed with 556 strict errors in 41 files (85 checked); baseline/lint/architecture
passed, downstream tests did not run. No check configuration was weakened.
See joint-transition-review.md. Between-sample behavior, physical clearance,
controller interpolation/rates/TCP/backend execution remain unqualified.
DESKTOP184 packaging/native review is a separate gate; the full scope stays open.


DESKTOP184 native checkpoint (2026-10-05): installed source 0b9b921 independently
matched 492 manifest files with zero mismatches and a valid strict signature.
Native CUA review at 2340x1608 and 1864x1306 verified Program scroll reachability
without overlap; freezing 168 received status events, Home/End selection and
Space playback/pause; and the 91-sample head/head joint route, selecting full-rank
endpoints and rank-4/5 interior sample 46. Live camera and reported Idle telemetry
continued. All 18 tracked operator stores matched the preupdate backup. Final
normal Program/Operations view reported T1/TLO50.480, zero spindle/feed and no
selected program/remote file. No motion, upload, toolchange, offset or adaptive
actuation was invoked. Receipts are under
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop184-20261005/`.

A native observation prompted a source followup: returning to the live recording
buffer disables archive step actions and resets its disabled cursor rather than
retaining a misleading partial archive position. This followup postdates the
installed DESKTOP184 source. Camera archive native roundtrip, loaded-job latency,
complete branch/path workflows and physical qualification remain open.


Indexed setup checkpoint (2026-10-05): fixed rotary angles and declared tool/work
geometry map up to eight work points to exactly three independent linear axes.
Head/head, head/table and table/table topologies, shifted pivots/bases, work-chain
linear axes and non-orthogonal bases participate in the affine solve. Any invalid
point rejects the whole result; dependent bases, stale results and cancellation
do not publish. Workbench controls copy a selected branch orientation explicitly,
inspect individual mapped points and hand off joint waypoints to separate route
review. Narrow forms reserve the actual multiline-field height and fit compact
point-choice captions. See indexed-setup-review.md. Backend/postprocessor,
indexing approach, physical travel/clearance and complete native acceptance remain
open; local mapping does not certify a cutting workflow.


DESKTOP185 bounded native checkpoint (2026-10-05): frozen source 9543153
independently matched 493 manifest files with zero mismatches and a valid strict
signature. Native CUA review mapped the two default head/head work points at
fixed C0/B30 with 5 mm tip offset, selected point 2 (X22.5/Y15/Z29.33), copied
the explicit joint route and reviewed six samples with 2 mm tip step, zero axis
change and zero chord deviation. Last-sample details remained reachable at
1864x1306 and selected state survived widening to 2340x1608. Freezing 583 status
receipts and returning to the live buffer disabled archive stepping and reset
the cursor. Live camera/telemetry continued; final Program/Operations view
reported Idle C1, T1/TLO50.480, spindle/feed zero and no selected program/remote
file. All 18 tracked operator stores matched the backup. No motion, upload,
toolchange, offset application or adaptive actuation was invoked.
Receipts: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop185-20261005/`.
Native selected-branch/custom-profile indexed workflows, camera archive
roundtrip, loaded-job latency, physical indexing/clearance and backend execution
remain open. The packaging-tool preflight source followup postdates this frozen
controller build. The full original and supplemental requirement sets remain
open; this receipt closes only the stated bounded native cases.

Camera viewing recovery checkpoint (2026-10-05): the existing Ubuntu camera
service was active; the missing Mac loopback forward was restored as a supervised
user LaunchAgent. Current host identity was verified over authenticated Tailscale
SSH and separately pinned with strict checking. Native DESKTOP186 again displayed
a live camera frame with 0.1-second age. Controlled forward termination recovered
automatically under a new PID; independent JPEG readback measured 0.064-second age.
Direct Mac-to-CNC control remained unchanged. See camera-forward-recovery.md.
Physical registration/synchronization and complete camera workflows remain open.

Spindle validation checkpoint (2026-10-05): malformed signals and invalid monitor
clocks latch faults without replacing valid sample history. Explicit baseline
recapture now starts a fresh five-second signal sequence while retaining earlier
arrival gaps. The signal panel reports elapsed capture time/sample count and
paused/captured states with wrapping text. All 101 focused monitor/feed/quality/
persistence/recovery/UI regressions pass, both changed machine modules pass strict
typing, and lint/format/architecture checks pass. Full local strict typing remains
open at 1,016 errors in 56 files (88 checked); this scope differs from hosted CI.
See spindle-monitor-validation.md. Changes postdate installed DESKTOP186; native
acceptance and qualified adaptive actuation remain open. Shadow sends no commands.

Tool-bank evidence checkpoint (2026-10-05 UTC): bank cards filter missing evidence
or selected assemblies and open an inline full assessment/raw-receipt review.
Logical and mapped controller receipts stay distinct; every raw sample is reachable
through bounded 80-sample pages. New pages start at the top, stale contexts clear
prior evidence, and compact action captions fit 360/760 dp layouts. Canonical
record validation rejects duplicate logical-tool bindings, malformed fields and
unbounded reads. All 69 bank/custody/mapped-program regressions pass; the changed
engine passes focused strict typing; lint/format/architecture pass. Full local strict
typing remains open at 980 errors in 55 files (88 checked). See
tool-bank-evidence-review.md. Installed and physical reload/re-entry acceptance
remain open; the original and supplemental full requirement sets are unchanged.

Repeat-plan persistence/review checkpoint (2026-10-06 UTC): explicit plan/stock/frame
contracts reject malformed and overflowing coordinates; canonical digest comparison
and a cooperating-writer lock protect per-machine saves. Background plan I/O keeps
navigation available, retains an authorized original-owner save snapshot and rejects
stale restore callbacks. Frame details show declared datum/bounds/stock separation;
active tabs and full-height quantity rows improve narrow layout. All 80 repeat/
simulation/archive/playback/geometry/UI regressions pass; the changed engine passes
focused strict typing; lint/format/diff/architecture pass. Full local strict remains
open at 906 errors in 54 files (88 checked). See repeat-parts.md. Changes postdate
installed DESKTOP186; measured offset transactions, repeat execution/inspection,
installed acceptance and the full original/supplemental requirements remain open.


Repeat-plan editing checkpoint (2026-10-06 UTC): regular saved arrays synchronize
layout inputs; custom frame tables retain individual geometry and require an explicit
new-array action before grid replacement. A collapsible selected-part editor validates
name/WCS/datum/origin/size before publication, preserves neighbors and clears stale
machine-context fields. Source narrow-layout review and focused strict/lint/format/
architecture checks pass. Full strict/package diagnostics remain open and unchanged.
See repeat-parts.md; installed workflow, measured frames and repeat execution remain
open. No controller offsets or execution commands are dispatched by editing.


Repeat draft ergonomics checkpoint (2026-10-06 UTC): pending per-part text survives
selection, shows status/count, and supports validated atomic Apply all plus explicit
single/all discard. A full-width name row and guarded save/restore/array replacement
prevent editing/navigation from silently losing or omitting pending values. All 87
repeat/simulation/archive/playback/geometry/UI tests pass; lint/format/diff/architecture
pass. Full strict and installed/physical acceptance remain open. See repeat-parts.md.


Repeat-plan persistence ergonomics checkpoint (2026-10-06 UTC): common Save/Restore
controls stay available on all repeat pages, with revision-aware status and disabled
pending-edit actions. All 88 local repeat/simulation/archive/playback/geometry/UI
regressions pass, including concurrent-save preservation and explicit restore of
the newer revision. Lint/format/diff/architecture pass; strict and physical acceptance
remain open. DESKTOP187 independently verifies native draft retention, bulk apply,
discard and clean restart (496 source files, strict signatures, nine operator JSON
files unchanged), with native save/restore still open at that frozen checkpoint.
See repeat-parts.md for evidence and the distinction between current disk state and
last-read/saved revision. The original and supplemental requirements remain intact.


Multi-form threadmill source checkpoint (2026-10-06 UTC): loaded profiles carry explicit complete tooth count and tip datum; hole previews use one-pitch radial passes with stack, floor, bottom and reach checks. Recipe restoration and physical assembly review compare those fields, nominal visualization shows the declared tooth cells, and the workbench summary explains axial coverage/reference with stable narrow-layout wrapping. See multiform-threadmilling.md. Installed DESKTOP188 predates this source; native complete workflow, true thread grooves, manufacturer geometry/reference and physical cutting/inspection remain open. The full original and supplemental scope remains intact.


Physical cutter lifecycle source checkpoint (2026-10-06 UTC): physical assemblies now retain explicit cutting-use intervals, operator inspections with optional measured diameter, and reviewed replacement links. Replacement preserves old calibration/use history and blocks new declarations for the retired identity; chronological, duplicate, stale and cycle checks reject atomically. A dedicated passport section provides complete bounded history pages, concentrated compact actions, synchronized assembly captions and background writes with original-store ownership. See tool-lifecycle.md. Native installed workflow, observed execution attribution, physically qualified wear/replacement and full original/supplemental requirements remain open. No controller commands are dispatched.

Lifecycle source validation: 109 focused lifecycle/custody/passport/process/bank/UI tests pass; changed custody/lifecycle/bank engines pass strict checking; full lint/format/diff and two architectural contracts pass. Full local machine strict typing remains 883 errors in 54 files (89 checked), package baseline 148 errors in 19 files (186 checked). No check configuration was weakened.

Long-form custody ergonomics checkpoint (2026-10-06 UTC): anchored overlapping-page
scroll controls expose final fields without submitting drafts, disable at boundaries
and disappear on fitting forms. Field/scrollbar separation, vertical-only motion and
collapsed empty validation space improve compact layout. Full-app pointer routing,
compact navigation and related focus/custody/process checks pass (8 + 37 tests);
360 dp rendering was inspected. The prior native scrollbar discrepancy and next
installed navigation acceptance remain open. See tool-lifecycle.md; the complete
original and supplemental scope remains intact.
