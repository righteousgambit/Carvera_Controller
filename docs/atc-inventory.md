# Configured ATC pocket review

Setup > Review ATC pockets opens a lazily constructed pocket panel. Reading
coordinates is an explicit gesture; opening, paging, selecting and routine refresh
never dispatch a command. Six tiles are shown at once. Selecting one opens the
existing tool comparison for that controller number. Local profile names remain
labeled declarations; occupancy and installed physical cutter identity are unknown.

The controller rechecks a connected, unpaused receive path, fresh Idle pose, observed
ATC flag and recognized custom-slot firmware capability immediately before sending
exactly M889. The generic send method now returns True on successful transport send
and False on transport failure; this is not an acknowledgement or physical result.
No slot write, calibration or tool-change action is included.

The connection-scoped collector requires the exact configuration header, bounded
Tool rows and an ending ok. Pre-header acknowledgements cannot complete the request.
Repeated headers, interleaved non-status output, errors, malformed/duplicate/empty
slots and oversized output reject the reply. A five-second timeout is enforced on
receive, refresh and the next request. Reconnect invalidates prior receipt state.
The response hash covers normalized header/Tool lines, not raw wire bytes. This
uses the recognized firmware's ordered textual command response; it is not a
transport-wide transaction ID or arbitrary-backend acknowledgement mechanism.

Coordinates are a configuration readback, not measured geometry, verified reach,
pocket contents or physical tool attribution. Disconnected, stale-pose and aged
receipts are labeled historical. Unknown coordinates remain unknown even when a
local tool profile exists. Ordinary age refreshes do not rebuild the tile controls.
Query rejection remains visible until another read gesture.

Source verification: 36 engine/capability/receive tests passed; six pocket/capability
UI tests passed. After render review, compact tiles and retained-query-error checks,
the final broader workspace/receive/navigation/pocket suite passed 48 tests
(60.89 s). Narrow/wide panel renders were reviewed after waiting for layout;
initial pre-layout exports are not visual acceptance. Both architecture contracts,
Ruff lint/format and diff checks passed. Receipts:

- /tmp/carvera-slot-inventory-tests.log
- /tmp/carvera-slot-inventory-ui-tests.log
- /tmp/carvera-slot-inventory-workspace-final-tests.log
- /tmp/carvera-slot-inventory-final-imports.log

The first broader suite failed a stale cutter-dimension test that substituted a
requested cutter for displayed geometry. Its fixture now establishes the displayed
tool explicitly; separate pending-identity tests retain that distinction. Failure
receipt: /tmp/carvera-slot-inventory-workspace-tests.log.

Installed/native actual M889 readback, slot overlays, retained receipt exchange and
physical assembly/pocket reconciliation remain open. DESKTOP145 predates this work.
No connected-machine command was issued during source testing.
