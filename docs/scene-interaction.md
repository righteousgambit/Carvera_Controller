# Direct scene interaction

## Component cutaways

Scene / Inspect component / Dimensioned section now offers Full component,
Keep below plane and Keep above plane. The X/Y/Z plane is in the nominal CAD
frame before group motion, matching the numerical slice. Each component keeps
its cutaway during in-session selection changes. The renderer clips fragments
without rebuilding CAD buffers, changing setup dimensions, moving the machine
or generating a closed cap. Stock outlines use the same clipping shader.
Components not selected for a cutaway, toolpaths and cutter geometry retain
their existing views.

Picking checks the same plane in the untranslated component coordinates and
skips removed triangles. A changed cutaway invalidates in-flight picking and
existing picked-surface probe previews. Invalid/nonfinite/overflowing plane
inputs restore the full component and report the problem inline. Midplane joins
the responsive action grid so the plane-coordinate field remains usable at
360 rendered pixels. The compact controls were rendered and inspected.

Cross-session persistence, arbitrary feature-aligned planes, exploded views,
complete installed interaction and physical geometry registration remain OPEN.
The source GPU regression reads actual pixels for both half-spaces and full
restoration; the initial uninitialized-OpenGL-window crash log is retained at
`/private/tmp/carvera-cutaway-gpu-20261006.log`. The corrected isolated GPU
receipt is `/private/tmp/carvera-cutaway-gpu-window-20261006.log`.

Scene workbench controls select a rendered component or edit stock/vise placement
in local preview coordinates. View mode preserves orbit, pan, zoom and the view cube.
Pick component intersects the actual indexed triangles, including current table
translation; empty space inside a component's bounds is not a surface hit.
Picking runs in a worker and delivery rejects changed geometry, camera, viewport,
visibility, task or mode.

Move XY and Move Z enter Preview and show a handle at the selected stock/vise
center. Drag the handle, with an optional millimetre grid snap (zero disables it),
then release to open the existing setup editor with the proposed coordinates.
Apply validates and saves the local per-machine setup; Cancel preserves the active
and saved setup. During the drag the mesh and saved setup remain unchanged.
A retained setup draft must be reviewed before another gesture can replace it.
Gestures are discarded if setup, geometry, profile, camera, viewport or machine
state changes. An invalid ray discards the entire gesture. Z movement requires
an angled view so the placement plane can be intersected.

Unprojection uses a full homogeneous 4x4 inverse of the renderer's projection and
modelview matrices, with perspective division and the render-to-machine frame
conversion. It does not substitute an affine inverse for perspective projection.

This UI edits declarations only: it sends no motion, offset, calibration or tool
change commands. Placement is not physical registration. Enclosure surfaces can
occlude inner components; hide the enclosure to select those surfaces.

Remaining scope includes stock/general rotation, calibrated fixture-hole snapping,
clipping/exploded views and native interaction acceptance.

Source acceptance: 23 focused tests passed; the final render/drag check exercises
the real stock handle, reviewed draft and cancel path. The screen-space overlay
shares the renderer's exact window viewport origin and converts parent-relative
touches explicitly. Controls sit above the component inspector in a responsive
panel. Native installed acceptance remains separate.

## Vise rotation

Rotate vise Z shows a projected XY ring around the registered vise's source CAD
pivot, including its current placement and table translation. It requires visible
vise geometry. Dragging the ring accumulates signed angle increments across the
180-degree boundary; angle snap is independently editable in degrees or radians
(zero disables snapping). Release opens a workholding setup draft with the new
canonical angle in [-180, 180) degrees. Translation and jaw settings remain
unchanged. The shared context checks, retained-draft protection and apply/cancel
transaction remain in force. The ring is a local declaration, not a measured
mounting registration or a machine-motion control. Stock rotation remains open.

Rotation source checkpoint: 28 combined interaction tests passed (63.49s), followed
by 12 pure tests after normalizing large angular vectors to avoid multiplication
overflow. Actual vise-ring dragging, pivot placement, angular snap, apply/save and
cancel were exercised in the isolated application. Render
`/tmp/carvera-vise-rotation0002.png` was reviewed. Receipts:
`/tmp/carvera-vise-rotation-tests.log`, `/tmp/carvera-rotation-numerics-tests.log`.
Both import contracts passed (216 files, 938 dependencies). This work postdates
DESKTOP144's frozen source and has no installed/native acceptance yet.


