# Illustrated stock setup editor

The stock and program-origin editor retains top (XY) and front (XZ) projections
above its scrolling form on large desktops. In short windows the illustration
scrolls with the form so fields remain reachable. Both projections use the same scale. Focusing a stock
dimension highlights its span; editing a valid dimension updates only the draft
drawing. Fractional inch input uses the existing canonical millimeter parser.

The circular marker identifies the stock minimum corner, whose coordinates are
relative to program zero. Program-zero fields instead describe machine coordinates
and are explicitly annotated as not drawn to scale. This is a nominal schematic,
not evidence of physical mounting or calibrated registration.

Invalid drafts suppress the drawing and retain a wrapped error caption. Reload
restores the current setup and drawing. Cancel, retained drafts, Apply, external
save conflicts and rollback retain the existing setup transaction behavior.
Opening, focusing and editing the drawing issue no machine commands.
Untouched dimension fields preserve an unconfigured stock state; editing program
zero alone does not silently introduce the editor's suggested stock dimensions.

This advances the illustrated geometry editor requirement. Direct geometry
picking, a measured transform illustration, illustrated vise editing, installed
native acceptance and physical setup qualification remain open.

Source checkpoint: 14 focused integration checks passed (62.14 seconds), including
dimension focus, imperial drafts, frame captions, invalid suppression, reload,
unconfigured stock preservation, rollback and external-save protection. Large
and 1100 × 850 popup renders were inspected. Ruff lint/format and diff checks
passed. Evidence: `/Users/wes/Downloads/carvera-stock-editor-20261004/`.
DESKTOP101 installed checkpoint, source
`75f69ed1366be82664e3a88192beb77debf6fd32`: native imperial Z input redrew a
6.35 mm thickness, invalid negative input suppressed the drawing, and Reload
restored the original 50.8762 mm thickness. The notice rendered in the normal
native window and Cancel left the active setup unchanged. Operator stores and
configuration were restored exactly after synthetic-preview verification;
manifest and signature receipts are in
`/Users/wes/Downloads/carvera-desktop101-20261004/`. Short native stock-notice
rendering, measured registration and the full interactive geometry workflow
remain open. This checkpoint issued no machining or motion commands.

The next source checkpoint makes all XY/XZ dimension lines selectable. A click
reveals and focuses the corresponding validated X/Y/Z field; selection changes
neither the draft values nor active geometry. Pointer movement cancels a click,
mouse-wheel events remain available to scrolling, and invalid/disposed drawings
offer no selectable geometry. The existing quantity parser and Apply/Reload/Cancel
transaction remain authoritative. This is field selection from an illustration,
not dragging stock geometry or measuring its physical placement. Installed native
acceptance of dimension selection remains open.

Selection source verification: 17 editor checks passed in 68.42 seconds, including
actual window pointer dispatch to stock X/Y/Z fields and the vise rotation arc.
A subsequent gesture check passed in 14.28 seconds after adding drag-cancellation
coverage. Existing invalidity, rollback, external-save, Apply and Cancel checks
passed. Ruff, formatting and both architecture contracts passed. Stock and vise
renders were inspected. Evidence and failed attempts are retained under
`/Users/wes/Downloads/carvera-stock-selection-20261004/` (the first missing-output-
directory log is adjacent as `carvera-stock-selection-20261004-tests.log`).
