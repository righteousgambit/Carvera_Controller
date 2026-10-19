# Review a portable job before applying it

The Program workbench's **Import & review job** action opens a `.cvjob`
archive into a staged review. Selecting an archive keeps the current local
program, stock, workholding and cutters visible. Archive validation, CAD loading,
stock preparation and cutter mesh preparation run on a worker rather than the UI
thread. Only one archive preparation runs at once; selecting more archives keeps
only the newest pending selection.

The review shows the current declarations beside the effective imported proposal:

- Program name, byte count and SHA-256.
- Machine profile and registered fixture/vise geometry.
- Stock dimensions, placement and work coordinates.
- Preview cutters, toolset and saved-inventory conflicts or missing records.
- Retained camera calibration, embedded asset hashes and retained job metadata.

Select a section, page through its values, or use **Find next**. Large windows
support a side-by-side comparison. Compact windows offer a **Current / Imported**
selector so the text remains readable and Apply/Cancel remain available.

**Cancel import**, Escape or dismissing the dialog leaves the current preview and
saved tool inventory unchanged. Staged assets remain in the local jobs directory.
**Apply local preview** rechecks the staged program and every embedded asset's
actual bytes against their SHA-256 hashes on a worker. A missing, linked or changed
file blocks application. Setup, relevant tool inventory, program, calibration,
connection or planning-context changes during preparation/review/verification
require a new import and review. An unrelated saved tool edit does not invalidate
an otherwise current proposal.

Application publishes the prepared preview geometry and local declarations. It
does not connect the CNC, move it, change physical tool custody, measure tools,
save imported definitions into the local inventory or qualify placement. Imported
coordinates remain unmeasured. Individually loaded cutter-profile bindings are
cleared when replaced by imported preview definitions.

## Acceptance limits

This workflow adds a cancellable staging/review boundary. Final publication still
uses the existing sequence of local profile, renderer, program and calibration
updates. A failure partway through publication is reported and assets retained;
there is no atomic rollback of that sequence yet. The full editing-transaction
requirement therefore remains open. The dialog must also be exercised in an
installed controller before installed-workflow acceptance is claimed. Source and
synthetic UI tests do not establish physical setup, camera registration or machine
execution qualification.
