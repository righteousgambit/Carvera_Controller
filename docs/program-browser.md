# Desktop program browser

`ProgramBrowser(workspace)` is owned by `DesktopWorkspace` and opened by its
Choose program action. The browser starts in **This computer** so opening a
local program never transfers it implicitly. **Machine files** is an explicit
location using the existing controller connection and legacy remote-directory
buffer. There is no additional CNC session.

Folders stay navigable alongside `.cnc`, `.nc`, `.gcode`, `.tap`, and `.ngc`
programs. Search applies within the current folder. Up, editable folder/program path,
Home, Downloads, and Refresh provide navigation. Local details show size,
modification date, and a bounded text excerpt. A missing or unreadable folder
produces an error instead of an apparently empty listing.

Enter or the adjacent **Go** action opens a full local program path's containing folder and selects the
file for background inspection. Relative paths are interpreted from the folder
currently being browsed. Extensions are case-insensitive and spaces in file
names are preserved. Unsupported files, missing folders and malformed paths
clear the previous selection and inspection rather than leaving an old program
actionable. Entering a path does not preview, upload or run a program.

The source regression first reproduced the installed full-path failure. After
repair, 12 browser unit checks and 10 inspection integration checks passed,
including full/relative paths, case-insensitive extensions, spaces, malformed
paths, missing users, stale inspection cancellation and compact/wheel behavior.
The rendered full-path inspection was visually reviewed. Focused Ruff checks
and both architecture import contracts passed. Installed acceptance of this
browser repair remains open; DESKTOP107 predates it.

## DESKTOP108 installed acceptance

DESKTOP108 was installed from `d0aeddab3405f544a662d72eaba2ea901f2ceeae`.
Native inspection confirmed a full program path through Go, a relative path
through Enter, and clearing of selected file/details/thumbnail and disabled
preview/upload after an unsupported file. No preview, upload or run action was
pressed. At 17:58:45 UTC all 430 repository and 433 staged/built/installed
manifest entries matched, strict signatures passed, and seven operator stores
plus configuration matched the fresh backup exactly. Normal relaunch showed
Idle, fresh reported pose, zero RPM/feed and live camera; Live view was restored.
Receipts are under `/Users/wes/Downloads/carvera-desktop108-20261004/`.

The first archive copy dereferenced bundle symlinks and failed signature
verification. The installer rejected it before replacing the installed app.
The failed copy and receipt were retained; a macOS `ditto` copy preserved links
and passed verification before installation. Future bundle archival must
preserve symbolic links and verify the destination signature before use.

## Local program shortcuts

Recent inspections retain the last 25 successfully inspected local program
paths, newest first. Favorites retain up to 100 explicit local references.
Neither list establishes that a program was run or that its contents are
unchanged. Selecting a reference performs a fresh inspection. Folder paths in
rows distinguish same-named files, and search matches the saved full path.
Missing references remain visible with preview/upload disabled and can be
removed from Favorites. Collection navigation identifies its virtual location;
Home, Downloads and This computer return to folder browsing.

Program references persist in `.carvera/program-places.json`, using bounded,
validated documents and atomic replacement with readback. Damaged documents
are retained and reported rather than overwritten. UI tests isolate this store
alongside the other operator stores. The browser initially uses the selected
program's folder, then a valid prior folder outside application bundles, then
Home. These source extensions are not included in DESKTOP108.

Source verification: 21 program-reference/browser unit checks and 12 shortcut/
inspection integration checks passed. Coverage includes persistence, recent
ordering and bounds, same-name paths, missing references/removal, stale async
inspection, malformed store preservation, failed atomic replacement, full-path
entry and compact/wheel interactions. The favorite-list render was visually
reviewed. Focused Ruff lint/format passed and both architecture contracts kept
(184 files, 748 dependencies). DESKTOP109 native shortcut acceptance is recorded below.

**Preview locally** uses the existing local preview workflow. **Load from
machine** uses the existing download-and-select workflow and does not start
execution. **Upload to machine** is separate, enabled only for an idle connected
machine without another transfer. It refreshes the destination first, then uses
the existing upload path and overwrite confirmation. Closing the browser cancels
any pending upload continuation; an already requested read may finish normally.
The browser offers no deletion, rename, firmware, or run action.

Integration must call `workspace.program_browser.directory_failed(error_msg)`
from the root's `loadError` callback. The legacy directory loader clears its
error flags before filling its result buffer, so those flags alone cannot prove
that an empty listing succeeded. The callback cancels an upload continuation on
failed directory reads.

The popup uses the shared desktop components and limits width to 1000 display
points. `tests/unit/test_program_browser.py` verifies filtering, bounded previews,
existing-session download dispatch, fresh destination checks, failure handling,
and idle-state changes without physical hardware.
# Captured program setup dependencies

