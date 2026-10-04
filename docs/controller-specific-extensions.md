# Specific interface and advanced-machine extensions

These 25 requirements extend the previous controller ledgers. They preserve the
full implementation objective. A source foundation, installed interaction,
backend execution and physical qualification remain separate gates.

| # | Workflow | Required end state |
|---|---|---|
| 1 | Consistent components | Shared dimension/unit/selector/table/validation/action controls with native spacing, focus and transaction verification |
| 2 | Tab state retention | Selection, scroll, expansion and unfinished inputs survive tab changes without changing active machine values |
| 3 | Secondary contextual inspector | Related assembly/measurement/source inspected beside the main task without replacing its editor |
| 4 | Selective setup propagation | Reviewed field-level propagation across physical instances preserving unselected individual properties |
| 5 | Scene label management | Nonoverlapping hole/tool/dimension/problem labels with semantic zoom and hover selection |
| 6 | Assembly focus treatments | Temporary isolation/transparency of related geometry and exact previous-view restoration |
| 7 | Registered camera magnifier | Scene feature-linked enlarged image region with calibration accuracy and frame age |
| 8 | Live-change highlighting | Changed values expose previous value, timestamp and observed source without excessive notifications |
| 9 | End-to-end keyboard workflows | Predictable operation/tool/source/return navigation with visible focus and tested shortcuts |
| 10 | Calculation performance controls | Phase timings, cancellable reusable partial results and independent rendering/calculation detail |
| 11 | Spindle-ready verification | Actual RPM/settling/available at-speed feedback gates capable-backend cutting entry |
| 12 | Telemetry quality | Sampling/transport delay/gaps/quantization/filtering visible before adaptive use |
| 13 | Cutting-time accounting | Observed cutting/air/dwell/probe/exchange/interruption time distinguished from spindle time |
| 14 | Measurement repeatability studies | Repeat measurements across seating/direction/operator/thermal conditions and variation analysis |
| 15 | Batch feature trends | Part-indexed dimensions/inspection linked to actual assembly usage and measured temperature |
| 16 | Correction applicability | Feature-dependent correction candidates with predicted effects on other features and qualified supported application |
| 17 | Tool-life forecast | Applicable inspected histories produce remaining-life estimates with uncertainty and changed-condition explanation |
| 18 | Fixture seating checks | Accessible reference-point comparison detects translation/tilt/seating disagreement against measured fixture frame |
| 19 | Sacrificial engagement entry | Reviewed accessible test region, conservative parameters and actual response review before extension |
| 20 | Part-completion record | Exact program/setup/actual assembly/interruption/inspection identities assembled per produced part |
| 21 | Random/multiple magazines | Actual tool/pocket/station inventory transitions, reservations and loading rules with exchange readback |
| 22 | Tool clamp condition | Available drawbar/pressure/clamp/release/seating measurements bound to actual assembly history |
| 23 | Pressure/flow resource model | Required/observed supply and recovery across clamps/air/lubrication/coolant with explained concurrency constraints |
| 24 | Bar-fed turning | Actual remaining bar/feed/chuck/cutoff/remnant/catcher state and stage-bound interruption recovery |
| 25 | Specialized synchronization | Polygon turning/broaching/chip-breaking geometry, phase/demand/result preview and qualified local capable-backend execution |

## Post-transfer status checkpoint

Polling resumes with an immediate status request and a bounded five-second
receive window. File bytes and command acknowledgments never refresh the actual
pose timestamp. During this handoff, motion/configuration commands and realtime
resume/keepalive are blocked; explicit queries, feed hold and STOP remain
available. Expiry does not establish readiness and the normal receive watchdog
can disconnect a silent link. This is part of telemetry-quality and operator
state work, not completion of the broader capabilities above.

## Shared keyboard and editor interaction checkpoint

