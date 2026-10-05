# Direct scene interaction

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
