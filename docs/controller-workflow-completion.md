# Workflow completion and advanced-machine requirements

The latest 25 recommendations extend the existing requirements ledgers. They do
not replace earlier requirements or treat existing partial foundations as complete.
The implementation goal remains active. Each workflow needs source validation,
installed interaction evidence and, where applicable, actual backend and physical
qualification. A machine profile declaration does not establish installed hardware.

| # | Requirement | Required completion evidence |
|---|---|---|
| 1 | Responsive background work | Large CAD/program/config workflows preserve controls and fresh state; bounded progress/cancel and measured native latency |
| 2 | Selection-driven workbench | Vise/cutter/path selection opens linked editing, measurements and operations while preserving the left views |
| 3 | Coordinated timeline | Operation/change/ramp/reload/probe/inspection selection aligns pose, source, telemetry and recorded camera with timing gaps visible |
| 4 | Desktop data grids | Tool/offset/measurement/magazine sorting, resizing, keyboard/bulk/paste/virtualization at small and large scales |
| 5 | Geometry-linked draft editing | Stickout/jaws/WCS inputs highlight precise geometry with previous/proposed states and reviewed application |
| 6 | Shared job search | Entity/operation/frame/measurement/alarm search navigates exact related context |
| 7 | Actionable setup readiness | Specific missing/stale/mismatched inputs open exact editors or evidence without closing unrelated checks |
| 8 | Persistent purposeful layout | Resizable/collapsible/pinned setup/run/inspection arrangements preserve visible proportioned model and camera panes |
| 9 | Visual change review | Old/new setup/tool/offset/program geometry and affected operations/simulation results are linked |
| 10 | Offline reconciliation | Disconnected complete preparation reconciles actual machine/magazine/offsets/capabilities on connection |
| 11 | Executable two-bank workflow | Appropriate stop, reload, physical/logical identity reconciliation, measurement, offset validation and qualified reviewed re-entry |
| 12 | Tool/pocket/spindle identity | Logical tools, physical assemblies, pockets and transfer/spindle positions with actual fixed/random changer semantics |
| 13 | Geometry-driven probing | Selected features produce supported approach/travel/expected-result previews and captured feature/frame-bound actual results |
| 14 | Inspect/correct/finish | Nominal/tolerance/results, explicit radial/diametral bounded correction, supported finish and reinspection |
| 15 | Complete moving-assembly collision | Swept cutter/neck/holder/spindle/machine/workholding/rotary checks identify first pose and contacting surfaces with qualified geometry |
| 16 | Remaining-stock decisions | Residual allowance/reach/candidate tools and finishing comparison at explicit simulation resolution |
| 17 | Explained adaptive decisions | Signal age, engagement inference, proposal, limiting factor and observed response tied to motion context |
| 18 | Machine-side adaptive execution | Qualified local sampling/actuation and desktop targets/bounds/recipes with measured latency and failure semantics |
| 19 | Trajectory quality | Segment/corner/dynamics/blending contributions and dialect-correct accuracy/timing comparisons |
| 20 | Spline/NURBS support | Dialect-specific preserved geometry or explicitly bounded conversion error with supported backend exercise |
| 21 | Five-axis tool/joint comparison | Intended tip and head/table motion, branches/limits/singularity and orientation/unwind review with actual adapter |
| 22 | Coordinate-frame inspector | Machine/fixture/work/local/rotary/tool transform tree explains effective coordinates and offsets |
| 23 | Synchronized machining | Pitch/encoder phase/reversal/retract/interruption semantics and actual threading/tapping qualification |
| 24 | Mill-turn channel/resources | Turret/spindle/live-tool/workpiece ownership, synchronization/shared-axis conflicts and transfer state simulation |
| 25 | Commissioning/fault replay | Real UI exercised with delay/stale/alarm/disconnect/tool mismatch; actual capabilities commissioned with configuration-bound results |

## Tool-bank preparation source checkpoint

`tool-bank-preparation.md` records partial progress on requirement 11. Preparation
selection/persistence and attributed evidence do not implement stop, physical
reload, controller mapping, offset application or resume execution. Existing
playback does not enforce these local preparation records. Full requirement 11
and the overall implementation goal remain open.

The DESKTOP72 source run found six existing navigation integration fixtures with
identity-only machine contexts. The board's display-name assumption raised
`KeyError: name`; the failed suite and uninstalled artifact are retained. The
follow-up uses the machine identity as the display fallback, preserving the exact
context binding rather than inventing or switching machine identity. Tests cover
that fallback as well as the actual shared-navigation workflows.
