# Illustrated workholding placement

The local vise placement editor projects the loaded workholding CAD component
envelopes into XY and XZ views. It retains fixed/movable component roles and the
source CAD pivot. Placement and the machine scene share one point transform:
movable components shift along source CAD Y before rotation about pivot Z, then
the complete assembly translates. The projected coordinates are relative to the
source pivot, not a measured machine datum.

Focusing translation highlights its projected axis spans. Rotation highlights an
arc about the placed pivot. Jaw shift highlights movable envelopes, their zero
shift outlines and displacement. The caption explains that jaw shift is not a
measured clamping gap. Bounds represent component envelopes, not exact outlines
or qualified collision clearance.

Draft edits update only the illustration. Invalid values suppress it and retain
an error caption. Reload restores the current setup; Cancel, Keep draft, Apply
and saved-scene conflict behavior retain the existing transaction. Short windows
scroll the illustration and change summary with the form; large desktops keep
them pinned. Wrapped notices and a compact action row preserve room for complete
quantity fields and conversion feedback. If no
workholding CAD is available, the editor explains how to select a model rather
than inventing geometry.

This extends the illustrated geometry editor requirement. Full CAD face picking,
interactive dragging/snapping, measured mounting registration, installed native
acceptance and physical workholding qualification remain open.

Source checkpoint: 32 setup-editor and CAD-profile checks passed (63.73 seconds).
They cover source/rendered envelope agreement at four rotations, jaw direction
after rotation, invalidity/reload, missing CAD and existing setup transactions.
Ruff lint/format, diff checks and both import architecture contracts passed.
Large and short-window renders were inspected; the latter required moving the
summary into the form to expose complete quantity feedback. Evidence and retained
failed attempts: `/Users/wes/Downloads/carvera-vise-editor-20261004/`.
Installed rendering remains a separate acceptance gate, including the short
stock dialog's notice rendering. No machine command or physical mounting
measurement was performed.
