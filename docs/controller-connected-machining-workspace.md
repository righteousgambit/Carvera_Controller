# Connected machining workspace extensions

These 25 requirements extend the existing acceptance ledgers and remain part of
the full implementation objective. Source engines, native workflows, backend
execution and physical qualification require separate evidence. None is closed
by this requirements checkpoint.

| # | Requirement | Required end state |
|---|---|---|
| 1 | Machine capability map | Available/configuration-needed/simulation-only/unsupported states with observed identity, prerequisites and supported alternatives |
| 2 | Setup conflict resolver | Geometry-linked conflicts and alternative remedies with reach, clearance and setup consequences previewed |
| 3 | Illustrated parameter sheet | Selected physical entity has dimensioned editable illustration, compact common fields and expandable uncommon fields |
| 4 | Multiple-part setup matrix | Part rows link WCS, stock, fixture, tool, program and inspection identities to scene selection |
| 5 | Change-driven invalidation | Changes identify affected operations and stale simulation/measurement/setup evidence with explained refresh actions |
| 6 | Alternative setup branches | Independent setups compare reach, clearance, timing, exchange and unresolved assumptions without overwriting active setup |
| 7 | Spatial setup checklist | Instructions identify physical scene targets and registered camera regions with measured versus estimated association |
| 8 | Unified transaction preview | Grouped changes show exact effects, supported rollback, per-step receipts and recoverable partial completion |
| 9 | Feature-centered workbench | Feature inspector joins nominal geometry, operations, assemblies, allowance, thread, measurements and tolerance |
| 10 | Operator/expert detail control | Shared state supports practical next actions and expanded frames/modal/ack/process detail, retained per task |
| 11 | Controller configuration import | Supported backend import derives axes/limits/spindle/ATC/I/O with facts, assumptions, conflicts and preferences distinguished |
| 12 | Machine-sequence debugger | Physical sequence steps animate and expose expected feedback, deadlines, actual transitions and stalled prerequisites |
| 13 | Complete machine interference | Moving machine structures and assemblies participate in checking with first contacting bodies and understandable scene views |
| 14 | Cable/hose/winding limits | Routing-dependent rotary restrictions and accumulated winding support clearance-reviewed unwind candidates |
| 15 | Advanced cutter contact | Taper/barrel/lens/lollipop/form cutter contact regions and effective radii are evaluated along supported paths |
| 16 | Five-axis solution chooser | Alternative configurations compare margin, singularity proximity, rotary travel, collision candidates and continuity |
| 17 | Setup tolerance allocation | Evidence-bound error contributions explain feature feasibility and valuable additional measurements |
| 18 | Measured stock assimilation | Probe/scan stock preserves measured/interpolated regions and supports material-envelope roughing with uncertainty |
| 19 | Interruption material planner | Execution-linked removal history, uncertainty and entry conditions inform reviewed restart candidates |
| 20 | Engagement forecast | Remaining stock and tool geometry predict upcoming engagement and bounded feed proposals within established process envelopes |
| 21 | Adaptive commissioning | Actual cadence/filter/ack/feed-response characterization and bounded physical trials qualify capable local execution |
| 22 | Frequency process diagnostics | Suitable higher-rate sensors associate vibration, spindle/tooth frequency, location and observed finish outcomes |
| 23 | Fixture deformation/release | Measured or modeled clamping effects inform support, operation order and inspection before/after release |
| 24 | Feature process qualification | Reusable program/setup/assembly/result packages declare accepted ranges, limitations and differences in new jobs |
| 25 | Production improvement dashboard | Observed time categories and quality outcomes link intervals to operations and evidence-based improvement comparisons |

Immediate Carvera priorities: 2, 7, 9, 18 and 20. Broader backend priorities:
11, 12, 16 and 21. Priority ordering does not reduce the full objective.

## Capability inspector source checkpoint

The Machine workbench now presents twelve capability explanations with retained
selection, related-workbench navigation, explicit physical prerequisites and
alternatives. Firmware and model observations are captured at receive parsing,
not inferred from saved profiles or delayed UI logs. Valid pose packets refresh
status evidence; C fields refresh the ATC hardware flag. A new connection clears
prior observations even if opening the replacement transport fails. Disconnected,
stale, reversed-time, missing and unrecognized identity observations cannot
produce a protocol-available state. Recognized firmware produces published
protocol inference, explicitly distinct from physical qualification; TCP remains
simulation-only and tapping explains the unsupported Carvera adapter plus a
thread-milling alternative. No controller command is dispatched by inspection
or navigation.

This advances requirement 1. Actual feature discovery, general backend adapters,
all advanced capability coverage, application/execution readiness and native
installed acceptance remain separate work. The inspector does not replace the
existing command guards or authorize a physical operation.

