# Desktop profile library

The library separates named machine preferences, cutter geometry, and planned
six-slot ATC sets. These are local profiles, not measured offsets or a record of
which cutter is physically loaded.

- **Machines:** name, C1 or CA1 model, address, port, camera snapshot URL, and
  optional converted machine CAD profile path. Using one supplies workspace
  preferences; the user still connects through the connection control.
- **Cutters:** name, program tool number, supported tool shape, cutting/shank
  diameters, overall/flute lengths, corner radius, thread pitch, manufacturer,
  part number, and notes. All library dimensions are millimeters. A blank optional
  dimension means unknown. Overall cutter length is not measured spindle stickout
  or tool length offset.
- **ATC toolsets:** a name plus up to six slot-to-cutter references. Slots are
  numbered 1 through 6; the same cutter profile cannot occupy two slots in a set.
  A second physical cutter can have its own separately named profile. Loading a
  set produces preview `ToolDefinition` objects numbered by slot; no tool change,
  offset write, spindle command, or other CNC command is sent.

The initial cutter inventory contains only the three photographed quarter-inch
end mills. It assigns no ATC toolset and assumes no machine address. The workspace
may save its existing connection settings as the first named machine.

Profiles live at `~/.carvera/profiles.json`, schema 1. Save validates the complete
library, writes a temporary file in the destination directory, flushes it to disk,
and replaces the destination atomically. Failed saves leave the prior in-memory
and on-disk library intact. Invalid existing files are preserved and reported,
not silently replaced with defaults.

Import merges a complete schema-1 JSON library by stable record ID. An imported
record with an existing ID updates that record. New IDs create new records.
Toolsets must refer to tools included in that library. Validation completes before
any write. Export writes the entire local library. Files are limited to 2 MiB;
each category is limited to 1,000 records. Embedded camera URL credentials and
nonfinite, invalid, or out-of-range dimensions are rejected.

## Integration

`ProfileLibrary(workspace, store=None)` is a Kivy widget suitable for a focused
modal. It contains searchable categories, a scrollable editor, save/delete,
import/export, and an explicit apply action.

The workspace provides these read-only/local hooks:

```python
apply_machine_profile(profile_dict)
apply_tool_profile(profile_dict, slot=None)
apply_toolset_profile(toolset_dict, definitions_in_mm)
choose_profile_file(callback, save=False)  # optional native/modern JSON picker
```

`ProfileStore` exposes detached `.data` readbacks, `save_machine`, `save_tool`,
`save_toolset`, `delete`, `import_file`, `export_file`, and
`toolset_definitions(toolset, units="mm")`. `to_tool_definition(profile,
number=None, units="mm")` converts profile dimensions into a viewer's G-code
units without changing the saved record. Default toolset apply passes millimeter
objects; the workspace owns conversion to the active preview's units.

The library adapts to available width. On desktop widths the saved-profile list
is capped at 280 dp and related fields share two-column sections. Below 760 dp
the list moves above the editor; individual sections collapse to one column
when there is insufficient room. Category and file-action buttons wrap rather
than clipping, while save/use/delete actions remain outside the form scroll.
Resizing retains current unsaved field values. The selected category and saved
profile have visible active states.

## Editor drafts

Machine, cutter and ATC editors preserve unsaved text independently for each
record and for a new record in each category. Switching records/categories or
closing and reopening the library retains those drafts for the current app
session, including invalid quantity expressions. Drafts are not written to disk.
The editor shows the number of changed fields and keeps Revert draft outside the
scrolling form. Revert restores the selected record's saved fields without
changing the stored library or the active workspace.

Save validates and persists the selected draft, then clears that draft. The
explicit Use/Load action saves and loads the selected profile into the workspace.
Saving alone does not load it. Failed validation preserves both the editable
draft and the prior saved library. Unsaved drafts do not survive app restart;
import conflict review and draft transactions for other workspace editors remain
separate work.

## Tool CAD, holders and drawings

