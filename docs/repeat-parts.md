# Repeat parts and declared work coordinate systems

The Setup workbench contains a collapsible Repeat parts & work offsets card.
It builds one to six unrotated rectangular stock instances in a planar array,
assigns distinct declared G54–G59 frames, and displays machine XYZ at each
part datum. Stock lower corners are relative to their individual datum.
Column/row pitch accepts negative spacing; overlapping stock interiors are
rejected while touching faces remain legal. This is a stock-overlap check,
not a fixture, travel, tool or collision acceptance check.

Build or restore a plan for the selected saved machine profile. Plans are
stored independently per profile in ~/.carvera/repeat-parts.json, with bounded
schema validation, duplicate-key rejection and atomic replacement. Editing
array inputs invalidates the built plan until it is rebuilt or restored.
Save and preview reject plans belonging to another machine profile.

Preview array with selected part active changes the active viewer stock and declared
preview origin, enters Preview and marks physical alignment unconfirmed.
It never writes machine offsets or remaps the loaded program's WCS. All instances
are rendered: the selected stock remains the editable/simulated stock and the
other nominal stocks have blue translucent faces and volume edges. They move
with the table, participate in whole-view framing and follow stock visibility.
Other instances are display declarations, excluded from active-stock picking,
handles, clearance and subtraction. Hiding other instances preserves the active
stock and its computed rest stock. Editing array inputs, loading a machine profile
or declaring an ordinary stock clears the array. Historical-scene viewing clears
it temporarily, and returning restores its declaration and selected instance. Playback, non-idle machine state,
profile loading and historical-scene restoration prevent preview changes.

The complete multiple-WCS requirement remains open: resolve program modal WCS against the selected frame table, capture registered
probe results, review offset transactions and machine readback, and execute
repeated parts with per-part inspection records. Backend capability and actual
machine registration must be verified before any physical workflow.

Initial rendered construction caught a Kivy size-property naming collision;
failed log is retained at /tmp/carvera-repeat-part-tests.log. Corrected unit
and rendered workflow checks passed 16 tests in 14.62 seconds, with one existing
SSL warning. Receipt: /tmp/carvera-repeat-part-corrected-tests.log.
New code is not installed; DESKTOP161 remains the installed checkpoint.

Final workspace regression: 21 passed in 29.47 seconds, one existing SSL
warning. Includes historical-context rejection, changed-input invalidation,
program-task navigation, palette lifecycle and default CAD preparation.
Receipt: /tmp/carvera-repeat-part-workspace-regressions.log. All 18 operator
store entries matched the post-incident baseline; no operator repeat-part file
was created. The failed first run remained alive after its pytest error summary
and was terminated after verifying its exact PID/command.

Full-array rendering source checkpoint: exact machine-space solids/edges for all
non-active instances, active-frame GPU conversion, shared table motion and stock
visibility passed the unit/rendered workflow checks (22 passed, 15.84 s). Historical
restoration initially compared derived edge-buffer identities as retained scene
state; failed evidence is preserved. The fix retains immutable plan/index state
and rebuilds display buffers. Corrected array/history workflows passed three tests
in 32.22 s; the other 49 affected scene/profile/default-preparation checks passed
in the retained combined run. The final declared-alignment guard passed the
rendered array check (one passed, 22.12 s). Existing SSL warning remains. Receipts:
/tmp/carvera-repeat-array-tests.log,
/tmp/carvera-repeat-array-scene-regressions.log,
/tmp/carvera-repeat-array-historical-corrected-tests.log and
/tmp/carvera-repeat-array-final-rendered-tests.log.
Packaging/native full-array review, program WCS-aware simulation and physical
registration remain open. No controller commands or operator plan writes occurred.

DESKTOP162 installs the planner and visualization from source 56923aa. Native
build/preview selected Part 1 and Part 6 in a six-instance array and hid the
other instances successfully. Restart returned to the saved actual-scene draft
and Live viewing; no operator repeat plan was saved. Package verification covered
479 files and strict signatures, and all 18 post-incident operator stores matched.
Receipt: /private/tmp/carvera-desktop162-20261005/native-repeat-array-acceptance.json.
Planner compactness/result placement, native persistence/archive restoration,
program WCS-aware simulation and physical acceptance remain open.

Declared-WCS simulation source checkpoint: the parser preserves machine position
when switching between explicitly declared G54–G59 offsets. The worker applies the
actual ordered machine-space path to every stock rather than duplicating paths or
filtering engagement by frame name. Each part retains separate remaining-stock
geometry and removal/collision results. Shared voxel/face budgets bound the array;
unsupported modal/rotary commands reject publication, and unknown initial motion
remains unresolved. Changing the active part retains current results. Changed
inputs, cancellation, disposal and concurrent calculations prevent stale publication.

The planner separates Array layout from Review & simulate, uses compact responsive
grids and content-sized summaries, and reports per-part collision candidates and
excluded unresolved lines. Rendered tests exercise subtraction, active-part changes,
cancelled/stale worker results and reversible historical scene handling without
controller execution. Combined checks passed 79 tests (30.65 s); the subsequent
collision/excluded-line display check passed (16.12 s). Existing SSL warning remains.
Receipts: /tmp/carvera-repeat-wcs-final-corrected-tests.log and
/tmp/carvera-repeat-wcs-result-review-tests.log. Initial expectation failures are
retained; operation bounds correctly remain unknown for an unresolved initial approach.
All 18 post-incident operator-store hashes matched; no operator repeat plan was
written. Receipt: /tmp/carvera-repeat-wcs-operator-readback.json.

Package/native calculation acceptance, persisted multi-stock results, frame-aware
toolpath playback, measured offsets and physical execution remain open. This is
translation-only local simulation, not a qualified multi-part machine workflow.
