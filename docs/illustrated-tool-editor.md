# Illustrated cutter drafts

The profile library keeps a compact nominal cutter drawing above the scrollable
form. Focusing overall length, flute length or stickout highlights its axial
span. Cutting and shank diameter fields highlight their transverse dimension.
Corner radius and thread pitch highlight the cutting region; they do not claim
an exact manufacturer radius or tooth drawing.

Valid quantity edits redraw the schematic with canonical millimeters. The draft
remains separate from saved profiles, the active workspace, physical tools and
measured offsets. Revert restores the saved geometry. Invalid expressions or
incompatible geometry suppress the draft drawing and expose the validation error,
so a stale valid silhouette cannot masquerade as the invalid edit. Switching to
another profile disposes the previous drawing; switching to machine/toolset
editing removes the drawing card.

The schematic uses the existing procedural cutter profile. Unspecified geometry
can use display envelopes; this is not manufacturer CAD or measured seating.
Imported CAD remains inspectable through the separate cutter/holder preview.
This checkpoint does not yet provide editable CAD dimensions, reverse picking,
stock/vise illustrated editors or qualified physical tool geometry.

Source verification on October 4, 2026: 43 profile-draft, dimension and profile
validation tests passed in 14.63 seconds. Checks include imperial input conversion,
focus highlighting, incompatible stickout rejection, saved/active state isolation,
Revert and a 1100×850 layout with drawing and actions retained. Wide and narrow
rendered source UI were inspected. One existing locale deprecation warning remains.
Logs and renders are in `/Users/wes/Downloads/carvera-illustrated-editor-20261004/`.
Packaging and installed native interaction remain separate acceptance gates.

## Installed DESKTOP100 checkpoint

DESKTOP100 from `dc4d072768dbd35c8b4294194e383d6ec857deae` passed native
overall-focus highlighting, 1.5 in / 38.1 mm stickout redraw, incompatible
100 mm stickout suppression, Revert to 30 mm and machine-editor schematic
removal on October 4, 2026. No profile Save/Apply, upload, run or motion was issued.
Operator configuration and stores were restored exactly before relaunch; the
controller then reported Idle, T1, TLO 50.480 mm, zero spindle/feed, fresh pose
and camera. Manifest and strict signature checks passed for source, stage,
build/install and retained DESKTOP99 recovery. Native receipt:
`/Users/wes/Downloads/carvera-desktop100-20261004/native-receipt.json`.

Native review exposed excess blank space on invalid geometry and an unsaved
caption after Revert. The subsequent source refinement contracts invalid
geometry to a compact message card and names saved/unsaved nominal geometry
from actual editor baseline comparison. Three focused profile integration
checks passed in 12.18 seconds, including compact invalidity and restored card
height/caption. Package/native acceptance of this refinement remains open.

## Illustrated selection source checkpoint

The cutter-library schematic exposes Overall, Cutting, Stickout, Diameter and
Shank selectors. Selecting one highlights the nominal dimension, focuses its
quantity editor and reveals the complete field after caption/layout updates.
Selection does not change field values, save a profile, load a cutter or issue
commands. Standalone dimensioned previews use the same selectors to highlight
dimensions without an editor. Disposed drawings disable their selectors.

The schema remains nominal: manufacturer CAD, measured seating, actual tool
length and physical ATC inventory require their own evidence. Radius and thread
pitch remain available through the numeric editors and cutting-region highlight;
they do not yet have dedicated illustrated selection controls.

Source validation: four profile-transaction/illustrated-editor/standalone-preview
checks passed in 14.22 seconds. Actual Window pointer gestures exercised every
selector and checked focused-field viewport containment, unchanged draft values,
unchanged saved profile bytes and no tool-application call. The smaller-window
render was visually inspected. Ruff and both architecture contracts passed.
Failed reveal attempts are retained alongside the passing evidence at
`/Users/wes/Downloads/carvera-stock-selection-20261004/`.

Installed native interaction acceptance remains OPEN. DESKTOP102 contains the
previous source revision; the next build must qualify these new selectors.

## Installed DESKTOP103 selection checkpoint

DESKTOP103 built from `1524e1c782861b6b1bd39b18dfb8177afbddd212` passed
full-size native selection of all five cutter dimensions. Actual keyboard input
in the selected Stickout field interpreted `1.5 in` as 38.1 mm, updated the
schematic and marked an unsaved draft; Revert restored saved 30 mm geometry.
No Save or Load cutter preview action was performed.

The 1504×1204 physical-pixel native window failed compact layout acceptance:
pinned editor chrome and the drawing overflowed the remaining form space and
overlapped compact library controls. This failure is retained in
`/Users/wes/Downloads/carvera-desktop103-20261004/native-receipt.json` and
`native-cutter-short-layout-failed.png`. A newer source repair moves heading,
explanation and schematic into the scrollable form when vertical space is short.
Its source verification and installed acceptance are recorded separately.

Operator stores and configuration were restored exactly before normal relaunch.
Source/stage/built/installed manifests and built/installed/recovery signatures
passed. Restored runtime showed Idle, fresh reported pose/telemetry, reported
T1/TLO 50.480 mm, zero RPM/feed and live camera. Physical tooling, probing,
machining and complete advanced workflows remain unqualified.

Compact-library source repair: the editor heading, explanation and drawing move
into the form when the library body is below 550 logical pixels high. The
library reacts to height as well as width changes. Profile switches detach and
reattach this chrome explicitly, preserving it across form rebuilds. Three
profile integration checks passed in 17.13 seconds, including actual selectors
at 750×600 logical pixels, focused-field viewport containment, retained draft
values, machine/cutter switching and visible actions. The exported compact form
was visually inspected without the native overlap. Ruff and both architecture
contracts passed. DESKTOP103 does not contain this repair; installed acceptance
remains open until the next package is exercised.

DESKTOP104 installed acceptance: built from
`2bfa7309cd77baac61a028e3e1971ce4191ec7dd`. All 430 repository files and
433 staged/built/installed files matched their manifest; strict signatures
passed for built, installed and preserved DESKTOP103 recovery bundles.
At 1504×1204 native pixels, library controls and actions did not overlap.
The editor chrome scrolled, Stickout selection revealed/focused its field,
`1.5 in` resolved to `38.1 mm`, Revert discarded the draft, and machine-profile
network fields remained reachable after switching tabs. Other compact selectors
remain source-tested and previously exercised natively at wide size; they were
not all repeated in this compact native check. Seven operator stores and config
matched the fresh backup before normal relaunch. Restored app showed connected
Idle, fresh live pose/telemetry, T1/TLO 50.480 mm, zero RPM/feed and live camera.
Receipt and screenshots: `/Users/wes/Downloads/carvera-desktop104-20261004/`.
No save/load/apply/upload/run/motion was performed in this qualification.