Shared desktop fields, actions and selectors now traverse enabled controls in
the displayed screen or modal scope. Focus has a visible outline and scrolls an
editor into view; leaving a workbench section clears its focused controls while
retaining scroll position and unfinished input. Editable fields restore their
focus-entry text on Escape. Numeric validation survives focus/size repaints.
Selectors support highlighted arrow-key candidates, explicit Enter selection,
Escape cancellation with selector focus retained, and Tab departure. Menus close
synchronously so rapid cancel/reopen does not race delayed dismissal. Repeated
activation keydown does not repeat the action until keyup. Jog buttons retain
explicit pointer/pendant/jog controls rather than Enter activation, and focusing
shared controls disables keyboard jogging; dispatch rechecks workbench focus.

This advances requirements 1, 2 and 9. It does not complete all editor transaction,
accessibility, keyboard workflow or component migration requirements. Actual
machine commands are not part of keyboard/editor qualification.

Dismissed/detached controls are excluded as well: retained action focus cannot
activate a closed dialog, and hidden text-input targets reject keyboard text.
The first DESKTOP79 build remains uninstalled because its source preceded this
additional regression fix; DESKTOP80 includes the complete checkpoint.

DESKTOP80 passed 1,280 tests (15 skipped, 7 warnings), signature and manifest
checks and installed connected/Idle readback. Native profile-name editing and
Escape restoration passed, as did Tab-to-selector and unapplied arrow candidates.
Native selector cancellation exposed a Window-level DropDown Escape handler that
closed the menu before the selector could consume keyup, losing focus. Its failed
native acceptance is preserved in the DESKTOP80 receipt. The repair routes that
Window cancellation through the selector's keyup guard. A Window-dispatched
regression now covers cancellation, retained focus and immediate reopening;
19 focused editor/playback tests passed. DESKTOP81 packaging and native acceptance
are separate gates until their receipts establish them.

DESKTOP81 acceptance checkpoint: implementation source
`325ef5cae03a8a7122fe24e6fcd5a4b89902b88b`; full suite 1,281 passed, 15 skipped,
7 warnings (484.32s). All 420 stage/built/installed files match the manifest;
417 comparable checkout files match; built/installed/recovery signatures pass.
Native Tab, arrow candidate, Escape cancellation with retained selector focus,
immediate reopening, explicit Enter draft selection and restoration passed.
Name Escape restores the entry without closing the dialog. Invalid numeric units
retain red validation while focused; Escape restores the valid port. All six
operator stores match their baseline. Connected/Idle, fresh camera and telemetry,
T1/TLO 50.480 mm were observed; configuration download reacquired status in
0.307 seconds. No machining, probing, exchange, offset writes or profile Save/Apply
were performed. Receipt:
`/Users/wes/Downloads/carvera-desktop81-20261004/native-receipt.json`.
This closes the shared-editor native checkpoint only; full component migration,
accessibility, end-to-end workflows, backend execution and physical qualification
remain open under the original full objective.

## Telemetry-quality source checkpoint

The Spindle workbench now combines compact RPM/droop/proposal metrics with a
responsive signal-quality inspector. Its bounded 300-arrival window records
complete/incomplete/invalid spindle packets, actual monotonic arrival intervals,
mean/p95/maximum intervals, gaps and rejected timestamps. Missing S/F/MPos never
refresh the last complete spindle sample. Incomplete-packet diagnostic events
are retained in the existing JSONL log; a local export captures the window,
shadow samples, connection generation, endpoint, UTC export time and timing
limitations, then reads the written file back. Charts break across stale or
reversed-time observations instead of drawing uninterrupted signal history.

Desktop arrival age/cadence and the 400 ms droop-filter constant are observed or
defined here. Firmware sampling age, one-way transport delay, actual sensor
resolution and feed-command response latency remain unknown. The smallest
observed RPM change is labeled as an observation, not sensor quantization.
Estimated unobserved poll slots are not a packet-loss count. No active adaptive
control, spindle-ready interlock or qualified machine-side loop is added.
Packaging, native interaction and physical adaptive qualification remain
separate gates until their corresponding receipts establish them.
