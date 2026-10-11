# Declared kinematic branch review

Machine workbench → Kinematics & machine clearance provides local geometric
review. The panel is collapsed initially and compares one to eight ordered seed
rows in a cancellable worker. Editing targets, seeds or geometry invalidates the
prior result. Selecting a branch highlights it and displays joint values, distance
to each declared limit, nearest equivalent rotary endpoints, and a local tip/axis
Jacobian rank diagnostic. Target positions and tool-tip offset accept the shared
length expressions, including inches; seed rows use mm and degrees as labelled.

Head/head, head/table and table/table examples are illustrative geometries,
not profiles for the connected Carvera. An imported declaration is labelled with
its file hash and canonical profile fingerprint. Import failures preserve the
prior declaration. No profile import, solver result, or branch selection issues
a controller command or asserts firmware TCP support.

The import accepts a UTF-8 JSON file of at most 64 KiB. Schema 1 permits these
fields only: `schema`, optional `name` (at most 120 characters), `tool_chain`,
`work_chain`, optional `tool_base`, `work_base`, and optional
`controller_tcp_supported` (must be false), `collision_bodies`, and
`collision_exclusions`, and `scene_source`. Declare one to nine joints total.
Joint names are unique across both chains, nonempty and at most 32 characters.
Each joint has `name`, `kind` (`linear` or `rotary`), unit `axis`, `minimum`,
`maximum`, and optional `pivot` (defaults to zero). Positive travel is required.
Values must be finite JSON numbers, not strings/booleans, within ±1,000,000.

Bases use `rotation` (nine row-major components of a right-handed orthonormal
matrix) and `translation` (three mm components); omitted bases are identity.
Joint axes and pivots are relative to their preceding chain frame, following the
engine's transform composition. Tool tip is local `(0, 0, -length)` and tool axis
is local positive Z. Each seed row must contain one value per joint, in displayed
spindle-chain then workpiece-chain order, within declared travel.

The solver runs at most 100 iterations per seed. Local convergence requires tip
error ≤0.01 mm and unit-axis difference ≤0.001. The diagnostic projects finite
axis derivatives into the unit-axis tangent plane, normalizes Jacobian columns,
and uses a 1e-3 residual threshold. A low rank identifies dependent local
directions; rank alone does not establish conditioning, global reachability or
a feasible path. Equivalent rotary endpoints do not constitute an unwind path.
Collision/holder clearance, cable travel, measured machine registration,
singularity-aware path planning and backend execution remain separate open gates.

Validation checkpoint: declared-topology known-pose recovery, malformed geometry,
all-seed prevalidation, limits, singularity diagnostics, iteration cancellation,
stale/closed worker results, imported-file provenance, rejected-import preservation,
unit expressions and no controller commands are covered by unit/Kivy integration
regressions. DESKTOP182 received bounded native expansion, unit-input, seeded
solve/selection, imported-profile/rejection and smaller-window review. Follow-up
source fixes remove unsupported chain glyphs and an empty-results gap, label
results by seed, improve initial rotary seeds and give the table/table example a
tilting base with an inner rotary table. Those fixes pass focused regressions
but are not yet in DESKTOP182. Full native/advanced-backend qualification remains
open.


## Declared machine bodies

Optional `collision_bodies` contains at most 32 boxes. Each entry has exactly
`name`, `frame`, `joint_count`, `minimum_mm` and `maximum_mm`. Names must be
unique, nonblank, at most 80 characters, and contain no control characters.
Minimum and maximum are finite three-component vectors in the attachment's local
millimetres; every maximum component must exceed its minimum. `frame` is `world`,
`tool` or `work`. `joint_count` is an integer, never a boolean: zero uses the
chain base, a positive count attaches after that many joints, and world requires
zero. This permits spindle/holder, carriage, intermediate rotary housing,
workholding and stationary enclosure declarations without flattening link motion.
These conservative boxes are declarations, not inferred CAD or measured geometry.

Optional `collision_exclusions` contains at most 496 distinct pairs of declared
body names. Pair order is immaterial. Only explicitly listed pairs are omitted;
intentional mounted contact needs an explicit exclusion. A review with every pair
excluded is refused. Exclusions are retained with saved geometry and results.

The Continuous machine-body clearance section retains separate unapplied body
drafts when changing selection. Apply validates the whole candidate declaration
before replacement; invalid text remains editable. Review/save requires every
retained draft to be applied or discarded. Save declared geometry writes the
same bounded schema atomically and verifies the destination bytes. Loading a
profile remains a local geometry operation.


## Workspace scene capture

Kinematics & machine clearance → Continuous machine-body clearance → Capture
workspace geometry copies the selected C1 scene into a detached declaration.
Choose an explicitly loaded tool profile and capture. All selected CAD groups,
including hidden ones, are included as separate component boxes. Fixture/vise
component overrides, placed movable jaws, selected stickout and every initial
stock in a repeat plan are retained. A body-limit overflow refuses the capture
rather than omitting components. Profiles for other machines require their own
kinematic mapping; the C1 capture refuses them.

The tool-chain origin is the selected tool tip. Entered rows are X, Z, Y machine
coordinates, matching the viewer's negative-travel convention. X moves the
carriage, X/Z move the spindle, and negative Y moves the bed, fixture, vise,
stock and ATC. CAD head registration and selected exposed stickout determine
spindle placement. Initial rows use the preview point twice; this is an explicit
stationary starting declaration, not observed machine telemetry. The branch
target starts at the same preview point with a positive-Z axis. Tool-tip offset
is reset to zero because the captured chain already ends at the tip.

Component bounds are conservative envelopes; voids, open enclosures and curved
surfaces can cause false alarms. Stock is initial bounding stock, even when the
viewer displays removed material. No intentional mounting or cutting-contact
pair is excluded automatically. Tool cutter/shank/holder envelopes come from the
selected simulation assembly; missing holder geometry remains explicitly unknown.
A complete physical machine-clearance claim cannot follow from these bounds.

`scene_source` is optional. Its exact fields are `kind` (must equal
`C1 nominal component envelopes`), `scene_digest` (lowercase SHA256),
`tool_number` (integer), `geometry` (all seven CAD group names with SHA256 geometry
identities), and `notes` (at most 16 strings of at most 512 characters).
The digest binds the original capture's geometry, setup, placement, assembly,
selected tool definition and repeat plan. It identifies the original capture;
subsequent local body edits remain separate declarations. Save/import and saved
clearance reviews retain this source record without reopening the original CAD.

Asset checks run before and after worker preparation. Editing the workspace
while preparation is pending prevents replacement of the prior declaration.
Check capture source compares the original capture's declared inputs against
current selections; it explicitly does not rehash disk assets or qualify local
body edits, live telemetry or physical registration. Capture again to update a
changed scene. Retained body drafts must be resolved before capture replaces
the local declaration. No capture, comparison or file action commands hardware.