Cutter profiles now retain `geometry_path`, `holder_geometry_path`, `drawing_path`,
`source_url` and optional `stickout` (tip to collet face). Overall length remains
catalog length. Explicit stickout controls the rendered length and machine collet
attachment; a holder extends above that face without increasing cutter stickout.
Without stickout, the full cutter is illustrative and marked unknown.

Browse a STEP/STP, STL or OBJ in the cutter/holder field to open CAD registration.
Select its units, axis toward the shank and tip origin (holder: collet face).
Conversion runs in a separate Python interpreter configured by
`carvera.tool_cad_python`. STEP requires `cadquery-ocp` in that interpreter; the
controller runtime does not require it. STEP embedded units are normalized to mm;
STL/OBJ units are explicit. Converted files are stored at `~/.carvera/tool-assets`.
No source CAD executes code or sends machine commands. The same converter can be
run from `scripts/convert_tool_profile.py` with `--units`, `--axis`, `--tip`, and
`--origin tip|collet`.

Converted assets use `carvera-tool-mesh-v1`, mm, +Z toward the shank and explicit
`tip` or `collet` origin. Expanded JSON is limited to 24 MiB and geometry to 65,535
vertices (including attached holder and clipped faces). Invalid geometry reports
an error instead of silently reverting to an approximate shape. Asset metadata
retains original source filename, SHA256 and registration. Library import/export
retains local asset references; copying JSON does not copy referenced files.

Inspect cutter & holder opens an independent orbit/zoom preview with dimensional
readback and links to the manufacturer and local drawing. Raster/PDF/SVG/DXF
files are attached references opened in the system viewer. Loading a cutter or
ATC set uses its geometry for program-number playback, in millimetres independently
of the G-code units. This remains visual rehearsal: no collision engine, stock
subtraction, physical tool identification or measured-offset qualification.

## Stock and workholding transactions

Scene → Origin & stock setup and Vise placement use a shared reviewed editor.
Related dimensions sit in labeled sections; the fields scroll independently of
Apply, Reload current setup, Keep draft & close and Cancel edits. The comparison
shows old and proposed values in canonical millimeters/degrees. Editing or
keeping a draft does not alter geometry or send CNC commands. Cancel discards
that draft; keeping and reopening it retains even invalid expressions for the
current app session. Reload discards the draft and reads the active preview.
A changed machine, component model or preview setup requires reconciliation
before Apply.

Apply updates preview geometry and saves one scene record for the selected
machine ID. Vise edits no longer also rewrite the machine-profile library: those
fields are defaults for new setups; saved per-machine scene geometry takes
precedence. With no selected machine, Apply changes only the local session.
A persistence failure restores prior geometry, stock display, workspace geometry
metadata and view framing, while keeping the editor's fields available. The scene
store's optional `expected` record check refuses a newer saved setup instead of
silently overwriting it. That check is an optimistic comparison before an atomic
file replacement, not a cross-process lock. External changes require loading the
machine's saved setup before rebasing the editor.

Drafts are session-local. Neither draft geometry nor a successful local save is
physical mounting, work-offset calibration or machining qualification.

Opening either editor suspends keyboard jogging and reuses an already open
editor of the same type. If restoring the prior scene also encounters a CAD
redraw error, the numeric setup is restored and the editor reports the unavailable
redraw; it does not claim that the displayed mesh has been qualified.

## Tool comparison and calibration workbench

Setup includes a searchable tool comparison panel, also reachable through
“Compare tools and calibration” in the command palette. It compares local
millimeter library diameters with unit-normalized CAM diameters and highlights
numerical disagreement above 0.001 mm. Selecting a row reveals declared
stickout, the active tool's fresh one-packet reported TLO, and raw repeated
calibration samples, reported spread, applied TLO and UTC timestamps. Only the
most recent ten reports are displayed; existing session history is retained.

Disconnected, stale, future-dated or missing pose packets cannot supply a current
TLO. Nominal overall length, stickout and reported TLO have different references;
this panel does not subtract them or infer wear corrections. Calibration history
is currently session-local and keyed by tool number. It does not identify an
individual physical cutter or establish that a historical result applies to its
replacement. Spread alone does not diagnose wear, damage or seating. Viewing,
filtering and selecting rows neither creates history records nor sends commands.

