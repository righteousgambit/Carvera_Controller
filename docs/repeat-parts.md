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

Declared playback source checkpoint: Review offers explicit Use declared-WCS
playback and Restore original file playback. Preparation uses canonical mapped
segments off the UI thread, preserves source line/tool/feed/hash attribution and
rejects unsupported modal/rotary/inverse-time programs or connecting gaps.
Cancellation/context changes reject publication. Path and cutter are rebased into
the active scene frame together; selecting another array part preserves their
machine positions. Original file samples remain available for exact local
restoration. Ordinary scene changes restore original playback, new file loads
drop old declarations, and reversible historical scene handling retains both modes.

The real-loader rendered regression verifies G54/G55 endpoints, displayed pointer
position, operation highlighting, original-sample/hash restoration and mismatched
source rejection, without controller execution. Combined affected checks passed
51 tests (35.15 s); strengthened pointer/highlight check passed (14.60 s); final
cancellation/engine/rendered checks passed three tests (14.71 s). Existing SSL
warning remains. Receipts: /tmp/carvera-repeat-playback-final-tests.log,
/tmp/carvera-repeat-playback-pointer-tests.log and
/tmp/carvera-repeat-playback-cancel-final-tests.log. Ruff and diff checks passed.
All 18 post-incident operator-store hashes matched; no operator repeat plan exists:
/tmp/carvera-repeat-playback-operator-readback.json.

DESKTOP163 remains installed; this playback checkpoint is not packaged/native
qualified. GPU/path mesh publication remains synchronous and comprehensive
responsiveness is open. Native playback/calculation, persisted multi-stock result
exchange, measured offset transactions and physical workflows remain open.


Source now retains actual per-part occupancy and provides .cvstocks result exchange
under Results & files. Bundles match the complete declared array, selected machine
profile, program hash, tooling/workholding and verified CAD bytes; changing the
active part alone is a display choice. File size, stock count, occupancy, placement,
resolution, volumes and shared voxel/mesh budgets are checked before publication.
Worker preparation and asset hashing keep file/geometry work off the UI thread;
context/cancellation guards preserve the previous displayed result. Conservative
collision candidates persist, while detailed contact geometry does not and is
explicitly labeled unavailable. These results are local approximate stock models,
not physical inspection or qualified clearance. Layout/review/results are distinct
compact views. Native calculation/file-picker/save/load/layout acceptance remains
open; DESKTOP164 predates these changes. Verification is in the evolution ledger.

## Revision-bound persistence and frame review checkpoint, 2026-10-06 UTC

The selected-part review now shows declared machine-space datum, stock lower/upper
bounds and nearest declared stock separation. This distance concerns nominal stocks
only; it is not a tool/fixture clearance or measured-offset acceptance check. The
review updates when the selected part or machine changes. Its active page is visibly
highlighted, and the quantity-field row reserves its full height rather than
intersecting the preceding action.

Plan reads/writes run on a background worker. File actions are disabled while that
operation runs, while page navigation remains available. Save captures an immutable
plan and original machine owner; changes to the current draft do not redirect the
write or replace the new draft. Restore applies only when its captured machine and
draft generation still match. Closed views reject completion callbacks; worker
launch/read/write failures release controls and produce an operation receipt.

A saved plan must match the reviewed canonical plan digest before replacement.
First saves expect an absent plan; existing plans must be restored/reviewed before
replacement. A cooperating-writer exclusive lock protects the read/compare/write
transaction and preserves other machines' plans. Invalid originals, an existing
lock owned elsewhere and atomic-write failures remain intact. A failed write cleans
its own staging and lock. This does not promise completion of an in-flight daemon
worker after process termination or power-loss durability.

The declared-plan, stock, frame-review and serialization boundaries now have
explicit contracts. Coordinates reject booleans, strings, nonfinite/overflowing
numbers and values outside the declared 1000 mm model bound. JSON fields are
validated and reconstructed before retention. Geometry factories and core box
operations have concrete types, preserving the same solid/wireframe geometry.

Verification: 80 repeat-plan/simulation/archive/playback/geometry/UI regressions
passed in 42.91 seconds, with the existing SSL warning. Covers exact frames/bounds,
negative pitch/touching faces, stale writer rejection, atomic failure, long blocked
I/O with live navigation, duplicate-save exclusion, changed-context restore rejection,
worker launch failure, 360/760 dp nested-control layout, full-array simulation,
archived rest stocks and frame-aware playback. A 360 dp source render was reviewed.
Focused repeat-plan strict typing, repository lint/format (503 files), diff and both
architecture contracts pass. Full local strict remains open at 906 errors in
54 files (88 checked), down from 980/55; package baseline remains 148/19. Local
imported-addon scope differs from hosted scope. No quality rules were weakened.

