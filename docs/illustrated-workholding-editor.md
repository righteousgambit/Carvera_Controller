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

DESKTOP101 native checkpoint: installed from
`75f69ed1366be82664e3a88192beb77debf6fd32`. Rotation and imperial jaw drafts,
invalidity suppression, Reload and Cancel were exercised against the loaded
Saunders/Gen3 CAD. A 1504 x 1204 physical-pixel window retained wrapped notices,
action buttons and scrollable fields with complete conversion feedback. Stock
imperial/invalid/reload interactions and the compact invalid cutter card were
also exercised. Seven operator-store identities and the original Kivy config
were restored exactly; 430 source and 433 staged/built/installed manifest entries
matched, and built/installed/DESKTOP100 recovery signatures passed. The restored
runtime showed Idle, fresh reported pose/telemetry, T1/TLO 50.480 mm, zero RPM/feed
and live camera. Evidence: `/Users/wes/Downloads/carvera-desktop101-20261004/native-receipt.json`.

Native review found that the jaw-zero reference appeared solid: Kivy defaults its
dash gap to zero. The follow-up source explicitly sets the gap alongside dash
length; its installed acceptance remains open until a newer package is exercised.
The follow-up's 16 setup-editor checks passed in 73.00 seconds, and the exported
jaw draft visibly showed separated reference dashes. Ruff and both architecture
contracts passed. Source render evidence is retained under
`/Users/wes/Downloads/carvera-vise-editor-20261004/dashed-reference-tests/`.
Short native stock-notice acceptance, interactive geometry editing, measured
registration and physical workflows remain open. No draft was applied to the
operator setup and no machining or motion command was issued in this checkpoint.

The next source checkpoint also makes translation lines, the rotation arc and
movable-jaw displacement markers selectable. Their event routes to the existing
validated placement fields and reveals the selected field in the form. References
remain visible while other fields are selected; highlighting follows selection.
No click applies a draft or issues a machine command. Invalid CAD drafts suppress
selection along with their drawing. Native installed selection acceptance remains
open, as do geometric dragging/snapping and measured mounting registration.

DESKTOP102 installed checkpoint from `246f12d`: short-window native rotation,
jaw-shift and Y-translation references selected and revealed their fields.
The jaw-zero envelope visibly rendered separated dashes. Drafts were canceled;
operator stores/configuration and package signatures were verified before normal
relaunch. Receipt: `/Users/wes/Downloads/carvera-desktop102-20261004/native-receipt.json`.
Zero-valued reference overlap remained a source-inferred interaction gap, so this
does not close every possible placement selection.

The following source adds explicit X/Y/Z, Rotation and Jaw shift selectors within
the drawing. They retain the same field-selection event and leave values unchanged,
providing an unambiguous route when lines have zero length or overlap. Invalid or
disposed drawings disable these selectors and reject pointer input. Installed
acceptance of this refinement remains open.

Zero-reference source verification: 17 setup-editor integration checks passed
in 78.44 seconds; the final hidden/invalid pointer guard passed its focused
interaction check in 15.50 seconds. Actual pointer gestures exercised all five
selectors at zero placement without changing the draft or active setup. The
exported zero-reference drawing was visually reviewed with separated selectors
and the selected Jaw shift field. Installed acceptance of these selectors remains
open; DESKTOP102 is the earlier `246f12d` source.

DESKTOP103 native zero-reference checkpoint: X/Y/Z, Rotation and Jaw shift
selectors each selected and focused their fields with every placement value
set to zero in a disconnected draft. The draft was canceled without Apply or
Keep, and operator data restored exactly. This closes the exercised zero-value
selector interaction gap, not measured placement, dragging/snapping, collision
qualification or physical execution. Receipt:
`/Users/wes/Downloads/carvera-desktop103-20261004/native-receipt.json`.
