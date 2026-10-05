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