## Displayed cutter selection and component framing

Picking now includes the displayed cutter/holder triangles with the exact pointer
shader transform, render scale, center and work offset. It works with the machine
CAD shown or hidden and respects the near/far clip interval. Hidden cutters are
excluded. Immutable UI-thread snapshots carry tool number, mesh identity, geometry,
pose and view; a same-number tool replacement or later camera/visibility change
rejects the worker result. No CAD files are read during picking.

Frame selected fits the visible component or displayed cutter in the viewport,
with a conservative bounding sphere and margin. Cutter geometry processing runs
in a worker. Delivery rejects changed selection, scene, pose, camera, viewport,
visibility or task, preserving an operator camera adjustment made while the
request runs. Framing changes only the local camera; it does not save a setup or
send controller commands.

The combined source suite passed 35 tests (173.86s, one existing locale warning)
including cutter selection with machine CAD on/off, same-number geometry replacement,
all referenced cutter vertices inside the framed viewport, reviewed rotation and
translation, and no-machine-command assertions. Receipt:
`/tmp/carvera-scene-interaction-complete-tests.log`. A subsequent task-context guard
also prevents late framing after leaving Scene; its focused receipt is
`/tmp/carvera-framing-context-tests.log`. Earlier failed mock-ray, loader and
visibility-isolation attempts remain in the picking/framing logs under `/tmp`.
These changes postdate DESKTOP144 and await installed/native acceptance.


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


Displayed identity checkpoint: the inspector now reads the current rendered mesh's
tool number rather than substituting the next requested tool. If the number is
pending or unavailable it reports that explicitly; dimensions and assembly links
follow the displayed identity. Four focused source tests passed (92.36s, one
existing locale warning), including both asynchronous framing context guards and
pending/unknown cutter identity. The test process exited zero. Receipt:
`/tmp/carvera-frame-inspector-final-tests.log`. This closes the previously OPEN
source regression gate for the task-change guard; installed acceptance is still
open. Ruff lint/format, diff checks and both architecture contracts passed.

The earlier 60-second full-app fixture timeout and hung cleanup are retained in
`/tmp/carvera-framing-context-tests.log`; the isolated failed process was stopped
with exit 137 before the longer-timeout rerun. The separate DESKTOP144 build was
not interrupted or duplicated.

Stock rotation remains open. Its implementation must carry orientation through the
stock declaration/schema, source CAD and wireframe rendering, setup editor/apply/
cancel/restart, job/recording custody, simulation occupancy and persisted rest stock,
stock/path engagement and facing boundaries. Rotating only the displayed box would
leave those calculations describing different stock. General rotation requires
explicit pivot/frame semantics and transformed cutting/collision geometry.


## Oriented-stock engine checkpoint

StockVolume now supports a fixed program-Z rotation and explicit pivot, preserving
local grid dimensions and cell volume. Candidate sweep bounds transform back into
the grid, while continuous removal tests use transformed program-coordinate cell
centers. Rest-stock triangles and normals transform exactly; conservative enclosing
boxes are reserved for collision candidates. Schema-2 rest-stock snapshots retain
angle/pivot, and clone/target comparison preserve/reconcile grid pose. Existing
zero-angle snapshots retain schema 1.

The combined engine/preview suite passed 41 tests (1.32s), including equivalent cuts
at 90, 37 and -125 degrees, independent clone, snapshot restoration and exact
rendered vertices/normals at non-cardinal angles. Receipt:
`/tmp/carvera-oriented-stock-render-final-tests.log`. The initial 31-test engine
run is retained, as is the wrong-interpreter collection failure (missing Kivy).
Ruff lint/format, diff checks and both import contracts passed. This is source
backend acceptance only. Stock declaration/schema/editor/restart, scene gestures,
portable jobs/recordings, engagement/facing integration, tilted stock and installed
acceptance remain open; no UI control exposes orientation yet.


