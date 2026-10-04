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
