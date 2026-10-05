# Controller evolution acceptance ledger

Requested scope: all 25 enhancements, including substantial workbench UI improvements.
An engine, a visible button, and an exercised machine workflow are separate gates.
No hardware qualification is claimed by this ledger. Current source is on
`feat/simulator-and-spindle-load`; the installed desktop remains a separate artifact.
The additional 25 workflow improvements are retained in
`controller-advanced-workflows.md`; they do not replace this scope.

| # | Capability | Implemented checkpoint | Remaining acceptance evidence |
|---|---|---|---|
| 1 | Contextual command palette | Search/ranking, availability recheck, keyboard popup and workbench entry | Native keyboard interaction, contextual action coverage and responsive visual review |
| 2 | Operation tree | CAM operations, line spans, tools, bounds, nominal timing, selection seeks preview | Path highlighting, observed execution progress and native layout review |
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, Program-tab export/import preview | Native roundtrip including rest stock/camera registration, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Existing numeric stock/vise placement | Picking, translation/rotation handles, calibrated hole snapping, clipping/exploded view |
| 5 | Camera registration | Distortion/intrinsic engine, bounded pose fitting, residuals; camera-tab load/fit/save and raised-stock outline | Physical correspondences and intrinsic measurements, calibration-frame image custody, calibrated-picking UI |
| 6 | Live/Preview/Compare | One-packet observed pose; Preview/Live/Compare modes, independent markers and stale-data handling | Physical CAD registration, tool reconciliation and rotary pose integration |
| 7 | Tool passports | Sectioned revision-aware physical assemblies, dimension/CAD/drawing references, raw measurement attribution, physical holder preview and hash-bound facing recipe links | Measured holder/gauge geometry, qualified reach, complete asset validation, hole/thread recipes and complete native workflow |
| 8 | Physical ATC inventory | Capability-bounded M889 parser and command plans | Actual dispatch/readback, slot overlay and observed-versus-declared reconciliation |
| 9 | Two six-tool banks | Sequential usage planning, saved assembly selections and revision-bound preparation/measurement records | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification; preparation records do not enforce execution |
| 10 | Calibration bench | Existing repeated calibration/history | Unified bench, supported offset measurement, seating trends and actual machine exercise |
| 11 | Geometry probing | Existing probing workflows | Scene geometry selection, approach/reach preview, measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export | Scene nominal association, tolerances/repeat evidence, workbench integration |
| 13 | Surface maps | Persistent samples and bounded interpolation/exclusions; workbench provenance entry, measured-point plot, height queries, import/export and measured upper facing target | Probe transport capture and physical sample qualification; unsampled curvature remains unknown |
| 14 | Boundary-aware facing | Workbench polygon/scene-stock boundary, loaded cutter reach checks, final target/process inputs, async local program preview and cutter-bound recipes | Native complete workflow and physical travel/clearance qualification |
| 15 | Hole/thread workflow | Workbench hole locations, imperial/metric threads, optional spot/bore/chamfer stages, explicit cutter/angle/reach checks, async single-form threadmill preview and recipes | Native workflow, multi-form tooth-stack geometry, verified tapping qualification and actual backend adapter |
| 16 | Observed recipes | RPM baseline/shadow monitor and reviewed facing recipes bound to assembly revision, nominal cutter fingerprint and exact file hash | Actual cutting engagement/outcome evidence, broader recipe associations and physical process qualification |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded queued/executed events, gaps distinguished | Transport recording, synchronized telemetry/camera and replay UI |
| 19 | Collision checking | Workbench fixture/vise bounds, collision candidates and line navigation | Swept narrow phase/rotation, complete holders/machine structures and registration qualification |
| 20 | Stock removal | Canonical mm segments with bounded arcs; swept flat/ball/bull/drill/taper/chamfer/engraving/thread envelopes; rendered and persisted rest stock, workbench controls | Rotating-axis subdivision, true thread grooves, detailed holder/envelope metadata and native workflow validation |
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

Second source checkpoint: canonical segment production, rendered stock removal, residual snapshots, camera calibration controls and fresh observed pose modes are integrated. Surface/hole generators remain engines awaiting workbench integration. 35 focused workbench tests and 41 package/camera workflow tests passed; final broad suite passed 916 tests with 15 skips; DESKTOP28 native proof pending.

Third source checkpoint integrates surface/facing and threaded-hole planners into Setup, a shared styled local artifact browser, and per-machine persistent Scene drafts (stock, preview work offset, vise placement, component choices/visibility). Profile restoration batches geometry into one final rendered scene. Integration metadata stores are isolated from operator data. DESKTOP28 was installed and observed connected/Idle with fresh telemetry, physical T1/TLO and live Ubuntu camera; Preview/Live selector and camera registration controls were exercised visually. DESKTOP29 packaging and native planner/restart checks remain pending. Final broad suite: 967 passed, 15 skipped, 7 warnings (182.37s); Ruff lint/format and both import architecture contracts passed. Skips do not establish visual acceptance. Initial scene-timeout run is retained as failed-attempt evidence.

DESKTOP29 native checkpoint: built from `25d13b81cd104ed33a3394d56c0ca965687e6906`,
strict signature verification passed, installed and restarted. Saved camera-estimated
stock, vise placement and enclosure visibility restored; controller connected/Idle,
T1/TLO 50.480 mm, fresh telemetry and live Ubuntu camera observed. Facing form and
recipe browser rendered. Receipt and screenshot are in
`/Users/wes/Downloads/carvera-desktop29-20261003/`. This does not qualify physical
stock registration, cutting, or a complete planner workflow with measured tooling.
Native review found stock translucency difficult to read, planner disclosure
scroll jumps and a missing first-use Jobs directory. Subsequent source fixes add
stock volume edges, put planners first in Setup, reveal their disclosure heading,
initialize the owned Jobs folder and restore saved measurement controls. Focused
regressions: 36 passed. Broad suite: 971 passed, 15 skipped, 7 warnings in 139.72s;
Ruff lint/format and both architecture contracts passed. Packaging/native
acceptance of these fixes remains open.
