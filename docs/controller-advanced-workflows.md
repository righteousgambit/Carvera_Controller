# Additional controller workflow requirements

These are the additional 25 improvements proposed in the October 3 controller
session. They supplement, rather than replace, `controller-evolution.md`.
They are requirements awaiting implementation and acceptance unless a receipt
below explicitly establishes a narrower completed gate. Existing engines and
profile fields are foundations, not proof of a complete operator workflow.

| # | Requirement | Evidence required to accept the workflow |
|---|---|---|
| 1 | Persistent next-action strip | Contextual prerequisites, direct navigation, state changes and native interaction |
| 2 | Setup readiness inspector | Entered/measured/stale evidence for stock, fixtures, tooling and offsets; actionable unresolved items |
| 3 | Selection-driven workbench | Consistent scene, operation and inspector selection for editable components |
| 4 | Saved task workspace layouts | Setup/run/probe/inspection/rotary arrangements, resizing and restart persistence |
| 5 | Visual asset browser | CAD/tool/program thumbnails, units, dimensions, compatibility and dependency review |
| 6 | Undoable setup comparison | Undo/redo and changes against saved/last-used setup without changing physical state |
| 7 | Units and coordinate inspector | Explicit MCS/WCS/tool offsets, imperial/metric entry and backend-specific program-unit support |
| 8 | Program compatibility report | Unsupported commands, macros, tooling, travel, feed modes and initial-state assumptions linked to lines/scene |
| 9 | Machine configuration comparison | Actual settings versus saved profile, proposed change review and recoverable backup/readback |
| 10 | Command receipts | Sent, accepted, completed and verified states; unresolved disconnects remain visible |
| 11 | Tool assembly editor | Cutter/collet/holder/gauge length/stickout CAD or dimensioned geometry and reach/clearance review |
| 12 | Tool wear and replacement history | Per-physical-cutter use, measurements, outcomes and explicit replacement identity |
| 13 | Tool-change choreography | Retract/approach/collet/pickup/calibration/return animation and supported physical sequence |
| 14 | Calibration health trends | Repeated TLO, seating, probe and reference measurements with time/source and native charts |
| 15 | Probing workflow builder | Reusable sequence, approach/retract preview, measured results and explicit offset application |
| 16 | Feature inspection plans | Nominals, tolerances, repeat measurements, scene association and part-specific exports |
| 17 | Fixture coordinate systems | Plate/vise/jaw/part frames, measured mounting relations and multiple parts |
| 18 | Part-flip assistant | Setup transition, locating surfaces, residual material and required remeasurement |
| 19 | Engagement/process dashboard | Geometry engagement, recipe and telemetry distinctions; qualified acknowledged adaptive control |
| 20 | Synchronized run replay | Executed operation, telemetry, override, alarm, tool and camera timeline with linked seeking |
| 21 | Explained recovery planner | Known/unknown position/tool/offset/stock, clearance/reentry and required revalidation |
| 22 | Instrumented peripherals | Named I/O, observed feedback, operation-boundary actions and machine-side interlocks |
| 23 | Complete rotary setup | Chuck/jaws/tailstock, centerline/zero, limits, clearance and indexed/continuous qualified execution |
| 24 | Five-axis reachability | Machine topology, orientation, limits, configuration branches, unwinding/singularity review and qualified backend |
| 25 | Production-run workspace | Multiple offsets, repeated parts, tool limits, inspection intervals, interventions and per-part records |

The original 25-item ledger remains open. Controller UI, source tests, built
packages, installed runtime, physical calibration and qualified execution are
separate acceptance gates.
