# Navigation and process workspace requirements

These 25 extensions retain the full implementation goal. Existing engines,
profile declarations and local renders do not prove complete operator workflows
or physical machine execution. Each row remains open until its end state has
been exercised on the relevant interface and, where applicable, backend/hardware.

| # | Requirement | Required end state |
|---|---|---|
| 1 | Permanently visible workbench navigation | Task selectors, machine/profile identity and compact hold/stop controls remain accessible throughout report scroll and source/review navigation at supported sizes. |
| 2 | Scene entry into object controls | Scene selection opens the exact retained inspector and links its identity across library, program and applicable camera overlays. |
| 3 | Illustrated compact editors | Dimension drawings, common/advanced fields and persistent Apply/Revert support validated reversible editing. |
| 4 | Machining file browser | Geometry/units/tools/setup/revision previews and missing dependencies distinguish local inspection, staging and execution. |
| 5 | Job revision comparison | Changed operations/tools/offsets/stock/fixtures/parameters identify affected path regions while preserving active-run identity. |
| 6 | Contextual command palette | Entity- and capability-specific actions navigate actual workflows and explain missing prerequisites. |
| 7 | Pinnable instruments | Selected actual/calculated values retain readable source and freshness across workbench tasks. |
| 8 | Reversible setup experiments | Draft alternatives compare reach/clearance/time and retain actual active-machine configuration independently. |
| 9 | Synchronized run timeline | Executed source, pose, telemetry, camera and interventions share time navigation with explicit gaps. |
| 10 | Focused execution layout | Actual operation, next intervention, tool, signals and exceptions remain prominent while preparation drafts persist. |
| 11 | Complete two-bank workflow | Reviewed bank planning, park/reload/reconciliation/measurement/reentry are exercised through physical execution. |
| 12 | Distinct physical tool identity | Individual assemblies retain history independently of logical tool numbers and pocket placement. |
| 13 | Process-linked tool CAD | Registered flute/neck/shank/collet/holder geometry supports reach and exact contact-surface explanations. |
| 14 | Fixture installation assistant | Plate/vise/hole/hardware/jaw setup produces illustrated instructions and measured refinement of estimated placement. |
| 15 | Feature probing and inspection | Selected features link nominal/tolerance, reviewed approaches, measurements and applicable corrections. |
| 16 | Full-face coverage review | Cutter coverage, untouched material, overtravel, clamps and reach resolve all boundary coverage before cutting. |
| 17 | Engagement prediction and telemetry | Stock engagement predictions compare observed RPM/feed/load with explained discrepancies and latency. |
| 18 | Machine-side adaptive execution | Qualified local loop enforces desktop-configured targets/bounds and reports sample-to-action timing and limits. |
| 19 | Motion transform explanation | Selected motion exposes program/work/tool/local transforms and resulting actual machine pose. |
| 20 | Reviewed restart planner | Executed boundary/modal/tool/offset/rest-stock state yields clearance-reviewed qualified reentry candidates. |
| 21 | Complete fourth-axis workspace | Chuck/tailstock/calibration/stock/angular limits/winding/indexed/simultaneous workflows show actual axis motion. |
| 22 | Five-axis kinematics explorer | Tip and joint paths, rotary alternatives/travel/singularities are linked to actual machine topology and capable backend. |
| 23 | Synchronized process capabilities | Supported tapping/threading cycles expose encoder readiness and actual cycle state through qualified execution. |
| 24 | Resource and peripheral handshakes | Commanded/observed peripheral states, missing signals and shared resources explain progression and waits. |
| 25 | Backend commissioning | Real adapter transport/execution/telemetry/recovery are exercised in simulator and physically qualified with configuration-bound evidence. |

## Fixed Program navigation source checkpoint

