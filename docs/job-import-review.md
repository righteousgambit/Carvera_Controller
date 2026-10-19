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
- Renderer preparation inputs and generated vertex count. Clearance height,
  cached work Z offset, display units and arc resolution are captured explicitly;
  editing them requires a new review.

Select a section, page through its values, or use **Find next**. Large windows
support a side-by-side comparison. Compact windows offer a **Current / Imported**
selector so the text remains readable and Apply/Cancel remain available.

**Cancel import**, Escape or dismissing the dialog leaves the current preview and
saved tool inventory unchanged. Staged assets remain in the local jobs directory.
**Apply local preview** rechecks the staged program and every embedded asset's
actual bytes against their SHA-256 hashes on a worker. A missing, linked or changed
file blocks application. The program loader receives the immutable, worker-prepared
UTF-8 program lines rather than reopening the staged path after verification. Setup, relevant tool inventory, program, calibration,
connection or planning-context changes during preparation/review/verification
require a new import and review. An unrelated saved tool edit does not invalidate
an otherwise current proposal.

Application publishes the prepared setup and starts the program preview load.
The status remains loading until that load reports the matching program hash and
generation; failure, cancellation or supersession does not report restoration
success. Invalid UTF-8 is rejected during preparation.

Application publishes the prepared preview geometry and local declarations. It
does not connect the CNC, move it, change physical tool custody, measure tools,
save imported definitions into the local inventory or qualify placement. Imported
coordinates remain unmeasured. Individually loaded cutter-profile bindings are
cleared when replaced by imported preview definitions. Manual cutter preview returns
to following the program. The review exposes the replacement of repeated-part
stock with the imported single setup and detects intervening repeat-plan edits.

## Detached program preparation

Before opening review, the archive worker runs the exact legacy preview parser
against the retained immutable program lines using its own variable map. It does
not reset live margins, update the controller's cached feed mode or borrow a
mutable parser from the current program. Unit/arc settings and the two cached
clearance inputs are explicit captured inputs. The default interactive parser
retains its existing shared-state behavior; callers opt into detached variables.

Prepared imports have a two-million generated-point work limit. Checks run inside
rotary interpolation, arc expansion and canned-cycle repetition, so a single huge
block cannot postpone the limit until its entire point list exists. Obsolete
imports cancel at line boundaries, every 128 generated points, and during
parenthesized-comment scanning every 4096 characters. Comment stripping uses a
linear scan with the legacy non-greedy/nested/unmatched/newline behavior retained;
a long unmatched comment prefix cannot force quadratic regex backtracking. A numerically
unrepresentable arc step fails rather than entering a zero-step loop. Inputs are
never silently replaced when cached values are invalid. The worker reports these
failures before applying setup, tools, calibration or the program selection.

The preparation report is a renderer check. It is not a strict G-code language
validator, controller acknowledgement, clearance check or machining qualification.
Legacy unsupported-word behavior remains unchanged. Portable imports now retain the worker-prepared path buffers, source metadata,
CAM cutter table and cutter meshes through Apply. Apply publishes those prepared
buffers without reparsing the program or reopening the staged program file. The
raw-byte and normalized-source manifest is also prepared from retained bytes.
The program-level publication retains the previous manager, source rows,
selection, parser state, margins, view and resume declarations for recovery if
renderer, page or finalization publication fails. Cancellation generations never
rewind, and recovery changes only program margins rather than restoring a stale
copy of live telemetry. Persistent drawing failure retains the old model and
withholds its displayed identity; it cannot guarantee a recovered image.

Prepared cutter, holder, machine, fixture, vise and stock source digests are
checked against retained archive bytes before review. Tool asset loaders validate
the bytes consumed against their prepared digest; a temporarily changed extracted
asset cannot become trusted geometry merely by being restored before Apply.

Ordinary local/remote loading still uses the existing incremental loader. This
portable-import path does not close complete Apply rollback or installed
responsiveness: scene construction, GPU publication, source page formatting and
some renderer asset reads remain on the UI thread. Long unmatched parentheses in
source highlighting use escaped plain text instead of unbounded syntax-regex
backtracking; the full source remains available without truncation.

## Acceptance limits

Apply now captures the complete previous local setup and program before publishing
any imported declarations. Machine CAD and component selections, workholding,
stock/repeated-part state, cutter definitions/assembly override, toolset summaries,
program data/controls, camera calibration drafts/reference framing, scene choices
and selection labels are recovered together after a failed pre-commit step. Shared
coordinate maps retain their identity. Program, camera-reference and camera-source
generations advance instead of rewinding; a restored valid image-pick undo is
rebound to the new reference revision. Camera frames that were invalidated by a
source change are not fabricated or presented as freshly recovered exposures.

Imported profile selection skips ordinary saved-scene seeding: applying an archive
does not save machine components into the scene library or reload another scene
over the imported placement. Saved cutter and scene inventories are unchanged.
Active fixture/vise/stock workers block import rather than racing publication.

The program manifest is staged until the entire local preview has published. The
commit checks its completed source identity, selected path, program/import
request generations and cached connection generation. Imported camera URL and
selected-profile preferences are committed last. Preference replacement uses a
same-directory temporary file, flush/fsync and atomic replace, with an intervening
file-revision check. Failed preparation or replacement leaves the prior file
intact. This is atomic file visibility, not cross-process compare-and-swap or
power-loss durability qualification. Preferences are read and serialized locally;
this is not a claim that Apply is free of UI-thread file or rendering work.

Before that commit, failure reports whether the previous local preview was
restored. If reconstruction fails (for example, a persistent renderer fault), the
retained previous numeric model remains available and its displayed program
identity is withheld; the review reports incomplete recovery. Closing the review
preserves that distinction. After commit, evidence/notification failure does not
pretend to undo the accepted setup. Unexpected evidence-observer failure withholds
recording program identity and reports a recording gap; journal durability remains
a separate gate.

Installed interaction, latency, camera exposure synchronization, actual backend
ownership, physical setup and execution qualification remain open. Source and
fake-transport UI tests do not close those gates.

The immutable preview handoff qualifies only the bytes consumed by the local
preview parser. Export, recording and upload apply their separate selection and
byte checks described in [Program identity through later effects](program-byte-custody.md).
Those local checks do not qualify machine-side acknowledgement, decompression,
installed execution or physical setup.

Operation analysis for a committed portable job now consumes that same immutable
preview text. Reanalysis after changing dialect, spline tolerance or segment budget
uses the retained text too, even if the staging file has been replaced or removed.
Text validation and parsing run on the analysis worker; completion checks the
current selection, displayed hash and retained text owner before publishing.
A failed import can rebind the recovered source to the advanced preview generation
without reopening the file or discarding a still-valid pending analysis. Superseded
workers cannot replace newer analysis. Changing the preview generation
invalidates the portable-job cache. Completed ordinary local previews receive
their own immutable worker-text handoff; standalone inspection and remote-file
analysis retain their existing file-based behavior. This extends local preview
custody, not upload or execution qualification.
