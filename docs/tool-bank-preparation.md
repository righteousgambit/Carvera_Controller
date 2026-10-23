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

Mapped controller receipts are counted separately from logical program-tool
receipts: bank two's program T7 is candidate controller T1. A mapped receipt
must match the endpoint, assembly revision and current cutter definition, have
an applied TLO, and have both its measurement and capture timestamps at or after
the latest matching declared placement. Redeclaring an assembly invalidates
earlier receipts. Placement and measurement links remain operator declarations.

The board compares that receipt with fresh current-spindle status only when
the reported tool number matches the candidate controller tool. Missing or stale
status, another spindle tool or missing TLO produces an unknown comparison.
It displays both numbers and a 0.001 mm numeric comparison tolerance; this is
not a part tolerance or physical tool identity check. Unchanged fresh telemetry
does not rebuild pocket cards; tool, offset and freshness changes refresh them.

The final affected suite passed 13 tests (1.14 seconds), covering post-placement
receipt identity, stale measurements, revision changes, fresh numeric comparison,
card reuse and command-free interaction. Receipt:
`/tmp/carvera-bank-offset-final-tests.log`. Installed acceptance remains open.

Saves merge under an exclusive local lock and reject stale writer revisions.
Invalid original files and failed writes are preserved. An incomplete or invalid
record cannot replace another program/machine/bank preparation.

## Remaining executable workflow

Saved pocket rows offer **Review exchange** and **Review measurement**. Each
opens the corresponding backend panel with the saved program hash, machine
profile, bank/source range, preparation revision, logical tool, controller
pocket, assembly revision and cutter fingerprint. Bank 2's Program T7 can
therefore show its selected assembly while the reviewed rack command targets
Controller T1. The loaded preview library and original program are unchanged.
Unsaved choices, replaced assemblies and stale preparations refuse this handoff.

Navigation sends no command and does not assert an installed cutter kind. A
direct measurement review supports an already-installed current tool and is
labeled as saved bank preparation. The exchange panel's separate **Continue to
measurement** action requires its retained later Idle/current-tool receipt,
the original backend connection and a current matching report. This route
retains the exchange journal lineage and is labeled as following that exchange.
Both routes retain the existing explicit review and dispatch gestures.

Changed program, bank, machine, assembly or design invalidates an open review.
After durable intent is saved and the backend snapshot returns, the worker rereads
the saved preparation. The exchange-followup route also rereads its retained
exchange receipt. The final UI check revalidates current context without file IO
and refuses verification older than 500 ms, including time spent reading. This
detects external saved revisions through that last worker read; filesystem edits
and controller submission are not one atomic transaction. No pending action is
automatically retried. **Use preview
tools** explicitly returns a settled panel to its ordinary library-based review.
Measurement samples still enter the passport unassigned; bank intent establishes
neither physical attribution nor applied TLO. These source workflows require
separate installed and physical qualification.

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
