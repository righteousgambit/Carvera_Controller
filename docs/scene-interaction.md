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

Remaining scope includes cutter surface picking, rotation handles, calibrated
fixture-hole snapping, clipping/exploded views and native interaction acceptance.

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
