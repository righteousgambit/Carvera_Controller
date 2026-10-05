# Physical assembly definitions and custody

Setup → tool comparison → Physical assemblies & saved receipts maintains local
operator assertions separately from machine tool numbers and live offsets.

- New assembly creates a stable physical identity with an optional cutter design,
  holder identity and declared stickout. Cancel writes nothing.
- Edit assembly appends a revision with a required reason. It preserves the
  identity and all previous definitions. A stale editor cannot overwrite a newer
  revision, including one saved by another store instance. Rejection refreshes
  the local snapshot so reopening uses the current definition without saving the
  rejected draft.
- Declare at selected tool binds the installation assertion to the reviewed
  definition. Changing a definition leaves its old placement visibly in need of
  reconciliation. This does not configure the ATC or write an offset.
- Remove declaration requires a reason and preserves the assembly and history.
  A stale removal cannot clear a replacement declaration at the same location.
- Link a raw receipt retains original samples/source/time and binds explicit
  attribution to the reviewed definition. Existing unversioned links remain
  labeled unversioned; old measurements never become current after editing.
- Open cutter design navigates to the exact saved design and preserves departing
  library drafts. Missing references remain historical and can be relinked.

Editor forms adapt to available width; dialogs fit their content with bounded
scrolling. History presents the latest ten definitions and receipts, while the
append-only file retains all events within its configured size limit.
Desktop refresh checks a cheap event-generation token before copying history.

The schema remains version 1 with new revision/release event kinds. Existing
version-1 files load without inventing revision evidence for legacy assertions.
Older software that does not understand these event kinds must not write this
file. Writer locks and corrupt files are preserved rather than guessed away.

Source/UI tests exercise cancellation, required notes, stale edits/removals,
revision-bound attribution, restart, legacy files and linked-design navigation.
These assertions do not prove physical installation, tool seating or cutting.

## Assembly geometry preview

Preview assembly resolves the linked cutter design into canonical millimeters,
using the physical assembly's own declared stickout and optional holder CAD.
A catalog example's seating/holder is deliberately not inherited. Holder assets
must be converted tool-mesh JSON with a collet origin; Choose holder CAD uses the
shared artifact browser. Unknown stickout remains unknown and cannot qualify
reach or material-removal simulation.

The workbench and Scene cutter dropdown can select an assembly. Its definition
revision and linked-design fingerprint are retained with the temporary preview.
The Scene cutter inspector identifies this source separately from reported tool
state. Editing either the assembly or catalog design marks the rendered snapshot
older; it never silently updates the mesh. Preview again accepts the new snapshot.

Clear assembly preview restores the prior local tool definitions and manual
preview selection. Loading a replacement toolset supersedes the preview binding.
Mesh loading is transactional: missing or invalid CAD preserves the existing
preview. Catalog records, persistent toolsets, machine inventory declarations,
measured offsets and controller state are not written by previewing.

Material-removal input uses the resolved assembly geometry and includes its
identity/revision in rest-stock applicability. Holder CAD is rendered at the
collet face above the declared stickout. This remains declared visualization:
full swept holder collision, CAD byte-change monitoring, measured seating and
physical clearance qualification are still open.
# Dimensioned assembly inspection

`Inspect dimensions` opens the shared tool inspector at the selected physical
assembly revision without loading that assembly into the scene or changing saved
designs. The inspector offers 3D geometry and a dimensioned nominal schematic.
Undeclared overall length or stickout leaves insertion unknown. Incompatible
lengths reject inspection; no fallback dimension is presented as a declared value.
See `controller-assembly-and-machining-intelligence.md` for the additional scope.

## Sectioned tool passport

The physical assembly panel now provides Overview, Geometry, Assets,
Measurements, Locations and Revisions sections in place, preserving the current
assembly and the left-hand scene/camera views. Existing edit, attribution,
declaration and dimension-inspection actions operate on that selected assembly.

Geometry separates physical declared stickout from the linked design's nominal
dimensions. Inserted length is derived only when overall length and physical
stickout are known and compatible. Catalog holder and seating examples are not
inherited. Holder gauge length and qualified reach remain unknown.

Assets lists declared cutter CAD, physical holder CAD, drawing, source, vendor
and part-number references. This read-only projection does not perform filesystem
work on section changes or claim that an asset exists or has been verified.
Measurements retain raw samples, reported applied TLO, source, timestamp,
attribution note and exact revision association. Editing an assembly does not
promote old measurements or location declarations to the current revision.
Missing cutter references remain inspectable and can be relinked with Edit assembly.

Source checkpoint: 13 passport/custody model tests and 5 initialized-app
assembly/comparison integration tests passed; Ruff formatting/lint and diff
checks passed. Integration exercises in-place section changes, declared seating,
missing holder assets and command-free inspection. Installed visual acceptance,
recipe linking, measured holder/gauge geometry and qualified reach remain OPEN;
the full original tool-passport requirement is not closed by this checkpoint.

## Revision-bound facing recipes

Link facing recipe opens the existing artifact browser and reads/validates the
recipe in a worker. Review compares the recipe's flat-cutter diameter, cutting
length and stickout with the selected physical assembly, then displays material,
feed, spindle speed, pass depth, stepover and source tool/WCS. A required note
records the operator's process provenance. Saving rechecks exact file bytes and
appends a local `facing_recipe` custody event with SHA-256, assembly revision and
nominal cutter-design fingerprint. Save is disabled while committing; errors
leave the review retryable. No cutting outcome is inferred from a recipe link.

The Recipes section provides an explicit choice among linked facing recipes.
Restore rejects older assembly/design definitions and changed source files.
File reading and recipe validation run in the background. Only the parsed,
hash-checked snapshot reaches the UI; the currently loaded source tool number
and dimensions must match before planner fields are restored. The facing
disclosure opens in Setup. Restoration does not load tooling, apply offsets,
generate/upload a program or start playback. Catalog stickout is never used as
physical assembly seating. The fingerprint binds nominal design fields; it does
not establish CAD-byte validity or physical clearance.

Custody schema 1 now includes `facing_recipe` events. Older builds that reject
this event kind must not write the updated file. Existing records and failed
writes retain the append-only store's lock, merge and preservation semantics.

Source checkpoint: 30 relevant model tests and 18 initialized-app integration
tests passed, including required-note review, worker save with independent disk
readback, revision invalidation, unchanged planner state after modified-file
rejection and command-free restore. Installed visual acceptance remains OPEN.
Hole/thread recipe associations, actual cutting outcomes, measured holder/gauge
geometry and qualified reach remain unfinished parts of the original requirement.
