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

## Configured target overlay and firmware-zero compatibility

The explicit Show configured targets toggle projects up to six targets from the
current page into the machine view. Numbered amber rings follow the displayed
table motion, hide with the ATC component or machine view, and disappear after
connection generation invalidation. Refresh neither queries the controller nor
rebuilds label textures unless the displayed number changes.

Pinned community firmware `feab653def96a959e695049a4f828aeddbcd5547` emits
Tool 0 in the default 0–6 configuration and accepts custom numbers 0–255.
The collector/parser now accepts the full bounded readback range, including zero;
slot-write authorization remains unchanged. The previous parser would reject a
normal default receipt containing Tool 0.

Firmware sources:
https://github.com/Carvera-Community/Carvera_Community_Firmware/blob/feab653def96a959e695049a4f828aeddbcd5547/src/modules/tools/atc/ATCHandler.cpp#L1513
https://github.com/Carvera-Community/Carvera_Community_Firmware/blob/feab653def96a959e695049a4f828aeddbcd5547/src/modules/tools/atc/ATCHandler.cpp#L977
https://github.com/Carvera-Community/Carvera_Community_Firmware/blob/feab653def96a959e695049a4f828aeddbcd5547/src/modules/tools/atc/ATCHandler.cpp#L2808

Pickup/drop scripts use configured XYZ directly in G53 moves. Markers therefore
represent configured axis-reference targets, not measured rack surfaces or cutter
tips. In the existing nominal CAD model, target XYZ plus the current table motion
places the target in the rendered bed frame. At the target's pickup pose, the
mapped point matches the nominal zero-length axis reference. No active cutter
length, work offset, or additional CAD offset is added. This establishes internal
model consistency; physical CAD/rack registration remains unverified.

The engine/profile/capability suite passed 42 tests (1.16 s), including Tool 0,
all 256 supported positions, oversized output rejection and coordinate-frame
consistency. Receipt: /tmp/carvera-atc-target-tests.log.

DESKTOP146's original build session and process are absent, with no completed app.
Exit status is unknown; its log and incomplete output remain preserved. Receipt:
/Volumes/Wes Storage/Archives/Downloads/carvera-desktop146-20261005/interruption-receipt.json.
No installation was attempted.

The first broader UI run passed 30 test bodies but timed out in scene-fixture
teardown, during refresh-triggered full CAD reconstruction. That feedback path
has been corrected separately (see ui-responsiveness.md). The replacement suite
is retained as session 18774 / PID 31003; its current log is
/tmp/carvera-atc-target-ui-final-tests.log. At the last observation it had not
collected tests: Python initialization was blocked reading
external-volume distutils-precedence.pth. The process sample is
/tmp/carvera-atc-final-startup-sample.txt. Final source UI acceptance remains OPEN;
this live run has not been duplicated or treated as terminal.

## Portable configuration receipt workflow

The collector retains the normalized response, its SHA-256, host UTC completion,
connection generation and model/firmware/protocol/address snapshot captured at
query dispatch. Monotonic process timestamps are deliberately omitted from the
portable artifact; loading it never restores freshness or live inventory.

Save receipt uses exclusive .cvatc creation, then validates an independent byte
readback. Review saved receipt runs bounded file I/O away from the event loop,
checks envelope/response digests, exact fields, UTC timestamp, number/coordinate
agreement and configuration-only semantics. Corrupt records leave the previous
historical selection intact. No slot write, calibration, tool change or query is
dispatched by save/review. Historical options are paged six at a time, including
the full 0–255 range, rather than constructing a 256-option dropdown.

Final engine/capability/actual mocked transport suite: 52 passed (0.73 s), including
query-time firmware capture, corruption rejection, exclusive creation and byte
readback. Two narrow/wide UI workflow tests passed (1.42 s), covering export,
reconnect invalidation, historical review, corrupt import and full-range paging.
Both final renders were reviewed. Receipts:

- /tmp/carvera-atc-exchange-complete-engine-tests.log
- /tmp/carvera-atc-historical-ui-pagination-tests.log
- /tmp/carvera-atc-historical-360.png
- /tmp/carvera-atc-historical-650.png

Source checks used an isolated internal Python 3.9 / Kivy 2.3.1 dependency path;
no operator profile/configuration store was changed by these tests. An earlier
independent run lacked pyserial; its setup errors remain in
/tmp/carvera-atc-exchange-dispatch-tests.log. After installing that dependency,
the exact transport checks passed. The broader original scene suite resumed and
reported 27 passes / 5 failures: one graphics-frame timing assertion and four
outer-visibility/framing invariant failures. Those have source corrections, but
full acceptance remains OPEN. The subsequent external-runtime process was
confirmed stalled during compiled Kivy initialization before test execution;
it was deliberately terminated (exit 143) before runtime migration. Receipt:
/tmp/carvera-atc-test-runtime-handoff.json. The first internal full-app attempt
lacked QuickLZ (4 passed / 29 setup errors); its log is preserved at
/tmp/carvera-atc-internal-scene-tests.log. QuickLZ installation remains an owned
live operation, session 93229, log /tmp/carvera-internal-quicklz-build.log.

Native actual readback, overlay/framing verification, installed receipt exchange,
physical rack registration and assembly/occupancy reconciliation remain OPEN.