Program task selectors now sit outside their own report viewport. Common Program
selection/start/pause/abort controls are also outside that viewport, in one
responsive four-column group that wraps to two columns in a narrow pane. The
redundant Program heading and excess status height have been removed. Retained
Operations, Simulation, View & playback and Job package sections are attached one
at a time, and task changes clear hidden focus and cancel old scroll animations.
Source inspection and return-to-clearance routing still target their actual
scrolling content without scrolling the fixed navigation.

19 focused integration checks passed, including long-report scroll, narrow/wide
selectors, retained drafts, cancelled obsolete reveals, source routing,
clearance return, captured geometry and responsive plot controls. Both import
architecture contracts and Ruff passed. Rendered evidence was inspected locally.
This closes the source/test/render checkpoint for fixed Program navigation.
The installed desktop package has not been rebuilt for this checkpoint; native
packaged acceptance and the remaining requirements stay open.

## DESKTOP94 packaged native acceptance

Installed `2.1.0-DESKTOP94` from source
`66054d830e2c0a1a90dba7003d7b01c9eb17e04a`. The verifier checked 425
repository files and 428 files in each staged, built and installed package with
zero mismatches. Built, installed and preserved DESKTOP93 recovery signatures
passed. Recovery is retained in the package evidence directory.

Native disconnected preview exercised retained Operations input, Job package,
View & playback scrolling, local program selection, clearance-cause reveal,
source line 5 inspection and Return to clearance review. Fixed Program tabs and
actions remained visible throughout; the returned review heading was visible.
Original six operator stores and Kivy configuration were restored and verified.
Normal launch reported Idle C1, physical T1, TLO 50.480 mm, 0 RPM and 0 feed,
with telemetry age 0.17 s and camera age 0.2 s at readback. No program was selected.

Receipts and native screenshots:
`/Users/wes/Downloads/carvera-desktop94-20261004/native-receipt.json` and
`artifact-verification.json`. This closes the packaged native acceptance for the
fixed Program navigation checkpoint. It does not close other requirements above
or qualify physical machining, probing, tool exchange or adaptive execution.

## Rich program picker source checkpoint

The Program picker now uses a compact responsive location bar and centered file
rows without unsupported folder glyphs. Narrow layouts stack the list and details;
the complete details body scrolls independently rather than overflowing its pane.
Selection launches a bounded background inspection of complete captured bytes
(up to 1 MiB / 5,000 lines). Oversized or invalidly encoded files report an
explicit quick-inspection limitation instead of presenting a prefix as complete.

Inspection includes raw-byte SHA-256, units, operation names, declared tools,
work frames, unresolved motion, interpreter notes and source excerpt. Missing
definitions refer to the current preview library, not physical loading. A sampled
XY thumbnail contains only resolved segments; multiple work frames are not
overlaid without registered transforms. Selection/refresh/close generation changes
discard stale worker results. Details open at the beginning of their text.

19 focused checks passed for captured bytes, unit normalization, pending tools,
limits, stale/closed selection, missing definitions, responsive layout and
unchanged local-preview / remote-download / upload boundaries. Both architecture
contracts and Ruff passed; wide and narrow renders were inspected. Native
packaged acceptance remains a separate gate. Full file-browser requirements,
including job/setup revision/dependency integration, remain open.


## DESKTOP95 packaged inspection acceptance

Installed `2.1.0-DESKTOP95` from source
`8639c599b1ea5d7ff3217f0343493f380b5fa33a`. The verifier checked 427
repository files and 430 files in each staged, built and installed package with
zero mismatches. Built, installed and preserved DESKTOP94 signatures passed.
The premature verification performed while installation was still running is
preserved separately; the post-install and post-restoration checks passed.

Native disconnected selection displayed captured mm units, 11 lines, one Face
inspection operation, T99, rectangular resolved XY motion, missing T99 preview
definition, raw-byte SHA-256 and unresolved initial motion. Focused Ctrl+End
reached the source excerpt. Local preview loaded the selected file and operation
without connecting the controller. Wheel scrolling did not visibly move the
nested detail text; pointer-scroll ergonomics remains open. A legacy tool overlay
was visible behind the model on synthetic preview load and remains open.

