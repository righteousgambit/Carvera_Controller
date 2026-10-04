# Decision and advanced machining requirements

These 25 requested additions extend the earlier 300-item implementation scope
to 325 requirements. A software checkpoint does not close native, adapter or
physical acceptance. Each item below remains open until its complete evidence
is obtained.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Task-density workbench | Remembered task-specific widths/forms with native responsive acceptance and left machine/camera arrangement |
| 2 | Next-five-minutes view | Approaching changes/inspection/reload/demand tied to actual operation progress and preparation |
| 3 | Machining action composer | Typed measure/review/correct/finish/reinspect workflows with supported execution and reusable successful sequences |
| 4 | Explained history defaults | Actual assembly/material/process applicability, changed-input explanation and reviewed selection |
| 5 | Preparation tray | Job-linked cutters/holders/collets/stock/jaws/gauges/actions and owned/assembled/installed/measured distinctions |
| 6 | Progressive capability disclosure | Task-appropriate compact and advanced controls driven by actual backend capabilities |
| 7 | Setup contact sheets | Exact scene/camera/hole-address/stock/assembly revision with reopen recognition and image custody |
| 8 | Inspection/motion boundary | Separate scene inspection, Cartesian tool-tip and joint jog with explicit frame/direction/increment/destination |
| 9 | Tolerance-driven simulation | Feature tolerance compared to actual model resolution and actionable insufficient-detail explanation |
| 10 | Clearance plots | Along-operation cutter/neck/holder/spindle/machine clearance with pose/geometry navigation and qualified registration |
| 11 | Measured stock import | Registered scan/mesh stock, nominal/observed/unsampled distinctions and real part validation |
| 12 | Stock coverage planning | Full cutter coverage/overtravel/clamp/travel/reach and reviewed alternative setup |
| 13 | Material lot lineage | Alloy/temper/source/dimensions/observations and process outcomes linked to actual lot |
| 14 | Per-edge behavior | Individual flute/insert measured runout/height with engagement consequence and inference distinguished |
| 15 | Spindle response map | Raw RPM/temperature/tool/engagement records, applicability and measured response model |
| 16 | Experimental chatter speed selection | Labeled speed comparisons with synchronized signals and inspected finish outcomes |
| 17 | Adaptive effectiveness | Actual adjustment/response timing, limiting sources and measured improvement evidence |
| 18 | Capability-backed adapter | Isolated simulator then actual backend mode/joint/offset/signal semantics and exercised UI/hardware actions |
| 19 | Five-axis accuracy explorer | Pivot/tool-length/angular uncertainty propagation and pose-specific measured validation |
| 20 | Advanced cutter contact patches | Barrel/lens/tapered-ball/form geometry, orientation-dependent engagement/reach/theoretical finish |
| 21 | Inverse-time inspector | Dialect-correct block duration/tip/joint demand and missing-feed/limit validation |
| 22 | Configuration-dependent limits | Documented angle/position/payload/accessory restrictions integrated into motion review |
| 23 | Rotary transition planner | Entire retract/rotation/head/approach motion, alternative parking/unwinding and qualified clearance |
| 24 | Peripheral handshake debugger | Actual requests/permissives/output/feedback/completion and timed missing-signal diagnosis |
| 25 | Thread fit acceptance | Fastener/class/depth/gauge/results, process-specific corrections and accepted fit |

## Assembly clearance checkpoint

Simulation now consumes byte-pinned converted holder CAD at the declared collet
face and exposed non-cutting cutter CAD. Triangle surfaces are clipped into up
to 64 axial bands per asset; each band encloses rotation about the registered
tool axis. This fills concavities and is conservative, not fixed-angle mesh
collision. Missing holder geometry stays explicitly unknown.

For constant +Z tools the engine checks continuous translated cylinders against
obstacle boxes, restricting XY contact time by axial overlap. Tilted tools
retain conservative swept boxes. Candidates carry their captured sections,
CAD digest, obstacle box and method into a scrollable inspector. Seeking is
refused after simulation inputs change. CAD envelope extraction runs off the
UI thread. No machine commands are introduced.

This advances requirement 10 and the earlier non-cutting assembly/collision
requirements. Numeric minimum-clearance plots, moving orientation, narrow-phase
fixture meshes, complete machine structures, measured registration and physical
qualification remain open. Initial-stock contact checks can still flag bodies
inside pockets already removed; residual-stock-aware body checks remain open.
