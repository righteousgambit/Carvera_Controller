# Coordinate dependency review

The Scene coordinate inspector presents selectable calculation dependencies. It
keeps configured preview calculations, unregistered fixture references and a
controller packet snapshot in separate groups. Selecting a row shows its source,
relationship and parent; unresolved points remain explicit. This advances the
coordinate-frame inspector workflow without asserting measured registration.

Review-point and provenance sections collapse to leave space for the tree. Point
fields accept supported length units and invalidate the displayed snapshot as
soon as text changes. Refresh rereads setup and telemetry and retains selection
when the dependency still exists. Errors clear the tree and capture provenance.
The scrollable inspector wraps rows at narrow widths and keeps footer actions
accessible. Selecting a row scrolls its explanation into view.

The inspector is read-only: it does not change profiles, offsets or controller
state. Tool length remains packet metadata and is not added to position again.
CAD placement is not physical registration. Rotary/tool transform editing,
qualified mounting datums, compensation application and the broader overhaul
remain open.

Validation: model tests cover parent relationships, grouping, unresolved sources,
duplicate/dependency rejection and existing coordinate calculations. Integration
tests cover imperial input, immediate invalidation, retained selection, narrow
layout, explanation navigation and absence of controller writes. Package and
installed verification require separate receipts.

Installed DESKTOP260 review found a popup dismissal regression: a tuple returned
from cleanup was truthy and canceled Kivy dismissal. The correction uses a cleanup
function returning None. A Close-action integration regression asserts actual
window removal and focus release; the failed native and test evidence is retained.
