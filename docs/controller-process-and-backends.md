# Further ergonomics and advanced-machine requirements

This records the latest 25 recommendations under the active implementation goal.
They supplement both `controller-evolution.md` and
`controller-advanced-workflows.md`. Source foundations, exercised desktop
workflows, backend execution and physical qualification remain separate gates.

| # | Requirement | Required completion evidence |
|---|---|---|
| 1 | Machining-aware numerical inputs | Units, fractions, arithmetic, visible interpretation, constraints, sensible increments and draft/application distinction throughout numeric workflows |
| 2 | Contextual explanations | Setting-specific diagrams, prerequisites, examples and accessible contextual help |
| 3 | Scene measurement cursor | Face/center/tool/stock/fixture selection, dimensions and source classification |
| 4 | Visible uncertainty | Estimated boundaries, registration residuals and measurement uncertainty shown without implying acceptance |
| 5 | Editable tools/offsets/measurement tables | Sort/filter/resize/multiselect/keyboard/paste behavior at desktop and large-machine scales |
| 6 | First-run commissioning | Versioned identity/travel/homing/spindle/ATC/probe/telemetry steps and actual readback |
| 7 | Communications health | Telemetry/command/camera latency, reconnect events, observation gaps and native diagnosis |
| 8 | Control ownership | Multiple observers, single command owner, explicit handoff and reconnect arbitration |
| 9 | Firmware-aware macro studio | Named parameters, validation, prerequisites/state effects, preview and supported execution |
| 10 | Managed warmup | Machine-specific sequence, progress, completion receipt and thermal/reference association |
| 11 | Probe direction-error calibration | Reference artifact, repeated measurements, polar plot and validated compensation model |
| 12 | Inspection uncertainty budget | Relevant contributions, measurement provenance and tolerance acceptance policy |
| 13 | Bounded measure/correct/finish | Actual bore measurement, radial/diametral correction distinction, bounded proposal and reinspection |
| 14 | Geometry and wear offsets | Distinct identities/offsets, supported compensation preview, lead-in and backend readback |
| 15 | Scheduled break checks | Operation-boundary checks, limits of length detection, actual sensor results and handling |
| 16 | Qualified sister tools | Per-physical-cutter offsets/assembly/process evidence and reviewed replacement/recovery |
| 17 | Machine dynamics model | Axis/rotary velocity and acceleration, corners, spindle ramp and validated timing |
| 18 | Clearance/stopping explorer | Declared limits, deceleration envelope, structures and qualified information bounds |
| 19 | Adaptive-loop diagnostics | Sample age/interval/filter/command latency/response and segment association |
| 20 | Backend-local adaptive action | Desktop targets/bounds, local qualified execution adapter, time/ack/failure behavior |
| 21 | Process signatures | RPM/load/feed/engagement and optional sensor association, qualified baselines |
| 22 | Thermal drift | Temperature/runtime/reference measurement trends and validated bounded compensation |
| 23 | Spindle-synchronized operations | Actual encoder/synchronization capability, feed/retract semantics and qualified execution |
| 24 | Turning/mill-turn | Stations, tool orientation, turning stock, diameter/radius modes and supported CSS process/backend |
| 25 | Adapter fault sandbox | Actual UI/workflow exercise under delay, stale state, alarms, mismatches and disconnect |

## Quantity input checkpoint

Stock dimensions/origins, preview work offsets, vise placement, cutter library
dimensions, facing parameters, surface queries and threaded-hole process inputs
now accept bounded arithmetic and an explicit unit suffix. Inputs show their
canonical interpretation while retaining the operator's expression. Saved
geometry and generated plans remain canonical millimeters/mm per minute;
changing an input does not issue commands. Compact minus/plus buttons adjust the
draft in canonical units (0.1 mm, 10 mm/min, one degree, 100 RPM or one count)
and refuse bound violations. Bulk coordinate rows accept compact
unit suffixes, or comma-separated expressions with spaces.

