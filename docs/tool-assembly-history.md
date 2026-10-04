# Physical assembly definitions and custody

Setup → tool comparison → Physical assemblies & saved receipts maintains local
operator assertions separately from machine tool numbers and live offsets.

- New assembly creates a stable physical identity with an optional cutter design,
  holder identity and declared stickout. Cancel writes nothing.
- Edit assembly appends a revision with a required reason. It preserves the
  identity and all previous definitions. A stale editor cannot overwrite a newer
  revision, including one saved by another store instance.
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
