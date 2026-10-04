# Illustrated cutter selection

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
