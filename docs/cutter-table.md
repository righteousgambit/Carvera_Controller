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

A follow-up separates write serialization from the short state-publication lock.
Readers receive the last committed profile snapshot while a disk write or reload
is pending, so slow filesystem work cannot hold a profile reader on the UI thread.
A deliberately blocked disk commit verifies reader availability and old/new
generation coherence. The current 54-check profile/table run passed in 17.33
seconds. DESKTOP127 was superseded before installation; its original source and
build are retained. The follow-up will be packaged as DESKTOP128.

## DESKTOP129 native acceptance

The installed app was exercised with the operator's three saved cutters. Arrow-key selection, Shift range selection, sorting, vendor search and retention of a selected cutter outside the filter were observed. A two-row paste with 4-inch stickouts was rejected without writing the library. A revised 1.5-inch paste showed the two changes explicitly and saved exactly two local nominal stickouts as 38.1 mm. Independent JSON readback confirmed every other library field was identical. After clean exit, all eight operator stores and the original Kivy configuration were restored from the pre-install backup; the temporary values are not physical measurements or retained operator configuration.

OPEN — Native column-divider dragging: two fast native drags from the Name divider sorted the landing header instead of resizing the column. The delayed synthetic-touch source test passed, so it does not close this native gate. Owner: root controller lane. Next action: investigate ScrollView's deferred touch delivery, add a fast-drag regression, and qualify the fix in a rebuilt installed app. Preserve the current DESKTOP129 recovery/acceptance receipts while doing so.

## DESKTOP131 divider acceptance

CLOSED — The native divider gap above was resolved in application source
`cc24627ab1355eb2c6bb7077f771453c408331e1`, installed as DESKTOP131. The initial
DESKTOP130 attempt did not resolve the native failure; its screenshots and logs
remain in `/Users/wes/Downloads/carvera-desktop130-20261004/`.

An isolated native pointer trace showed mouse-down and mouse-up delivered about
1 ms apart before the next Kivy input dispatch. The mouse provider reused a
mutable event, synchronizing its original position to the final drag position
before delivering begin. The header now preserves the original press only for
divider gestures before the provider processes movement, immediately captures
the divider, and applies the final displacement on release. Its native observer
is removed when the popup closes. Ordinary header sorting remains separate.

The reproduced coalesced-event test failed before origin preservation and passed
afterward; the complete cutter-table integration suite passed 3 tests in 24.03 s.
Ruff lint/format and diff checks passed. Native DESKTOP131 gestures expanded and
restored Name, shrank Diameter, retained Name sorting during resize, and then
successfully sorted by Tool. Rendered cells remained aligned with the headers.
Source tests additionally exercise a divider after horizontal scrolling; that
specific scrolled gesture was not exercised natively in this checkpoint.

Built/installed manifests and strict signatures were verified separately.
Receipts and native screenshots are retained in
`/Users/wes/Downloads/carvera-desktop131-20261004/`. The app was returned to Live
with reported Idle, fresh controller telemetry, and the live Ubuntu camera. This
closes column-drag acceptance, not the complete tool-passport workflow or the
overall 25-item roadmap.

Native screenshots, local-save readback and restoration receipt are in `/Users/wes/Downloads/carvera-desktop129-20261004/`. No program start, machining, tool change or offset application was performed in this acceptance workflow. The broader controller implementation goal remains OPEN.
