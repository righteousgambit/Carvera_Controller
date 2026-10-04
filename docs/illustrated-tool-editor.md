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