The detail inspector separates Path, Setup and Source so a quick geometric preview
does not compete with setup notes and source text. Setup compares the captured
candidate's tool IDs with the current canonical preview library, distinguishing
active parsed tools from preselection. Ordered six-pocket Carvera bank assignments
are drafts, not source rewriting or physical pocket assignments. At most eight
banks appear in the quick inspector; local preview retains the complete plan.

Machine/toolset names, declared stock and locally confirmed alignment describe
current local context. Refresh setup check rereads that context without replacing
the candidate program or touching the connected machine. Review setup opens Scene
without loading/uploading the inspected file. Multiple work frames require their
own registered transforms; library presence proves neither complete geometry nor
physical tool identity. Travel, clearance and physical offsets remain unchecked.

DESKTOP109 installed/native acceptance of recent inspections and favorites is
retained at `/Users/wes/Downloads/carvera-desktop109-20261004/native-receipt.json`.
Favorite persistence was exercised across an actual app relaunch. Operator stores
and configuration were restored; 431 repository and 434 staged/built/installed
files matched, with strict built/installed/recovery108 signatures passing.
A transient reconnect dialog occurred; restored Idle telemetry and live camera
were observed afterward. Compact installed acceptance remains open. The dependency
inspector and detail tabs are subsequent source changes requiring their own build
and installed acceptance.

Dependency/tab source verification: 19 focused unit checks passed. Thirteen
browser/shortcut integration checks passed; after adding hidden-focus handling,
the final 11 inspection checks passed, including native-provider wheel delivery
in both directions, tab focus clearing, compact layout, stale inspection rejection
and setup navigation without loading or transfer. Setup-tab render was reviewed.
Ruff lint/format and both architecture contracts passed (185 files, 752 dependencies).

## DESKTOP110 installed inspector acceptance

DESKTOP110 built from `07def4757a48795792806e860c99bedbbcd43c72` passed native
Path/Setup/Source switching, current-profile dependency inspection, explicit setup
refresh and Review setup navigation to Scene/Stock. The candidate remained unloaded.
At 18:26:05 UTC, 432 repository and 435 staged/built/installed manifest entries
matched; built, installed and recovery109 strict signatures passed. Operator stores
and configuration matched the clean-exit backup. Restored normal launch reported
Idle C1, G54 XYZ (-232, -195.28, -53.48) mm, T1/TLO 50.480 mm, zero RPM/feed,
fresh telemetry and live camera. Live visualization was restored. Receipt:
`/Users/wes/Downloads/carvera-desktop110-20261004/native-receipt.json`.

The initial system-Python build failed without PyInstaller; that log is retained.
The correct packaging environment produced the verified artifact. A delayed Quit
caused the first backup to refuse; clean-exit backup succeeded before native launch.
The archived install helper now requires backup baseline/config files before use.
Compact native acceptance, full compatibility/travel/clearance review and physical
qualification remain open. No machining or controller configuration writes occurred.

## Frame-specific candidate inspection

The Path detail now offers each declared work frame independently, including
frames without resolved motion. Selecting a frame changes only the inspection
thumbnail and its dimensional summary; it never loads, uploads or executes the
program. Unknown-frame geometry is labeled explicitly. Multiple unregistered
origins are not overlaid.

Resolved program-coordinate bounds are accumulated from every interpreted move
before thumbnail sampling. Circular moves include analytic axis extrema; the
thumbnail remains a bounded sampled XY representation. Short frame sections
retain their own samples even when global decimation would omit them. The
summary identifies its frame, millimeter units and resolved source-move count.
Unknown initial approaches, machine-coordinate moves and unresolved semantics
are excluded and remain reported. These bounds do not establish machine travel,
registered setup placement or cutter/holder clearance.

The setup report retains complete missing-tool requirements while limiting long
displayed lists and exposing the full count. Candidate selection or refresh
clears frame details along with the previous inspection. Installed acceptance
of the new frame selector remains OPEN until exercised in the packaged app.

The broader consumer test run exposed four failures also reproduced against
unchanged HEAD in an isolated checkout. Navigation/bookmark test workspaces
omitted the required preview transition. Their fixtures now provide and verify
that transition before seeking; the product requirement remains intact.

## DESKTOP111 installed frame inspection

DESKTOP111 is installed from `e62994d0ad9820572e224b623e8a312a7a15844f`.
Native interaction exercised the frame dropdown, distinct G54/G55 thumbnails
and dimensional summaries, refresh clearing, and an unresolved G55 with an
empty thumbnail and explicit unavailable-bounds message. These specific
installed inspection gates are CLOSED. Compact native interaction and actual
registered machine travel/assembly-clearance qualification remain OPEN.