This is an integrated read-only comparison checkpoint. Persistent machine- and
physical-cutter-bound measurement custody, full comparative geometry/wear offset
tables, reviewed backend writes/readback and physical qualification remain open.

## Persistent physical assemblies and raw calibration receipts

Expand **Physical assemblies & saved receipts** below the Setup tool comparison.
Create a distinct named assembly (inventory tag, optional holder/collet identity,
optional declared stickout and cutter-design reference). Select it to browse its
attributed raw calibration history across application restarts. Creating an
assembly does not load or change the preview tool geometry.

With a saved machine profile and a selected comparison tool number, **Declare at
selected tool** opens a review before saving a local placement assertion. Moving
an assembly supersedes its earlier declared location while retaining all events.
Replacing a slot's assembly does not transfer calibration history.

New completed console calibration reports persist in
`~/.carvera/tool-custody.json`, including raw samples, reported spread, applied TLO
when present, report time, receipt time, and connection address. Unknown reported
tool numbers remain unknown. A report starts unassigned even when a slot has a
declared assembly. **Link a raw receipt** shows the original source and values;
an attribution note is required. Attribution is an operator assertion, not
proof of physical identity, calibration validity, or currently installed offsets.
Previously linked receipts cannot silently be reassigned to another assembly.

The event store validates existing contents, merges on each write under an
exclusive writer lock, writes via atomic replacement, and preserves corrupt
files on failure. Capture errors remain visible in the workbench. Reading or
opening an editor creates no file; Cancel writes no custody event. These actions
send no controller commands. The older session-local tool-number history remains
available separately and is not silently imported as physical-tool history.

Full assembly revision/edit/release workflows, scanned physical identities,
measurement-cycle identity binding, insert-edge custody, geometry/wear offsets,
qualified backend writes/readback and physical qualification remain open.

## DESKTOP210 browser acceptance

Frozen source `0dab677bfc3e8d96e061d6b494c7322e07dd7427` is installed as
DESKTOP210. All 504 packaged source files match, and strict signature verification
passes. Native Profiles remains in the right workbench; the counted saved-machine
and saved-cutter Browse/Hide controls expand and collapse without replacing the
machine or camera panes. Collapsing the browser gives the retained editor more
space. Saved Workshop Carvera was connected explicitly; fresh C1 Idle telemetry
and independent Ubuntu camera updates were observed. DESKTOP209 remains available
as a recovery app.

Receipts are under
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop210-20261006/`:
`built-verification.json`, `artifact-verification.json` and
`native-workflow-receipt.json`. Native compact drawing edits, physical geometry
and registration remain OPEN. Operator stores were not independently rehashed in
this native acceptance run. Later inline recovery and recipe contracts are not
included in DESKTOP210.

## Concentrated embedded library controls

Embedded libraries use a category selector and a Library actions menu for import,
export and closing. Standalone libraries keep their visible category/action
buttons. Save and the current Use/Load action stay visible in one compact row;
More exposes only the currently available Revert draft and Delete profile
operations. Delete retains its existing confirmation and toolset-reference checks.
Changed profiles still say Save & use/load, preserving the distinction between
saving metadata and loading a preview. Category selection updates in both
keyboard-driven and programmatic navigation and retains drafts across categories.

At 360 and 600 dp the embedded category toolbar is 34 dp high and the pinned
editor actions are 36 dp high. The counted Browse/Hide control retains the saved
record browser. Initial new-test failures used an incomplete cutter fixture and
assumed the seeded library would select a newly appended record; the fixtures now
use validated dimensions and explicit record identities. Product validation and
interaction assertions were retained. Rendered compact layouts were inspected.
This follow-up postdates frozen DESKTOP211 and needs a later package/native check.

Final source verification passes 78 combined compact-menu, workbench, draft,
selection, comparison and connection-recovery checks. Category selection is
exercised with keyboard Enter/Down/Enter; import/export routing, available editor
menu actions, retained drafts, store bytes and no-command behavior are checked.
Full locked lint/format/diff and both architecture contracts pass.