Original operator stores and configuration were restored with exact readback.
Normal DESKTOP95 launch reported Idle C1, physical T1, TLO 50.480 mm, 0 RPM,
0 feed, telemetry age 0.20 s, camera age 0.4 s and no program selected.
Receipts: `/Users/wes/Downloads/carvera-desktop95-20261004/native-receipt.json`,
`artifact-verification.json` and `operator-restoration.json`.
This closes the named packaged inspection/loading checkpoint, not the complete
file-browser requirement, physical qualification or full controller goal.

## Single-scroll inspection and orientation HUD source checkpoint

Program details now use one DesktopScrollView with a visible, draggable bar.
Selectable readonly source text grows to its wrapped content height and passes
wheel events to that viewport; selection and refresh return the viewport to its
start. Source text remains copyable without a second scrolling surface.

The apparent legacy overlay recorded in DESKTOP95 was the Top/Front orientation
cube. Inspection and real-window renders identified both draw order and inherited
machine camera translation as causes. The HUD is raised after program mesh
rebuilding and now uses scene rotation with a centered, fixed-distance camera.
Face picking uses that same camera, independent of stock/fixture centering,
program scale and machine fit distance.

39 focused checks passed across program inspection/browser and machine simulation.
The final seven UI checks additionally exercised actual wheel dispatch, selection
reset, repeated full program loading and cube face clicks with large changes to
machine camera center. Architecture contracts and Ruff passed. Real-window
framebuffer inspection confirmed the cube is visible; widget FBO export cannot
prove GL rendering and its blank attempt is retained. Initial fixture-path and
incomplete loader test failures are also retained.

Evidence is under `/Users/wes/Downloads/carvera-picker-ergonomics-20261004/`,
with final logs `carvera-picker-ergonomics-final.log` and
`carvera-picker-ergonomics-accepted.log` in `/tmp`.
This closes the source/test/render checkpoint. Installed DESKTOP95 does not
contain these changes; rebuilt native-package acceptance remains open.


## DESKTOP96 installed verification and camera restoration

Installed `2.1.0-DESKTOP96` from source
`72aca09503c8bd20baecca741eb8646e80287637`. Post-restoration verification
on 2026-10-04 at 14:17 UTC checked 427 repository files and 430 files in
each staged, built and installed package with zero mismatches. Built, installed
and preserved DESKTOP95 signatures passed. Operator stores and configuration
matched their original backup exactly before normal relaunch.

Native disconnected program selection showed units, operation, missing T99
preview definition, unresolved initial motion and a sampled rectangular thumbnail.
Dragging the visible detail scrollbar reached the complete source excerpt.
Reselection returned to the top. Native wheel gestures in both directions over
the details did not visibly move them: native wheel acceptance remains OPEN
despite the source test passing. The next investigation must exercise native
wheel delivery and routing, rather than infer installed behavior from UnitTestTouch.

After local program load the orientation cube was visible in the foreground.
Clicking Front changed the machine preview to a front view. This closes the
named native orientation HUD checkpoint; it does not qualify machine geometry
or collision detection.

Normal reconnect observed Idle C1 at 192.168.0.79, firmware 2.1.0c, physical T1,
TLO 50.480 mm, 0 RPM, 0 feed and telemetry age 0.03 s. Camera access initially
failed. The existing Tailscale SSH authentication check completed; Ubuntu's
local snapshot returned HTTP 200. A localhost-only SSH forward restored the
existing saved camera URL, and the native controller showed a live frame aged
0.1 s. The forward is a current process, not an installed persistent service.

Receipts and native screenshots:
`/Users/wes/Downloads/carvera-desktop96-20261004/native-receipt.json`,
`artifact-verification.json`, `operator-restoration.json`,
`native-detail-drag.png`, `native-cube-front.png` and
`native-program-restored.png`. Full requirements and physical qualification
remain OPEN. No push was performed.
