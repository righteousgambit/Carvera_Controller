# Choose saved cutter geometry from a simulation review

Simulation lists every cutter used by the current scope: the whole program or
the selected operation. Each numbered review shows its assigned name and nominal
diameter when cutting dimensions are ready, or explains the geometry that needs
attention. Ready cutters remain reviewable so another saved cutter can be chosen
after evaluating the setup. Changing the operation updates the list; a missing
operation selection or closed program clears it.

Open **Review Tn geometry**, then choose **Choose cutter for Tn**. The embedded Cutters library
keeps that program number visible in **Use saved cutter for preview Tn**.
Select a saved cutter and apply it to return to the same simulation task,
operation, settings and scroll position. The assigned cutter remains in the
review list with its current name and dimensions. Missing or unsupported cutting
geometry continues to block calculation; a ready row describes declared cutting
dimensions, not verified assets or a physically installed cutter.

The selected cutter's saved default number stays unchanged. For example, a
cutter saved as T1 can supply the geometry for program T3 without replacing T1.
Unsaved edits and new cutters require an explicit Save first. Applying the saved
cutter changes only the local preview; it does not save a toolset, update
controller preferences, assign a physical ATC pocket or measure a tool.

A customized preview no longer claims to match the loaded saved bank. Matching
individual cutter provenance is retained for job capture. Previous material
removal and clearance results become historical; review the setup and explicitly
recalculate when ready. No playback, calculation or CNC command starts from this
action.

Preparation runs off the UI thread. A different program, setup, saved-library
revision, cutter selection or later navigation supersedes the pending assignment.
After publication, newer navigation or scrolling takes precedence over the return
position. A failed geometry publication restores the prior tool declarations and
pointer buffers; an incomplete redraw is reported explicitly. A return-position
failure after a successful assignment keeps the new cutter and reports that it
was applied.

This is a software workflow. Installed-app interaction and physical geometry,
stickout, ATC inventory, calibration and machining require separate verification.
