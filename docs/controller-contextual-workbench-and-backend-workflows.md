# Contextual workbench and advanced backend workflows

These 25 requirements retain the latest user-approved implementation scope.
All complete workflows are OPEN. They supplement earlier ledgers rather than
replace them. Source engines, native interaction, backend execution and physical
qualification require separate evidence. This ledger does not authorize physical
execution, machine configuration writes or automatic adaptation.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Selection-driven workbench | Object selection routes to the linked inspector and preserves context. |
| 2 | Named resizable layouts | Pane sizing, scene/camera framing and workbench section round trip in named presets. |
| 3 | Dimensional inputs | Shared unit/expression input, keyboard stepping and validation work throughout the native workbench. |
| 4 | Program revision differences | Tools, depths, frames, extents and operations compare between captured revisions before loading. |
| 5 | Coordinated selection trail | Back/forward restores selected operation, assembly, issue and source context with view framing. |
| 6 | Progressive expert detail | Compact summaries, everyday controls and expert disclosure preserve focus and responsiveness. |
| 7 | Coordinate-chain inspector | Machine, fixture, vise, stock, WCS and tip transforms expose values and measurement provenance. |
| 8 | Camera setup verification | Reference images, reviewed checks and calibration mismatch are retained and exercised. |
| 9 | Viewport tool assembly editing | Cutter, holder, collet and extension dimensions distinguish vendor geometry from measured stickout. |
| 10 | Tool choice comparison | Candidate reach, features, holder clearance, residual stock and changes are explained. |
| 11 | Physical magazine semantics | Fixed/random pockets, oversized exclusions, reserved pockets and sister tools reconcile through a supported backend. |
| 12 | Two-bank transaction | Remove/install/reconcile/measure/continue completes with qualified six-pocket hardware. |
| 13 | Physical cutter condition | Usage, material, measurements, replacements and inspections bind to individual cutter identities. |
| 14 | Geometry-launched probing | Selected features produce reviewed approach/contact/retract plans and retained measured results. |
| 15 | Measurement correction proposals | Feature errors, predicted effects, approval and backend readback remain distinct. |
| 16 | Synchronized run replay | Path, RPM, feeds, overrides, alarms and camera retain timing uncertainty and queued/executed identity. |
| 17 | Adaptive experiment workspace | Signal noise, response, delay and override experiments are measured per assembly and material. |
| 18 | Operation adaptation policies | Operation-specific objectives, permitted responses, bounds and stale-state behavior are exercised. |
| 19 | Backend-owned fast loop | Qualified local sampling/actuation exposes timing, limits, acknowledgments and desktop handoff. |
| 20 | Dynamics cycle analysis | Acceleration, short moves, rotary motion, changes and stops compare with observed timings. |
| 21 | Rotary setup assistant | Chuck/jaws/centerline/tailstock, indexed/continuous motion, travel and unwind plans are registered. |
| 22 | Joint and tip debugger | Joint solutions, tip motion, travel, topology and supported TCP state are inspectable. |
| 23 | Orientation quality map | Joint margins, singularities, holder clearance and orientation changes associate with candidate paths. |
| 24 | Auxiliary timing/interlocks | Named coolant, air, extraction, clamps, doors and pallets distinguish observed states and immediate/synchronized actions. |
| 25 | Commissioning/capability workspace | Configured, observed and exercised hardware, commands, geometry and telemetry remain distinct. |


## Task-focused Machine workbench checkpoint

Machine workbench content is now organized into Connect, Health, Kinematics,
Capabilities, Captures and Preferences. A single retained task is mounted in the
scroll host; hidden tasks keep their model/drafts while releasing keyboard and
menu focus. Measured caption widths determine tabs versus a compact dropdown,
keeping the navigation on one 34-pixel row. The task summary explains the active
workflow, with separate reading positions and stale restore rejection during
rapid navigation. Disposal cancels pending restoration and releases focus.

The workbench Connection action routes to Connect before revealing its controls.
All six tasks are discoverable in the command palette with terms for connection,
UI timing, five-axis joints, capability evidence and historical HAL comparison.
These are navigation actions, not controller commands. Existing connection,
maintenance and configuration guards remain in their original command paths.

Full-app mounted checks exercise 360/650/1100-pixel layouts, focus release,
retained advanced state, scroll restoration, rapid switching, palette routes,
connection reveal and absence of execution commands. The related connection,
palette and capability regression passes 15 checks, with one environment SSL
warning. The final render pass passes all three widths; actual Connect/Health
renders were inspected. Full Ruff/format and both architecture contracts pass;
three changed UI modules pass focused package-baseline typing. Native installed
interaction, packaging of this source and the broader 350-requirement overhaul
remain OPEN. This checkpoint does not close camera registration, synchronized
capture or advanced backend/physical qualification.

Final full-app navigation/kinematic review/command regression: **66 passed**, one
known environment SSL warning, 51.49 seconds. The earlier failed navigation test
and logs remain retained; the scroll-restoration race was corrected and the final
run uses the corrected source. The installed application has not been replaced
by this source checkpoint.


