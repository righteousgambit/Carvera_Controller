# Assembly and machining intelligence requirements

These 25 requirements supplement all eleven earlier ledgers (300 total listed
requirements). They preserve the requested full implementation scope. Source,
native interaction, backend execution and physical qualification remain separate.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Unified working context | Part/setup/operation/physical assembly/WCS selection updates linked controls and scene consistently |
| 2 | Physical relationship drag/drop | Cutter-holder-pocket and stock-vise-plate previews, dimensional resolution and reversible application |
| 3 | Dimensioned assembly drawing | Linked cutter/assembly dimensions, inserted portion, actual holder/gauge data, unknown fields, responsive native inspection |
| 4 | Geometry change-impact view | Affected operations/clearance regions, exact old/new revisions and simulation invalidation |
| 5 | Interactive toolpath legend | Motion/tool isolation and model region selection linked to operation and source |
| 6 | Time-scaled operation timeline | Cutting/air/change/wait durations with estimated versus observed classification |
| 7 | Job comparison workspace | Synchronized revision views and stock/tool/path/process/setup changes |
| 8 | Feature quick controls | Contextual measure/inspect/frame/operation/edit actions and shared selection |
| 9 | Live dimensional annotations | Persistent selected dimensions with CAD/entered/measured source and frame |
| 10 | First-piece workspace | Operation-linked required dimensions, actual results and resulting finish/correction decisions |
| 11 | Remaining allowance map | Target-model comparison, residual material and smaller-tool needs at declared resolution |
| 12 | Tool accessibility analysis | Qualified cutter/holder reach, interference regions and minimum stickout |
| 13 | Reviewed air-cut shortening | Proven removed-material regions, compared original/proposed links and clearance assumptions |
| 14 | Thin-wall/support tracking | Geometry/support transitions and reviewed sequence or support alternatives |
| 15 | Exit-edge/burr-risk overlay | Geometric exit indicators, direction/stock/chamfer comparison and inspected outcome validation |
| 16 | Measured spindle response | Raw unloaded/ramp/engagement/recovery data, timing/filter model and bounded applicability |
| 17 | Multi-signal engagement estimate | Geometry/RPM/feed/current inputs, uncertainty, alternative explanations and delay |
| 18 | Process-envelope explorer | Feed/RPM/depth/width/stickout scenarios, chip load/removal/demand/clearance and measured outcomes |
| 19 | Measured finish prediction | Scallop/marks/direction model versus actual finish and reviewed process alternatives |
| 20 | Change-driven inspection sampling | Tool/reseating/material/process changes linked to affected dimensions and explained sampling |
| 21 | Executable backend contract | Actual adapter discovery, observations/actions/semantics, transport and capability-specific exercise |
| 22 | Planner/servo comparison | Time-aligned intended path/joint command/feedback/following error and data gaps |
| 23 | Orientation sensitivity explorer | Compared small orientation changes, clearance/travel/demand/singularity consequences and resulting path |
| 24 | Synchronized-cycle debugger | Actual encoder phase/axis/feed/reversal/acquisition state, supported cycle and fault exercise |
| 25 | Machine-side adaptive controller | Qualified backend-local loop, desktop targets/bounds/recipes, limiting factors and diagnostic evidence |

## Dimensioned drawing source checkpoint

The shared cutter inspector now switches between orbitable 3D geometry and a
dimensioned nominal schematic. Physical assemblies open that inspector using
their own stickout and holder reference. The schematic uses the shared procedural
cutter profile, shows overall/cutting/stickout/inserted-cutter spans and the collet
face, and leaves undeclared dimensions unknown. Inserted length is derived from
declared overall length minus declared stickout; it is not a measured insertion.
Holder gauge length is not inferred. Manufacturer CAD remains available in the
3D mode. Actual holder dimensions, editable drawing dimensions, calibrated gauge
length, native physical-assembly inspection and complete requirement 3 remain open.

## Rendering recovery

DESKTOP58 passed 1,138 source tests but failed native drawing-mode switching with
`Too much StencilPop (stack underflow)`. That runtime gate remains failed for that
artifact. The drawing now owns a separate Canvas and preserves StencilView's
clipping instructions. Tests retain the clipping instructions across repeated
redraws and exercise the drawing in the initialized application event loop.
This failure shows why source tests alone cannot close installed UI acceptance.

## Geometry consequences source checkpoint

The residual simulation now carries a canonical content-bound input context,
retains previous/current values for review and links tool changes to dependent
operations. Changes to stock/frame/workholding/program conservatively affect all
operations. Exact converted CAD byte identity detects same-path replacements and
requires explicit reload/recomputation. Residual snapshots now require schema 2
context matching. See `geometry-change-impact.md` for scope and limitations.
Requirement 4 remains partial: spatial consequence regions, prospective change
review, related measurements/recipes and full native acceptance are still open.
