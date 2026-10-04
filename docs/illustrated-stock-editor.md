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
This source change has not been packaged or installed; DESKTOP100 remains a
separate prior artifact.
