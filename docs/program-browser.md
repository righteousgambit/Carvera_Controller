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
(184 files, 748 dependencies). Native installed shortcut acceptance remains open.

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