Receipts: /private/tmp/carvera-repeat-layout-final-tests-20261006.log,
/private/tmp/carvera-repeat-full-strict-20261006.log and
/private/tmp/carvera-repeat-frame-source-20261006.png. These source changes postdate
installed DESKTOP186. Installed workflow, qualified measured offsets, probing,
repeat execution/inspection and advanced-machine backend acceptance remain open.
No machine offsets or execution commands were dispatched by these reviews.


### Restore and individual part editing (2026-10-06 UTC)

Restoring a regular row-major array now fills its layout fields from the stored
geometry, including signed spacing and first WCS. Unused spacing axes default to
60 mm because a single row/column does not encode that pitch. Arithmetic matching
uses 1e-9 mm only to accommodate floating-point subtraction; stored positions are
not rounded or replaced and this is not a physical tolerance.

Custom names, sizes or frame tables remain custom. Their regular-array fields are
locked and Build/scene-seeding reject replacement until the operator explicitly
chooses Start a new array draft. Review includes a collapsible selected-part editor
for name, declared WCS, machine datum, local stock origin and size. Apply validates
the entire plan, preserving all other instances; duplicate names/frames and stock
overlap leave the prior plan intact. Discard restores the reviewed values.
Selection retains unapplied part drafts in the current plan session. Changing
machine context clears and disables stale editor inputs. Changes remain local
declarations; Save retains them for that machine without applying controller offsets.

The expanded editor and quantity controls reflow at 360/760 dp. A narrow source
render was visually checked. Focused engine typing, lint/format and both architecture
contracts pass. Full local strict remains 906 errors/54 files (88 checked), package
baseline 148/19 (185 checked); installed DESKTOP186 and physical qualification are
separate, open gates. Test and render receipts are under /private/tmp with the
carvera-repeat-editor prefix for 20261006.


### Retained drafts and atomic multi-part edits (2026-10-06 UTC)

Each declared part retains its unapplied text draft while selecting another part.
The editor shows the pending count and whether the selected part is reviewed or
pending. Apply/discard actions work on one part or all drafts. Apply all constructs
and validates one candidate plan, so frame/name swaps can succeed together while
individual duplicate/overlap changes cannot partially publish. An invalid candidate
retains the original plan, rendered results and all text drafts for correction.
Applying one part carries the other pending drafts into the new reviewed plan.

Array fields are locked while edits are pending; programmatic layout changes are
reverted to the reviewed layout. Save, Restore, scene-seeding and new-array actions
require applying or discarding drafts first. Pending drafts are in-memory, bounded
by the six declared instances and tied to the exact plan/machine context; replacing
the plan or switching machines clears them. They are not crash-persistent. No
machine offsets are read or applied by draft editing. The part name has its own
full-width row, and the pending note/actions were visually checked at 360 dp.

Validation: 87 repeat/simulation/archive/playback/geometry/UI tests pass in 34.22 s,
including two-frame swaps, invalid all-or-nothing edits, navigation retention,
single-edit migration, explicit discard, guarded save/restore/layout replacement,
machine isolation and save readback. Existing 360/760 dp nested-layout checks pass;
repository lint/format/diff and both architecture contracts pass. Local package and
full strict diagnostics remain 148 errors/19 files and 906/54 respectively. The
previous hosted checkpoint (69d6d6b, run 37393595616) passed lint/format/package
baseline/architecture but failed strict with 365 errors/34 files; hosted tests
were skipped. These source edits postdate installed DESKTOP186.


### Common persistence controls and status (2026-10-06 UTC)

Save/Restore now sit beside the repeat-plan page choices and remain attached in
Layout, Review and Results. A wrapping status line distinguishes an unbuilt draft,
a reviewed plan not compared to disk, reviewed changes not saved, and a plan that
matches the last successful save/read. This describes retained revision evidence,
not a continuously observed file. Concurrent external writers remain protected by
canonical revision comparison; a failed save does not advance the known revision
or replace the local plan or external file. Explicit Restore reads the new revision.

Pending part edits disable Save/Restore, with their count and apply/discard instruction
beside the controls. File work keeps navigation available and displays its operation
in the shared status; failure and changed-context restore rejection remain visible.
No machine offsets are written by these actions. Narrow/wide source layout checks
and an inspected 360 dp render cover the toolbar, wrapping status and nested editor.
All 88 repeat/simulation/archive/playback/geometry/UI tests pass in 31.69 s, including
concurrent-save refusal and recovery through explicit restore. Lint/format/diff and
both architecture contracts pass; local strict/package diagnostics remain 906/54
and 148/19. These source controls postdate frozen DESKTOP187.

The retained DESKTOP187 native receipt is at
/private/tmp/carvera-desktop187-20261006/native-repeat-review.json. It proves native
array building, two draft retention, bulk apply and explicit discard with a clean
restart, not native save/restore or physical machining. All 496 installed source files
and signatures were verified; nine existing operator JSON files were unchanged.