## Declared stock orientation integration

The stock setup editor now accepts a fixed Z angle in degrees or radians, around
the declared stock center in program coordinates. Its unrotated corner/dimensions
remain the stock-frame inputs; work offsets and toolpath coordinates do not rotate.
The inspector reports that angle and the dimensional drawing labels its stock frame.
Apply/cancel still review local metadata only, with no controller commands.

Declared CAD/schematic stock surfaces and outline normals/vertices share the same
transform as StockVolume. Scene schema 2 requires stock_rotation_deg; legacy schema
1 loads zero orientation without rewriting until save. Restart, unrelated stock
edits, simulation context identity, calculation, matching rest-stock load, portable
jobs, recording start binding and historical scene geometry retain/reconcile angle.
Facing copies transformed XY corners instead of the unrotated rectangle. Engagement
review uses a conservative enclosing program AABB, so possible engagement can still
include empty corners; material removal uses actual transformed cell centers.

Verification receipts: 66 geometry/engine/preview tests passed (96.12s), 48 Scene/
job/recording persistence tests passed (0.19s), 43 recording/archive tests passed
(75.76s), and one explicit rotated binding test passed (0.09s). The editor/context
suite passed 29 tests (273.75s). A later focused angle-field test passed (15.73s),
including radian input, reviewed apply/persistence and no-command assertions.
Logs: `/tmp/carvera-declared-oriented-stock-tests.log`,
`/tmp/carvera-oriented-scene-persistence-tests.log`,
`/tmp/carvera-oriented-custody-tests.log`, `/tmp/carvera-rotation-binding-tests.log`,
`/tmp/carvera-oriented-editor-tests.log`, `/tmp/carvera-stock-rotation-field-tests.log`.
The editor process sample showed frame pumping/sleeps; an earlier filesystem-I/O
inference based only on process state was not established by that sample.

Remaining: direct stock rotation gesture, general tilted stock frames, full job/
recorded-run native roundtrip and installed visual/interaction acceptance. The
original requirements remain open. DESKTOP144's existing frozen-source build has
not been replaced and does not contain these later changes.


Facing footprint source acceptance: the focused workbench test passed (13.54s,
one existing locale warning), copying every rotated corner and preserving top Z
with no machine commands. Receipt: `/tmp/carvera-oriented-facing-tests.log`.
Final Ruff checks, diff checks and both architecture contracts passed.


## Direct stock rotation ring

Rotate stock Z projects an XY ring around the declared stock center, including
current table translation. It shares angular snapping, incremental signed rotation,
context-change rejection and retained-draft protection with vise rotation. Release
opens a stock angle draft; only Apply updates the local geometry and persisted Scene
setup. Origin, size and program work offset remain unchanged. Cancel preserves both
active and saved setup. The pivot follows the declared stock volume, not the bounds
of asymmetric computed rest stock. This edits declarations and sends no commands.

The combined interaction suite passed 40 tests (179.40s, one existing locale warning),
including real projected stock/vise ring dragging, apply/cancel, persistence,
picking/framing and unchanged-source context guards. A later residual-pivot/retained
stock-draft regression passed separately (15.09s). Both processes exited zero.
Receipts: `/tmp/carvera-stock-ring-tests.log` and
`/tmp/carvera-stock-ring-residual-tests.log`. Source render
`/private/tmp/carvera-stock-rotation-ring0002.png` was reviewed. Ruff lint/format,
diff checks and both import contracts passed. Installed/native acceptance, general
tilted frames, calibrated hole snapping and clipping/exploded views remain open.
DESKTOP144's original build is still live and predates these changes.

## Nominal surface measurement planning

Exact picking now retains component/group, source triangle index and vertices,
nominal point before group motion, displayed point and normalized winding normal.
Selections are invalidated after geometry, setup, cutter or reported pose changes.
This reference is rendered geometry, not a measured datum or physical registration.
The earlier surface-reference suite passed 42 tests (179.24s); receipt:
`/tmp/carvera-surface-reference-tests.log`.