DESKTOP83 checkpoint: source `b6ecd363bcf396a73f16e917286ab1aed890fdce`;
72 focused tests passed, full suite 1,301 passed / 15 skipped / 7 warnings
(394.42s). All 424 staged/built/installed files match and all bundle/recovery
signatures pass; six operator stores remain unchanged. Native identity reads
C1 / 2.1.0c / session 1, keyboard selection works and tapping prerequisites and
thread-milling alternative render. Native review exposed a clipped final evidence
line for live-position support. The partial receipt is preserved at
`/Users/wes/Downloads/carvera-desktop83-20261004/native-receipt.json`.
The fixed-height label helper constrained multiline texture measurement. A repair
uses unbounded-height text measurement and tests that height stays unconstrained
across selection and resizing; eight focused repair tests pass. Its source
intentionally differs from DESKTOP83. Rebuilt/native repair acceptance remains
open; DESKTOP83 does not close the complete layout gate.

DESKTOP84 repair acceptance: application source
`6da4095251a63e43d5a1aca7dfdaa58c5613342c`; full suite 1,301 passed / 15 skipped /
7 warnings (593.14s). Eight focused repair tests pass. The UI test fake clock is
subsequently scoped to its module rather than the shared time module in
`d235ae8f1e0ffd14bfae31b186a3b25e3784045a`; two isolated-clock tests pass, and
packaged application files are unchanged. All 424 stage/built/installed files and
421 comparable checkout files match; strict built/installed/recovery signatures
pass and six operator stores are unchanged. Native live-position evidence is
fully visible, keyboard selection works, tapping limitations/alternatives render,
Open Setup navigates correctly, selection survives returning, and TCP explicitly
shows Simulation only. Both imagery panes remain visible. Final connected/Idle,
fresh camera/telemetry, T1/TLO 50.480 mm were observed. Configuration download
matched advertised MD5 (8,192 bytes); status reacquired in 0.324s. No machining,
probing, exchange or offset writes occurred. Receipt:
`/Users/wes/Downloads/carvera-desktop84-20261004/native-receipt.json`.
This closes the installed Carvera capability-inspector interaction checkpoint,
including the clipping repair. General backend discovery, complete capability
coverage, execution readiness and physical qualification remain open. A caught
startup NoOptionError for missing optional mdi_history is retained as a separate
ergonomics issue; it does not establish a connection or inspector failure.

## Setup remedy comparison source checkpoint

The clearance inspector now embeds a local comparison draft for loaded alternate
cutter geometry or a selected obstacle-bounds translation. Both alternatives are
simulated against independent copies of the same captured starting stock and
path. Results distinguish the selected contact, removed and newly introduced
contact locations, and calculated material-removal differences. Cutter shape,
diameter, exposed length, unknown holders and unqualified registration remain
explicit. Moving an obstacle box does not move stock, validate grip, or establish
physical mounting feasibility. The active setup and controller are never changed.

Changed program/setup inputs, editable drafts, alternative tool definitions and
same-path CAD byte replacements reject stale comparisons. Calculations are
cancellable and bounded to 20,000 captured segments; dismissal invalidates pending
callbacks. Compact responsive forms retain numerical interpretation space and
results use unconstrained-height wrapped text inside the existing inspector scroll.

Eighteen focused source/application-event-loop tests pass, including real worker
completion, stock nonmutation, newly introduced contacts and stale-input refusal.
Both import architecture contracts pass. This advances requirement 2; native
installed interaction, whole-machine registered geometry, alternative setup
application and physical qualification remain open.

## Setup comparison interaction repair

The native DESKTOP85 observation exposed pointer selection failure, raw integer
validation text and a missing arrow glyph. A real Kivy Window touch regression
reproduces the selector failure: ScrollView delays option release until after
focus cleanup, which used to dismiss the menu prematurely. DesktopDropDown now
preserves the owning selector's focus for inside-menu touches; outside dismissal
and keyboard cancellation remain intact. Missing remedy selections now explain
which input to choose, and comparison ranges use readable text.

Removed and new contact locations now provide direct local-preview navigation
actions. They seek the original captured motion, without applying alternative
geometry, changing stock or issuing machine commands. Changed setup, draft,
alternative definition or actual CAD bytes invalidate navigation. The next
comparison clears prior actions before starting.

Thirty-five focused event-loop and engine tests pass (18.63 seconds), including
the formerly failing pointer route, outside dismissal, keyboard traversal,
friendly missing-input refusal, changed-contact navigation and stale setup
refusal. Both architecture contracts pass. This is source verification; installed
DESKTOP86 interaction and physical qualification require separate evidence.