At 18:49:36 UTC, all 432 repository and 435 staged/built/installed manifest
entries matched and strict signatures passed for built, installed and recovery
DESKTOP110 bundles. Eight operator-store identities and the configuration matched
the fresh clean-exit backup. Normal relaunch restored Live view and showed Idle,
G54 XYZ (-232, -195.28, -53.48) mm, physical T1/TLO 50.480 mm, zero RPM/feed,
fresh telemetry and live camera. No program was loaded, uploaded or started.
Receipts are under `/Users/wes/Downloads/carvera-desktop111-20261004/`.

Local disk exhaustion interrupted additional fixture creation and UI screenshot
capture. The current temporary build directory was preserved by moving it to
`local-build-evidence` on the archive volume, recovering about 335 MB locally.
The same native process was re-read before resuming. Operator restoration and
artifact verification subsequently completed; failed-attempt evidence remains
retained. Future packaging must account for available temporary storage.

## Captured revision comparison

Compare retains a pinned immutable inspection in this browser instance. Inspect
another file or replace the same filename and inspect it again to compare fresh
captured bytes with that baseline. Refresh or an unavailable selection clears
the candidate report while retaining the explicit baseline; Clear baseline
removes it. Pinning, comparing and clearing never load, transfer or execute a
program. The baseline is an inspection/digest, not a copy of the complete source.

The semantic summary compares units, work frames, active/declared tools, ordered
operation names, feed/spindle declarations, six-pocket bank assignments, source
line count, resolved per-frame dimensional bounds and unresolved-motion counts.
Matching summary fields with different digests leave other changes unclassified.
Feed/spindle declarations are sets of parsed states, not a chronological motion
diff. Bounds exclude unresolved motion and do not establish clearance. Lists
are bounded for display; full captured requirements remain available internally.

Changes lead the Compare detail; revision digests and file locators remain in
the scrollable report. Detail tabs wrap into a grid at narrow widths, and
content reserves room for the scrollbar. Installed comparison acceptance and
complete source-line/trajectory differences remain OPEN.

Packaging now checks the output volume and temporary storage for a conservative
1 GiB free reserve before staging or invoking the packager. A failing check
reports the affected path and aborts before creating build output. This prevents
the observed low-space start condition; the reserve is not a guarantee against
later concurrent disk consumption or filesystem failure.

Revision-comparison source checkpoint: 90 targeted unit checks and 15 browser
integration checks passed. Ruff lint/format and both import architecture
contracts passed (186 files, 755 dependencies). The revised Compare render
was visually reviewed after repairing scrollbar overlap and detail-tab wrapping.
Installed DESKTOP112 functional checkpoint (2026-10-04): source
`32602b4698ecefca729ec73d6381c827e0406f27` passed native pin/candidate,
tool/feed/spindle/bank/bounds comparison, refresh-retains-baseline and clear
interactions. The two-row tabs and scrollbar clearance were observed in the
installed app. Supplemental comparison/storage suite: 11 checks passed.

Receipts and screenshots are retained in
`/Users/wes/Downloads/carvera-desktop112-20261004/`: `native-receipt.json`,
`artifact-verification.json`, and `operator-restoration.json`. Source 433 and
staged/built/installed 436 entries had zero manifest mismatches; built,
installed and preserved DESKTOP111 strict signatures passed. Operator stores
and configuration were restored before a normal relaunch and fresh Idle,
zero-RPM/zero-feed telemetry plus Ubuntu camera readback.

Presentation acceptance remains OPEN: comparison arrows render as missing
glyphs in the native font. Connection-loss overlays twice interrupted local
navigation; automatic reconnection restored telemetry, but cause is unproven.
Preserved screenshots expose this separate responsiveness/reconnection gap.
Full trajectory/material-removal comparison and physical qualification remain
OPEN; local file inspection did not load, upload or execute a program.

## Responsive local navigation source checkpoint

Local path checks, folder enumeration and shortcut-file metadata reads now run
outside the UI thread. One active worker and one coalesced latest request bound
the filesystem work. Navigation immediately clears the actionable candidate;
generation checks reject results after newer navigation, selection, collection
changes or dismissal. Recent/favorite collections reread their persisted store
in the worker, retaining unavailable references for removal.

Comparison changes use the word `to` instead of native-font-missing arrows.
Verification: 21 unit checks and 16 interaction checks pass, including a blocked
filesystem reader while the Kivy clock continues, rapid-navigation coalescing,
dismissal rejection, full/relative/invalid paths, shortcuts and comparison.
Lint/format and both architecture contracts pass. Rendered comparison layout was
reviewed. Installed acceptance of these source changes remains OPEN.

This does not establish the cause of the observed reconnect interruptions.
Constructor directory validation and recent/favorite persistence still contain
synchronous filesystem calls; reconnect-modal ergonomics and those remaining
I/O paths need separate work. A filesystem operation already blocked in the OS
cannot be canceled; a newer read waits for that worker to return while the UI
remains usable.
