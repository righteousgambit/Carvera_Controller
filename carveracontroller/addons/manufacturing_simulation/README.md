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
cylinder sweep; ball cutters use its cylindrical portion plus the swept sphere
at the ball center. There are no discrete temporal steps along a translation.
This supports any fixed tool axis including indexed rotary cuts. A change in
orientation must be segmented by the producer; one sweep does not approximate
changing orientation. Boundary error remains bounded by voxel size, so reported
volume is a discretized estimate, not measured stock volume.

`compare_target` reports excess stock and missing target cells on identical
grids. `top_surface` supplies a height field and `boundary_boxes` exposes cells
for rendering, with an explicit rendering output budget.

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
original stock bounds for conservative noncutting-body checks; they may flag a
holder in a pocket already cleared by previous segments.

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