Examples: `1/4 in`, `1 1/4 in`, `127/2 mm`, `12 ipm`, `90 deg`.
One suffix applies to the entire expression. Mixed units inside an expression
are rejected. Only numeric arithmetic is allowed; functions, names, powers,
nonfinite values, zero division and excessive nesting are rejected.

The existing profile/planner validators still enforce geometry and process
constraints. This checkpoint does not claim unit-aware inputs in every legacy
dialog, keyboard increments, arbitrary machine travel support, or physical
execution qualification. Those parts of requirement 1 remain open.

Source validation: the first broad pass completed 1,030 tests with 15 skips and
7 warnings (159.74s). After the final adjustment controls and parser restrictions,
77 focused parser/profile/facing/hole/readiness workflows passed (23.10s). Ruff
lint/format and both import architecture contracts passed. Packaging, installed
interaction and physical qualification remain separate gates.

Final committed-source broad validation: 1,034 passed, 15 skipped, 7 warnings
in 174.82s. DESKTOP33 built from `744f69a9c8c3b78dc9603288b46d83522c966c44`;
391 checkout files matched the build manifest, and built/installed strict signature
checks passed. Native interaction acceptance is recorded separately below.

DESKTOP33 native receipt: `/Users/wes/Downloads/carvera-desktop33-20261003/native-receipt.json`.
Connected/Idle, reported T1/TLO 50.480 mm and fresh camera were observed. The
measurement form now displays all four fields and was cancelled without saving.
Native quantity acceptance failed: TextInput graphics refresh removed the child
conversion label and adjustment canvases. Fraction entry itself remained editable.
The next source fix retains these controls in the after canvas and adds a redraw
regression. Operator profile/scene/evidence hashes were unchanged. No machining
commands or measurement receipts were created.

The further 25 recommendations are retained in `controller-connected-workflows.md`;
they supplement all prior requirements.

DESKTOP34 source `9f923bdef0d6eecaaf497154a9b1f26013783c26` passed
1,035 tests (15 skipped, 7 warnings, 193.55s), lint/format and both architecture
contracts. Build/installed signature checks and 391-file manifest comparison
passed. Native feedback displayed `1/4 in = 6.35 mm / 0.25 in`, but adjustment
buttons were misplaced across adjacent fields. This failed installed layout
acceptance is retained in the DESKTOP34 native receipt and screenshot. The next
repair uses a composite editor with independently positioned sibling controls
and checks containment in the actual responsive stock form.

DESKTOP35 checkpoint: source `f575cf99e3b9b4f17da9454af6a9973fef8a9cc3`;
1,035 tests passed, 15 skipped, 7 warnings (173.24s). Thirty-two focused quantity,
profile, facing and hole workflows passed (24.46s). Lint/format and both import
contracts passed; 391 files matched the manifest and built/installed strict
signature verification passed. Native inspection confirmed all nine stock/origin
fields retain contained adjustment controls and feedback. `1/4 in` displayed
6.35 mm / 0.25 in; an actual pointer click incremented to 6.45 mm. Incompatible
RPM input displayed validation. Both stock and measurement drafts were cancelled;
operator profile/scene/evidence hashes remained unchanged. Saved-profile
connection completed Idle with T1/TLO 50.480 mm and fresh telemetry/camera.
Receipt: `/Users/wes/Downloads/carvera-desktop35-20261003/native-receipt.json`.
No machining commands or physical qualification are claimed. Recovery builds
and failed native evidence remain retained.

The complete goal remains open across all four requirement lists. Remaining
quantity work includes legacy fields, keyboard increments, machine-specific
ranges and clearer accepted-unit error copy. Native review also found the Scene
origin editor changes the underlying tab to Program. Further work must integrate
selection/relationships, operation explanations, actual tooling and qualified
backend execution rather than treating this input checkpoint as broad completion.
