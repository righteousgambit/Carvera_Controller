# Tool-bank preparation

Program exposes a collapsible preparation board for programs with tool changes.
It preserves the source program and its logical tool numbers, divides sequential
tool use into candidate six-pocket banks, and lets each pocket select a saved
physical assembly. The board expands directly below its heading, ahead of
simulation bookmarks. Pocket cards reflow between one and two columns.

Each row opens the assembly's custody and attributed measurements or previews
its cutter/holder geometry at the program tool number. Selecting, previewing and
saving do not send controller commands, change actual pocket declarations,
write offsets, upload programs, or start playback. Duplicate physical assemblies
within a bank are rejected without discarding the previous valid choice.

Preparations are stored locally in `~/.carvera/tool-bank-reviews.json`, bound to
the parsed program hash, machine profile, bank source range, physical assembly
revision and cutter definition fingerprint. This fingerprint binds declared
profile fields; it does not independently bind CAD asset file contents. Partial
preparations are allowed. Switching banks or machine profiles preserves unsaved
notes and choices in the current session. Reload explicitly discards that context's
draft and rereads the saved preparation.

The board separately reports selected assemblies, matching pocket declarations,
and attributed measurement receipts. A receipt is applicable here only if its
endpoint, program tool number and linked assembly revision match, and the bound
cutter definition remains current. This is not proof of actual controller
mapping, current seating, measurement freshness after a reload, calibrated offset
application or safe re-entry. Raw attributed reports remain available when the
definition changes, but stop contributing to the applicable count.

Saves merge under an exclusive local lock and reject stale writer revisions.
Invalid original files and failed writes are preserved. An incomplete or invalid
record cannot replace another program/machine/bank preparation.

## Remaining executable workflow

Requirement 9 in `controller-evolution.md` remains open. Completion needs actual
backend-specific stop/reload/mapping reconciliation/calibration/offset validation
and resume transactions, with machine readback and qualified approach motion.
The original program is not rewritten or split by this board, and its existing
playback controls are not gated by preparation records. No preparation record
authorizes execution. General magazines also require backend-specific pocket
capacity, probe/manual tool classification and fixed/random changer semantics;
the six-pocket planner is currently a Carvera candidate preparation workflow.

Source tests cover machine/bank isolation, definition invalidation, receipt
attribution, stale writers, corrupt-store preservation, failed atomic writes,
draft restoration, invalid selection rollback, command-free preview and responsive
card containment. Installed UI interaction and physical execution are separate
verification gates.
