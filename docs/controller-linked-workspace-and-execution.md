# Linked workspace and executable-machine extensions

These 25 additional requested improvements extend the existing acceptance ledgers. Recording a requirement does not establish implementation or acceptance. Current UI, packaged behavior, transport execution and physical qualification remain separate gates.

| # | Requirement | Required end state |
|---|---|---|
| 1 | Linked entity selection | Selection identity follows scene, source, workbench and measurement views without implicit machine motion |
| 2 | Pinnable instruments | Compact operator-selected telemetry, offsets, dimensions and clearance instruments remain readable at supported window sizes |
| 3 | Assembly browser | Searchable dimensioned cutter, holder, collet and fixture previews expose mounting and reach |
| 4 | Setup transaction tray | Related drafts show combined impact and separate local persistence from actual machine writes |
| 5 | Persistent feature identities | Revision matching preserves feature-linked measurements and annotations with explicit unresolved matches |
| 6 | Physical-cause issue grouping | Equivalent clearance causes aggregate affected motions without losing individual contact evidence |
| 7 | Precise direct manipulation | Scene gestures expose exact dimensions, frame, constraints and undo |
| 8 | Machining comparison workspace | Matched viewpoints and timeline compare clearance, reach, remaining stock, exchanges and timing |
| 9 | Generated preparation instructions | Setup-bound illustrated mounting, jaw, stock, assembly and pocket instructions refresh on change |
| 10 | Preparation/running layouts | Editing and execution layouts retain context and provide deliberately different information density |
| 11 | Executable two-bank workflow | Bank boundary preparation, physical reconciliation, calibration and supported resume execute as one workflow |
| 12 | Tool-setting geometry reconciliation | Measured lengths and declared assembly geometry explain differences and affected operations |
| 13 | Time by cause | Observed and predicted cutting, air, ramp, probing, exchange and operator time remain distinct |
| 14 | Adaptive observability bench | Engagement, RPM, sample gaps, filtering, override requests and observed response align in time |
| 15 | Physical-region adaptive policy | Operation regions carry explained, bounded control policies with supported execution |
| 16 | Probe-fit setup transaction | Multi-point fits expose residuals and preview supported datum/rotation changes before application |
| 17 | Risk-linked inspection | Feature requirements and changed process/setup dependencies identify reinspection needs |
| 18 | Machine motion fidelity | Acceleration, rotary limits, spindle ramps and blending distinguish nominal and predicted motion |
| 19 | Configuration-aware reachability | Orientations, joint alternatives, singularities and assembly clearance cover operation entry and exit |
| 20 | Compensation-stack inspector | Work/local/tool/cutter/rotary/TCP transforms explain their combined effect on selected motion |
| 21 | Executable advanced backend | Actual transport, state, acknowledgement and completion extend current offline declarations |
| 22 | Visible spindle synchronization | Actual encoder/index readiness, pitch and motion relationship support qualified synchronized workflows |
| 23 | Multi-system resource scheduling | Spindles, turrets, magazines, pallets and shared zones show overlap and blocking resources |
| 24 | Pocket-independent tool identity | Physical assemblies retain identity, offsets and history through pocket, spindle and sister-tool changes |
| 25 | Executable profile acceptance | Repeatable actual-interface tests record communication, homing, tools, probing, offsets, sync and recovery evidence |

## Clearance cause browser source checkpoint

The material-removal contact browser defaults to grouped causes, with an
individual-contact view retained. Groups require matching operation boundaries,
tool identities and exact captured method, obstacle bounds and body sections.
Missing capture, tool or operation identities remain separate. A source motion
with different captured geometries can appear in multiple groups; no contact
evidence is deleted by grouping.

Expandable groups retain all source motions with separate bounded pagination.
Search covers tool, operation, line, component and obstacle. Wrapped actions adapt
to narrow workbench widths, and opening a group does not dispatch a machine
command. This organizes conservative candidates; it does not establish physical
contact or complete the clearance-remedy workflow.

Validation: 21 focused engine and Kivy integration checks passed, covering exact
geometry/tool/operation separation, missing identities, complete motion retention,
search, pagination, narrow rendering, source inspection and remedy behavior. Both
architecture contracts and Ruff checks passed. Packaging and native acceptance
of grouped causes remain separate gates.
