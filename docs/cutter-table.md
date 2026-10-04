# Cutter comparison and spreadsheet review

The cutter library's Table action opens a desktop comparison surface with name,
logical tool number, cutting and shank diameters, overall/cutting length, nominal
stickout, vendor, part number, shape and stable library ID. Dimensions display in
millimeters. Header clicks sort both ways; separate divider targets resize columns.
The header tracks horizontal scrolling. Recycled rows bound widget creation to
the viewport even for the library's 1,000-record maximum.

Click selects a row; Cmd/Ctrl toggles and Shift extends ranges. Up/Down, Home/End,
Page Up/Down, Shift ranges, Cmd/Ctrl+A/C/V, Enter to edit and Escape to clear work
inside the focused table. Selection uses stable IDs, survives sorting/filtering,
and exposes the count outside the current filter. Copy includes those hidden
selected records as well. Edit routes a single selected identity to the existing
editor and retains other unfinished drafts. Table filtering uses the library's
same unit-aware filter dialog and metadata search.

Copy selected TSV exports explicit headers and IDs. Paste accepts those headers
or internal field names, with ID plus at least one editable column. Row positions
and names never infer identity. Fractional/imperial dimensions use the shared
quantity parser; blank optional dimensions clear a value, while required values
remain required. All rows and cross-field constraints validate before a review
exists. Duplicate/unknown IDs or columns, inconsistent row widths, unsupported
values and invalid cutter geometry reject the whole paste.

Validation runs off the UI thread. Reviewed changes show saved/proposed values
in pages of at most 30 cutters. Editing the paste or closing the dialog invalidates
pending work. Save reviewed locally performs one validated atomic library commit
in a worker; it cannot silently cancel after commit starts. Generation changes,
detected external file changes and unfinished conflicting editor drafts prevent
the save. Reload explicitly rereads the saved library in a background worker,
retaining editor drafts and keeping invalid files from replacing current data. The file
check does not claim cross-process locking across an external check/write race.

Local saved nominal profiles, active preview definitions, physical assemblies,
measured offsets and controller assignments remain separate. Neither comparison,
review nor a local bulk save applies a physical tool or sends machine commands.
The desktop data-grid and tooling requirements also include offset/measurement/
magazine grids, physical instances, richer assemblies and qualified execution;
those full requirements and the overall implementation goal remain OPEN.

Verification and installed acceptance are recorded below after actual checks.

Source verification on October 4: 66 table/profile/browser/draft checks passed
in 42.64 seconds. The final 19-check table run passed in 21.12 seconds after
adding delayed-worker invalidation, 95-cutter paged review, atomic-save liveness,
external file rejection/reload, retained drafts and hidden-selection copying.
The 1,000-cutter interaction created fewer than 50 visible recycled row widgets;
actual pointer gestures sorted a header and resized a divider. Temporary-library
saves were independently reread from disk; no controller commands or active-tool
application calls occurred. Both import contracts and Ruff passed. Wide, compact
and review renders were inspected; the first invalid-shape fixture mistakenly
used the supported `unknown` shape and was corrected to an unsupported value.
The cancelled initial test startup and failed fixture evidence are retained.

Installed/native interaction and latency evidence remain separate gates.
