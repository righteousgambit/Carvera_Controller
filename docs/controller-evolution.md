# Controller evolution acceptance ledger

Requested scope: all 25 enhancements, including substantial workbench UI improvements.
An engine, a visible button, and an exercised machine workflow are separate gates.
No hardware qualification is claimed by this ledger. Current source is on
`feat/simulator-and-spindle-load`; the installed desktop remains a separate artifact.

| # | Capability | Implemented checkpoint | Remaining acceptance evidence |
|---|---|---|---|
| 1 | Contextual command palette | Search/ranking, availability recheck, keyboard popup and workbench entry | Native keyboard interaction, contextual action coverage and responsive visual review |
| 2 | Operation tree | CAM operations, line spans, tools, bounds, nominal timing, selection seeks preview | Path highlighting, observed execution progress and native layout review |
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, Program-tab export/import preview | Native roundtrip with all active assets, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Existing numeric stock/vise placement | Picking, translation/rotation handles, calibrated hole snapping, clipping/exploded view |
| 5 | Camera registration | Existing camera image and grid evidence | Intrinsic calibration, 3D extrinsic pose, raised-stock projection and residual validation |
| 6 | Live/Preview/Compare | Existing nominal playback | Independently measured MCS/WCS/TLO pose, separate live ghost, stale-data handling |
| 7 | Tool passports | Dimension and CAD profiles, measurement history foundations | Unified passport, holders, recipes, reach limits, drawings and measurement provenance |
| 8 | Physical ATC inventory | Capability-bounded M889 parser and command plans | Actual dispatch/readback, slot overlay and observed-versus-declared reconciliation |
| 9 | Two six-tool banks | Sequential usage planning and reload instructions | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification |
| 10 | Calibration bench | Existing repeated calibration/history | Unified bench, supported offset measurement, seating trends and actual machine exercise |
| 11 | Geometry probing | Existing probing workflows | Scene geometry selection, approach/reach preview, measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export | Scene nominal association, tolerances/repeat evidence, workbench integration |
| 13 | Surface maps | Existing leveling inputs | Persistent sampled map, exclusions/interpolation/error bounds, facing target separation |
| 14 | Boundary-aware facing | Existing facing generator | Stock-boundary/target workflow, overtravel and clearance validation |
| 15 | Hole/thread workflow | Existing tool profiles | Hole placement/fit/depth planner through spot/drill/bore/chamfer/threadmill; qualified tapping adapter |
| 16 | Observed recipes | Existing RPM baseline/shadow monitor | Material/cutter/stickout/engagement recipe evidence and outcome recording |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded queued/executed events, gaps distinguished | Transport recording, synchronized telemetry/camera and replay UI |
| 19 | Collision checking | Conservative swept bounds and confidence reporting | Actual scene meshes, swept narrow phase/rotation, segment UI, registration/geometry qualification |
| 20 | Stock removal | Bounded voxels, swept flat/ball cutters, fixed arbitrary axis, rest metrics | G-code segment producer, viewer rendering, persistent rest stock and rotating-axis subdivision |
| 21 | Recovery checkpoints | Canonical modal checkpoints, explicit verification inputs and conservative draft | Alarm/lost-position workflow, clearance/tool/WCS revalidation and qualified reentry |
| 22 | Multiple WCS | Existing coordinate backend | Stock instances, probing/offset transactions, repeat-part planner |
| 23 | Rotary workspace | General rotary forward geometry and limits | Chuck/jaws/tailstock setup, G93 program playback, indexed/wrapped/simultaneous validation |
| 24 | Capability adapters/IO | Versioned actual/declaration evidence, bounded Carvera command plans, lifecycle receipts | Transport adapters, fresh observed evidence, peripheral UX and verified acknowledgements |
| 25 | General five-axis | Head/table forward chains, pivots, limits, tool/work transforms, bounded inverse solving and angle unwind | Singularity handling and seed/branch review UI, indexed 3+2 workflow, declared/observed TCP and actual capable backend |

## Verification checkpoints

- New pure-engine tests cover archive corruption/traversal, modal parsing, bank planning,
  restrictive capability inference, command invocation rechecks, stock subtraction and kinematics.
- Import/export and operation navigation require native UI exercise before their UI gate closes.
- Collision candidates are conservative bounding volumes, not certified clearance.
- Voxel removal is approximate at the selected resolution; changing orientation requires subdivision.
- Firmware release capability metadata does not establish installed firmware or authorize a physical run.

Source checkpoint validation: 847 passed, 15 skipped in the broad suite; 7 focused UI/workflow tests passed after fixing the Console search alias. Ruff lint/format and both import architecture contracts passed. Skipped visual reference tests do not establish native visual acceptance. No new package install, controller command or physical run is claimed.
