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

Preview selected stock locally changes the single viewer stock and declared
preview origin, enters Preview and marks physical alignment unconfirmed.
It never writes machine offsets or remaps the loaded program's WCS. Only the
selected instance is currently rendered. Playback, non-idle machine state,
profile loading and historical-scene restoration prevent preview changes.

The complete multiple-WCS requirement remains open: render all instances,
resolve program modal WCS against the selected frame table, capture registered
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
