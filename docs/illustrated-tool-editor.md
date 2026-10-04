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
