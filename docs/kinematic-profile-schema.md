# Declared kinematic branch review

Machine workbench → Five-axis reachability & branches provides local geometric
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
`controller_tcp_supported` (must be false). Declare one to nine joints total.
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
regressions. Native packaged review of this panel is still open; installed
DESKTOP181 predates this source increment.
