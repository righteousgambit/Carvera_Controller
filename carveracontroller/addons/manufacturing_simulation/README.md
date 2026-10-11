# Machining geometry engine

This package has no Kivy imports, controller connection, or machine commands.
All geometry uses millimetres, with rotary joint coordinates in degrees.

## Stock evolution

`StockVolume(bounds, resolution_mm)` divides the requested stock envelope into
regular cells, fitting the final cells to the requested dimensions. Occupancy is
one byte per cell and allocation is capped at eight million cells. The API
refuses a finer-than-budget grid rather than silently lowering resolution.

`subtract(SweptTool(start, end, tool, axis))` tests each potentially affected cell
center against the continuous translating cutter. Flat cutters use an analytic
cylinder sweep; ball cutters use the lower swept hemisphere plus the upper
cutting cylinder. Sphere distance and axial caps share the same motion parameter;
material above finite flute length is retained, including diagonal sweeps. There are no discrete temporal steps along a translation.
This supports any fixed tool axis including indexed rotary cuts. A change in
orientation must be segmented by the producer; one sweep does not approximate
changing orientation. Boundary error remains bounded by voxel size, so reported
volume is a discretized estimate, not measured stock volume.

`compare_target` reports excess stock and missing target cells on identical
grids. `top_surface` supplies a height field. `boundary_boxes` and
`occupied_boxes` expose conservative program-axis envelopes with explicit budgets.
The rest-stock display uses exact transformed boundary vertices, not these envelopes.

`StockVolume(bounds, resolution_mm, rotation_deg=angle, pivot=Vec3(...))`
keeps its regular grid in the declared unrotated frame and rotates it around
program Z about an explicit program-coordinate pivot (default: stock center).
`grid_bounds` describe that local grid; `bounds` are its enclosing program AABB.
Cell centers, sweep candidate ranges and normals use the corresponding transform.
This preserves requested stock volume instead of filling the larger enclosing box.
Schema-2 snapshots retain grid bounds, angle and pivot; zero-angle snapshots remain
schema 1. Clone and target comparison preserve/check pose as well as occupancy.
Tilted stock frames and changing stock orientation are not represented by this Z
angle. Desktop declaration/editor/job integration of this parameter remains open.

### Imported initial stock geometry

`StockMeshInput.load(path, units="mm" | "inch")` reads bounded STL bytes with
explicit units and retains source SHA-256 and source-local coordinates. It checks
manifold topology without tolerance welding. `StockSolid.validate(input)` adds
exact rational triangle-intersection and shell-containment checks. Crossing or
improperly touching faces and inconsistent cavity orientation are refused.
Separate closed pieces and correctly oriented nested cavities are supported;
either overall winding direction is accepted. Analytic enclosed material volume
is separate from the discretized voxel estimate.

`solid.voxelize(resolution_mm, translation_mm=(...), rotation_deg=..., pivot=...)`
classifies actual cell centers against material intervals, including closed
boundaries. Concavities, gaps and cavities start empty. Translation maps the
source-local mesh into the unrotated program grid; rotation uses the existing
program-Z pivot convention. Validation and sampling have explicit work budgets
and cancellation, and publish a fresh volume only after completion. Exceeding a
budget fails rather than substituting the mesh's bounding box. Very fine grids
at placements that lose floating-point coordinate precision are refused.

The returned `ImportedStock` retains detached source/placement identity and can
clone its mutable stock independently. Imported volumes measure removed material
from their initial occupied count, so source cavities are not counted as cuts.
Schema-3 snapshots preserve that count and pose and validate it against restored
occupancy. Legacy schema-1/2 box stock remains readable and writable.

This is an engine API. Desktop import, mesh preview, context/portable exchange
identity integration and installed workflow acceptance remain open. Nominal STL
geometry and source digests do not establish measured stock registration or
physical machining qualification. Center sampling can miss features smaller than
the voxel size; it does not prove continuous physical clearance.

## Clearance

`CollisionScene.check_sweep` encloses each translating cutter, shank, and holder
in a conservative box for the entire segment. Obstacle boxes, rapid contact
with stock, noncutting-body contact with stock, and cutting outside the permitted
region are reported by component. Bounding envelopes deliberately produce
false positives at their corners. An empty hit list has `unknown` status unless
registration and geometry completeness have both been explicitly established.
Even a clear conservative envelope has `qualified=False`: this does not qualify
physical setup registration, unseen clamps, servo following, or execution.

`simulate` ties ordered segments, resolved physical tool geometry, stock
subtraction, candidate collisions, progress, and cancellation together. It never
uses unknown tool geometry or makes machine movements. Collision checks use
the current occupied cells for rapid-cutter and noncutting-body checks before
each subtraction. Without a supplied residual volume, standalone scene checks
fall back to initial stock bounds. Cleared voxel cells remain a discretized
material estimate; they do not establish physical clearance.

## Machine transforms

`MachineKinematics` declares separate ordered tool and workpiece chains. Each
joint declares a unit axis, limits, and pivot in its parent's coordinates.
Forward composition yields spindle/world, table/world, relative tool/workpiece,
actual tool-tip coordinates, and tool axis. These cover table/table, head/table,
and head/head rotary assemblies. Declared travel violations are returned;
unknown or missing joint states fail. Rigid transforms reject reflected or
non-orthonormal rotations. Tool and holder mesh vertices can be transformed by
the returned pose.

`controller_tcp_supported` is a declared machine-controller capability. Forward
visual geometry does not implement firmware TCP compensation, rotary singularity avoidance, or a physical 5-axis postprocessor.

`inverse_kinematics` provides bounded damped numerical tool-tip and axis solving
for declared chains, with explicit convergence, residual errors and travel-limit
enforcement. It is local to the supplied seed and is geometry for preview and
postprocessor development, not machine-side TCP. `unwind_rotary` chooses the
closest equivalent angle within declared limits, without authorizing or adding
a physical clearance/unwind move.

Stock state can be cloned or saved in a JSON-safe, compressed snapshot. Reload
checks units, schema, integrity digest, exact grid size and bounded decompression;
it supports carrying actual simulated residual stock between operations/setups.