## Setup task workbench and cross-platform navigation correction

Setup now separates Tools, Datum, Surface, Holes and Repeat using the retained
responsive task deck. Existing controls and command guards are preserved; surface,
hole and repeat planners keep their local drafts and expanded state. Cutter
comparison routes to Tools. Restoring a reviewed facing or hole recipe selects
Surface or Holes before expanding the relevant form. All five tasks are searchable
in the action palette; switching does not upload or execute a program.

Hosted run 37465237309 for `e8cbb6d9034cd816196d504ff921f99b3eecd9a7`
failed three newly added navigation tests, while 2,743 tests passed and 17 skipped.
The failed raw log is retained. Two failures exposed scroll restoration occurring
before Linux layouts settled; the third used a Mac-specific screenshot path.
Restore now waits for pending child layouts/textures, resets residual scroll
motion and rejects superseded generation callbacks. Test artifacts use the
portable pytest temporary directory. Explicit result reveals cancel saved-position
restoration; long cutter lists and planning disclosure/recipe restores retain their
intended target. A retained-passport test explicitly selects Overview to avoid
assuming state left by prior recipe tests. No product state reset was introduced.

The corrected combined full-app regression passes **53 checks**, one known local
SSL warning, 44.56 seconds. It covers Machine and Setup task navigation, preserved
drafts, focus release, direct palette routes, long-magazine reveal, surface/hole
recipe restoration, repeat plans, connection navigation and no unexpected machine
commands. Eight changed UI modules pass focused package-baseline typing; full
Ruff/format and both architecture contracts pass. Source Datum/Tools renders were
inspected at narrow/wide widths. Installed interaction and exact-source hosted CI
remain independent OPEN gates. Camera registration, synchronized capture and all
remaining requirements in the full 350-item program remain OPEN and active.

The existing desktop workspace, kinematic review and command regression also
passes **63 checks**, one environment warning, 45.27 seconds, on this source.


## Task-aware Back/Forward history checkpoint

The shared bounded session history now captures the active task and reading
position for Program, Setup, Machine and Spindle workbenches. Task changes use
before/after hooks so departure framing/reading position is retained before the
new task arrives. Task name is part of history identity; changing only a reading
position updates the current entry rather than manufacturing a new visit. History
labels identify the task. Existing program/setup-context checks still reject a
revisit after identity changes without silently rebinding the old entry.

Task names and finite normalized reading positions validate before changing page,
selection, pose or history index. Restoration suppresses arrival callbacks, restores
the specific task, and waits for pending layout/texture work before applying its
reading position and resetting scroll motion. A later selection, history reset,
rapid traversal or workspace disposal invalidates pending delivery. Departure
while a restore is pending preserves its target position rather than overwriting
it with a transient layout value. A closed navigation object rejects traversal.
Restoring a non-Operations Program task invalidates an earlier inspect-line reveal,
so delayed work cannot take the operator from Simulation back to Operations.

The initial combined task/selection regression passes 36 checks. Seven final
focused checks additionally cover Setup/Machine/Spindle Back/Forward loops without
new history entries, invalid task/boolean/nonfinite/out-of-range positions,
reading-position and stale-restore behavior, and a loaded program returning to
Simulation/View & playback with its inspected line retained. Four changed UI
modules pass focused package-baseline typing; full Ruff/format and architecture
contracts pass. These are source/full-app fixture receipts; installed interaction,
exact-source hosted CI and all remaining 350-item acceptance requirements remain
OPEN. Current scratch capacity remains below the retained 3.5 GiB package reserve;
no new build, installed-app replacement or machine actuation was performed.

Final task/history/Program/Setup/Machine/whole-workspace regression passes
**85 checks**, one known local SSL warning, 101.11 seconds. The hosted quality
hooks for prior source `0e30f52e9e6d292d5ce5f85673deae09bf147bd1` pass;
run 37468341272 tests remain in progress and are not claimed green. Latest task
history source requires its own hosted receipt. The full objective remains active.

## Full-pane compact profile browser checkpoint

Embedded machine/tool libraries below 760 dp now switch between a full-pane saved
profile browser and the retained editor. Selecting a saved profile or creating a
new one returns to editing; Back to editor restores the current draft. Search,
filters, sorting and 30-row paging remain available. Resizing to a wide layout
restores the side-by-side browser/editor without discarding drafts. Hidden editor
inputs release keyboard focus. The compact New action leaves space for search.

The profile/browser/draft/chrome/workspace regression passes 14 checks in 47.21
seconds. Two additional final checks at 360 and 650 dp cover wide/narrow resizing,
selection, paging through 35 cutters, unchanged stored bytes and no controller
commands (18.51 seconds). Source renders were inspected at both widths. The
illustrated-editor fixture explicitly fixes popup geometry so native backing-scale
changes cannot silently turn its intended compact check into a wide layout.
Ruff, formatting, focused module typing and architecture contracts pass.
Installed interaction and exact-source hosted CI remain OPEN. This checkpoint
advances the broader overhaul without closing the remaining controller requirements.
