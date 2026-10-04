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