Measure surface opens a scrollable review with unit-aware tip diameter, approach
clearance and overtravel fields. Outward side is explicitly selectable by reversing
CAD winding; travel can follow the normal or a selected machine axis. Ball-center
contact offsets along the normalized surface normal even for axis travel on a
sloped surface. Tangent/outward travel and invalid dimensions are rejected.
The approach/contact/search-limit line is projected into the scene using the
selected group's current translation. Setup/geometry/pose changes discard it;
hidden groups and inactive tasks hide it. Actions wrap within narrow workbenches.
No commands, offsets, probe results or datum assignments are generated.

The engine also computes signed local-plane deviation from an explicitly supplied
compensated, registered ball-center measurement. It does not treat a firmware
trigger position as that measurement, or establish compensation/registration.
Adjacent surface/body/holder clearance, machine reach, calibration, transport,
measured result custody, repeated measurements and datum transactions remain open.
This is progress toward requirements 11 and 12, not their completion.

DESKTOP144 completed with exit zero. Independent verification at
2026-10-05T09:15:13Z checked 461 source and 464 staged/built files without
mismatches, matching version and strict signatures. Frozen source is
`4aa016989ab2303f7fac15e945f7b7d7e1a9646f`; receipt:
`/Users/wes/Downloads/carvera-desktop144-20261005/built-verification.json`.
It predates rotation and surface-measurement work and is not installed.

Combined nominal geometry/scene tests passed 53 tests (206.48s, one existing
locale warning); receipt `/tmp/carvera-surface-measurement-tests.log`. After
responsive action-row and overlay-visibility refinements, two focused review tests
passed (18.05s), including unit conversion, rejected tangent approach, projected
line, hidden-component handling and pose-change invalidation, without machine
commands. Receipt `/tmp/carvera-surface-measurement-review-final-tests.log`.
Wide source render `/private/tmp/carvera-surface-measurement-review0001.png` was
reviewed. Ruff, diff checks and both import contracts passed (218 files,
948 dependencies). These are source-render/test gates; installed/native acceptance
remains open.

Final narrow-window review passed two focused tests (15.33s); receipt:
`/tmp/carvera-surface-measurement-narrow-final-tests.log`. The 560 × 700 logical
window renders a single scrolling input column with persistent action buttons;
`/private/tmp/carvera-surface-measurement-narrow0002.png` was reviewed.
The first narrow test failed because resizing rebuilt the scene and correctly
invalidated its reference; its receipt is retained in
`/tmp/carvera-surface-measurement-narrow-tests.log`. The final test checks the valid
projection before resizing and retains rejection after pose/geometry changes.


## Installed picking and nominal approach review

DESKTOP145 (`33de5ab`) was exercised through the native UI: stock top-face picking,
measurement-plan review, local projected approach preview, component framing,
task-change overlay hiding and return to full machine framing. The native receipt
is retained in the DESKTOP145 external evidence folder, linked from the evolution
ledger. Nine operator-store baseline entries were independently read back unchanged.
These nominal CAD points do not establish physical registration or a measured datum.
No inspection feature was retained during this bounded acceptance exercise.

The review exposed a tiny, undifferentiated approach line in full-machine framing.
Later source adds viewport-sized teal approach/retract, amber contact-center and
red search-limit markers, a separate stage legend, and a compact Clear preview
action in the existing responsive action row. The legend survives component
framing/status messages. Clear discards the local plan; task/group hiding removes
all markers, and stale setup/geometry/pose discards the plan and disables Clear.
These source refinements require separate installed/native acceptance.

Preview-stage source validation: 38 scene-interaction/surface-planning tests passed
in 215.79 s; two focused checks passed after the final legend-refresh refinement
(15.16 s). They cover marker placement/size, clear via the actual action, group
hiding, stale pose invalidation, and no-machine-command assertions. Both import
contracts, Ruff lint/format and diff checks passed. Receipts:
`/tmp/carvera-measurement-preview-markers-complete-tests.log`,
`/tmp/carvera-measurement-preview-legend-final-tests.log`, and
`/tmp/carvera-measurement-preview-imports.log`. Initial circle-getter assertions
ran before Kivy's geometry prebuild and failed; those logs remain preserved.
The final filled markers expose position/size directly. Installed/native
acceptance of these visual refinements is still open.
