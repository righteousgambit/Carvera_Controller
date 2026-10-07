## Immutable-bound picking and package qualification checkpoint

A timing check against the saved C1/Saunders/vise CAD profile (123,582 triangles, SHA256 `ff5ae4980b41a8280127922286c0dc452c991214db952bed3e766855382464bb`) exposed a 28.3185-second miss scan under the current host load. Exact immutable GeometrySnapshot bounds now reject non-intersecting rays before triangle scanning. Slabs are widened beyond barycentric edge tolerances, account for component motion and finite ray limits, and fall back to exact triangles on ambiguous nonfinite arithmetic. Mutable or duck-typed geometry is not trusted for pruning. Possible hits still require the unchanged exact triangle and cutaway checks; a box intersection never creates a surface selection. Snapshot positions additionally reject booleans, consistently with exact point validation.

The same profile and miss ray took 0.001907 seconds after pruning; profile loading took 52.944 and 79.195 seconds in these two host-contended runs. These are pure-model timings, not a controlled native interaction benchmark. Ninety-eight geometry/render/picking tests pass, including oblique randomized equivalence, motion, cutaways, finite distance, tolerant edge hits, guaranteed zero triangle work on a miss, mutable-bound distrust and malformed geometry rejection. Focused strict typing of both engine modules, full lint/format/diff and both architecture contracts pass. Two early invocations referenced a nonexistent test filename and ran no tests; those logs remain retained. This source follows frozen DESKTOP237 and needs later package/native qualification.

Frozen `e6be4636dd1e18261134c69b6d03074e0ffa9283` hosted run 37548312312 is successful: 2974 passed, 17 skipped. All 527 staged DESKTOP237 source files independently match the frozen archive (SHA256 `37c07746db9327c45a44764928ba48ecd722729ccd657cd9fddf117ed6d57cc5`) with its explicit version change. Packaging process 1317 remains active; built/signature/install/native gates remain OPEN. Installed DESKTOP236 still reports Idle, zero RPM/feed, no program and fresh camera/telemetry. No actuation was issued.

Completed DESKTOP234/235/236 scratch trees moved to the archive volume after byte/type/mode/link comparisons and strict signature verification; 7987, 7990 and 7996 entries respectively match, with zero mismatches. Original scratch paths remain links and recovery apps remain installed. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop237-20261006/completed-scratch-relocation.json`. Local capacity now reads about 6 GiB; installation still requires its own bundle-size/reserve check. Broad requirement completion, native selection disambiguation, camera registration, synchronized capture and physical qualification remain OPEN.

## Component isolation and exact view restoration checkpoint

The component inspector adds Isolate selected and Restore previous view. Isolation hides other component groups, includes both outer-machine groups when selected, and frames known cutter geometry through the existing asynchronous framing path. Repeated isolation retains the original visibility and camera baseline. Restore reinstates component/cutter visibility, machine-view enablement, framing scope, projection/orbit/pan/zoom and the saved camera baseline. A different machine-profile identity rejects restoration; missing geometry or rotary machine view rejects isolation before visibility changes.

Visibility changes are applied as one validated batch with at most one geometry rebuild. Program geometry, local placements, offsets, physical tooling and saved setup records are not modified. The controls synchronize under the same readback guard, preventing the scope dropdown from turning presentation updates into persisted setup edits. Current surface/candidate/measurement references and pending frame requests are invalidated when visibility changes. Validation: 59 isolation/picking/inspection-plane checks pass (`/private/tmp/carvera-isolation-accepted-tests-20261006.log`), followed by all eight isolation checks after the final projection/view update (`/private/tmp/carvera-isolation-source-final-20261006.log`). The compact 360-pixel render was inspected. Focused UI typing, full lint/format, diff checks and both architecture contracts pass. Initial failed runs are retained: a nonexistent refresh call was corrected, then explicit fixture teardown restored presentation state before the combined suite. Native acceptance and the full selection-disambiguator requirement remain OPEN; installed DESKTOP236 does not include this source.

## Depth-ranked component selection checkpoint

Scene Pick component now lists the nearest surviving surface of every intersected component, ordered along the clicked ray. Choosing a farther candidate selects through occluding components without changing setup, visibility or controller state. Triangle identity, winding normal, component-frame point, rendered point and group motion remain available for nominal inspection. Candidate controls appear only in Pick mode to keep the workbench compact.

Candidate selection rejects changes to geometry, pose, cutter, setup, viewport, camera matrices, visibility, cutaway, explosion or interaction request. Unexpected mesh-worker errors log diagnostics, release picking and permit retry without publishing a partial selection. The geometry API bounds component candidates and preserves stable depth ties. Validation: all 77 geometry/scene/section tests pass (`/private/tmp/carvera-ranked-accepted-tests-20261006.log`), followed by all seven candidate-context checks after the final layout adjustment (`/private/tmp/carvera-ranked-layout-final-20261006.log`). The 360-pixel render was inspected; the selector precedes the detailed surface readout. Focused machine/UI typing, full Ruff lint/format and both architecture contracts pass. Two earlier combined runs failed because a synthetic visibility fixture omitted outer-machine entries; their logs are retained and the fixture now preserves the complete visibility map. Isolate, installed/native acceptance and the complete selection-disambiguator requirement remain OPEN. This source postdates installed DESKTOP236; no machine actuation was issued.

## Native drawing/face acceptance and inspection navigation checkpoint

## Hosted scroll-position regression checkpoint

Exact `25c5d538b809702a7c1f9f2f76125b23aaae11fd` hosted run 37544109096 completed with 2954 passed, 17 skipped and one failed assertion: the preserved normalized scroll coordinate was `0.19999999999999998` versus literal `0.2`. The section completion remained on Camera and produced its result. The assertion now uses zero relative tolerance and absolute `1e-12`, retaining the no-navigation invariant without requiring identical floating-point representation. Failed-run evidence remains `/private/tmp/carvera-face-ci-failure-20261006.log`. Acceptance of the next exact revision remains OPEN.

## Face-to-section handoff and native saved-layout checkpoint

A picked-face shortcut now reveals the section controls even when aligning that face intentionally replaces an active cutaway. The deferred reveal validates the resulting cutaway and plane while retaining the original geometry, pose, setup, cutter, viewport, explosion, component and request identity gates. The original face pick remains stale after the cutaway changes; it is not republished as a current measurement reference. Later pick replacement, interaction requests, geometry changes, invalid plane drafts and cutaway changes cancel the pending navigation.

Native DESKTOP236 (`773945ff655f70a9f846572f40713a93bcc6a93a`) exercised saving a separately named layout, changing media width to 60%, restoring 50%, exporting through the file picker and reimporting the same export without duplicates. The original `Machining 50-50` layout restored Program/Operations. Both original layout records retain every original field. The layout store migrated from schema 1 to schema 4 and gained exactly one explicitly named verification layout; the other eight operator JSON paths retain their hashes. Export SHA-256: `6fd0efbe8df222d1bcf54fc00fd529481c630ecb4453c6180609f8012418569a`. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/desktop236-native-layout-receipt.json`.

The import picker now says `Import workspace layouts`, and a duplicate-only import explains that the layouts are already saved. Native observations exposed temporary telemetry unavailability during the picker; the existing connection recovery returned fresh Idle telemetry. Final native readback: Live Program/Operations, no selected program or remote file, zero RPM/feed, camera 0.8 seconds old and telemetry 0.15 seconds old. No actuation was issued.

Validation: 57 section/picking/layout integration checks passed (`/private/tmp/carvera-cutaway-layout-accepted-20261006.log`); all 7 final layout UI checks also pass (`/private/tmp/carvera-layout-import-final-20261006.log`). Focused typing across the three changed UI modules, Ruff lint/format across 568 files and both architecture contracts pass; all 13 shared file-picker regressions pass (`/private/tmp/carvera-layout-picker-regression-20261006.log`). The final singular/plural import feedback check passes separately. The first regression fixture lacked stock geometry and failed before exercising the handoff; the corrected fixture passes. Native exploded-layout restoration, installing the newer source, camera registration, synchronized capture, physical qualification and the broader 350 requirements remain OPEN. The installed/native result is distinct from these new source changes.

Installed DESKTOP236 (`773945f`) now has independent native evidence for stock-section SVG export and picked-face alignment. CUA saved a fresh drawing through the custom file picker; XML readback confirms eight contours, Z -84.9298 mm, 127 x 69.4182 mm spans and the nominal-CAD/physical-placement qualifier. Picking stock triangle 10 returned normal (0,0,1); Use picked face retained distance -59.49168 mm and calculation returned four boundary segments with the expected U/V spans. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/desktop236-native-export-face-receipt.json`. All nine tracked operator JSON paths remain unchanged. A transient connection loss recovered through the existing automatic retry without restart/manual reconnect; final Program/Live reports Idle, zero RPM/feed and fresh camera/telemetry. No actuation was issued. These checks close only the named installed drawing/face workflows; saved-layout native acceptance and physical qualification remain OPEN.

The source now adds Pick a face from the section editor and Section picked face from scene interaction. Each shortcut reveals its destination after layout settles, with current-section and current-surface guards. Missing/stale faces preserve the current plane; calculation disables its picking shortcut. This removes the long manual scroll round trip observed in native inspection. All 49 section/scene-interaction checks pass, focused typing of both UI modules passes, Ruff across 568 files passes and both architecture contracts are kept. New shortcut installation/native acceptance and the full 350-requirement controller overhaul remain OPEN.

## Section export recovery and standard-density layout checkpoint

Drawing export now releases its controls after unexpected encoder errors or temporary-file cleanup failures. Failed encoding retains an existing destination and a subsequent export can succeed. The plane editor stacks its axis and distance controls below a 485 dp row width, retaining room for length expressions on standard-density displays.

Hosted run 37539530627 at `983f300` failed one compact-editor assertion: at 360 pixels on Linux the input was squeezed into a second column. The corrected breakpoint passes the explicit density-1 compact-editor check (`/private/tmp/carvera-section-density-one-20261006.log`). All 13 section-workbench checks pass, including injected unexpected encoder and cleanup failures, destination preservation, retry and no-command assertions (`/private/tmp/carvera-export-recovery-accepted-20261006.log`). Focused UI typing and Ruff lint/format across 568 files pass. These changes are source-only; installed DESKTOP236 remains at `773945f`. Exact-revision hosted CI, native export/picked-face/layout acceptance and the broader 350-requirement overhaul remain OPEN. No machine actuation was issued.

## Unit-aware section editing and native plane checkpoint

The section inspector now keeps a persistent position/signed-normal-distance label and accepts the shared length expressions (including fractional inches), shows the canonical interpretation, and validates the same ±10,000,000 mm bounds as the geometric plane. The axis and expression controls stack at narrow widths. Valid repaired drafts clear old validation messages. Enter calculates through the input's actual validation event. Invalid drafts invalidate exports and withhold cutaway/result publication.

Unexpected calculation-worker failures now log their diagnostic, publish no section, release disabled editors and allow a subsequent retry. An injected RuntimeError validates this recovery path. The final section suite passes 59 checks (`/private/tmp/carvera-section-editor-accepted-20261006.log`), including the unit/keyboard/bounds/compact-layout workflow, geometry, GPU cutaway, stale worker results and failure/retry. The 360-pixel render was inspected and shows the complete expression and conversion. Focused UI typing, Ruff across 568 checked Python files and both architecture contracts pass. Earlier failed runs are preserved: a host-load-sensitive injected delayed worker timed out; isolated checks passed, and the final complete suite passed after worker recovery was hardened. These source changes still require package/native acceptance.

Installed DESKTOP236 frozen `773945ff655f70a9f846572f40713a93bcc6a93a` independently exercised stock axis midplane calculation (127 by 69.418 mm nominal section), custom (1,0,1) normal, normalized oblique section (U/V 71.950 by 69.418 mm), below-plane stock cutaway and full-component restoration. Return to Live Program showed Idle, zero RPM/feed, no program and fresh camera/telemetry; nine operator JSON paths remain unchanged. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/desktop236-native-section-receipt.json`. This advances geometry/process requirement 13 (virtual inspection tools) and responsive/recoverable workflow requirements. Native picked-face selection, SVG export, saved layouts, newer editor acceptance, measured geometry/clearance, camera registration, synchronized capture and the complete 350 requirements remain OPEN.

Hosted CI run 37537475643 completed successfully for preceding `9a1db50073fd13f20a5df49ef20604041b168e43`. This is distinct from hosted acceptance of the next section-editor revision.

## DESKTOP236 installed inspection and ATC regression checkpoint

DESKTOP236 is now built, independently verified and installed from frozen `773945ff655f70a9f846572f40713a93bcc6a93a`: 527 packaged files match, zero mismatches, strict signature verified. DESKTOP235 remains the recovery app. Native gestures verified 25 mm exploded inspection, visible reassembly, and return to the Live Program workspace with Idle, zero spindle/feed, no selected program, fresh camera and telemetry. All nine operator JSON paths remain unchanged. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/desktop236-native-inspection-receipt.json`. Native feature-plane and saved-layout workflows remain OPEN; newer palette routes and joint-corner review are source-only.

Hosted run 37534781305 at `2d933f9` completed with two failed ATC overlay tests, 2939 passed and 17 skipped. Both legacy fake viewers lacked the display-movement method introduced for exploded inspection. Fixtures now bind the real viewer movement methods, and additionally verify that ATC markers follow exploded displacement in Preview and return to assembled coordinates in Live. All three overlay checks pass (`/private/tmp/carvera-slot-overlay-accepted-20261006.log`). Hosted acceptance of the repaired final revision remains OPEN until its own run completes. No backend actuation or physical qualification is claimed.

## Declared joint corner-demand checkpoint

The inverse-time joint study now retains signed velocity changes at each interior waypoint, including direction reversals and explicit stops/restarts. Unequal fraction intervals use their own declared block durations. Rotary coordinates remain unwrapped: a 350-to-10-degree transition remains minus 340 degrees. Numerically equal rates (relative 1e-9, absolute 1e-12) are omitted. Limits on input and output sizes and cancellation withhold partial reports.

The operation inspector shows the total changes and reversals, then pages through every retained corner with fraction, declared seconds, signed before/after rates, units and source provenance. Pages reset on source line or study replacement; paging neither seeks the toolpath nor sends controller commands. A discontinuity in piecewise-linear velocity requires an explicit blending/dynamics model; this calculation does not invent finite acceleration, endpoint rest, jerk or backend timing.

Validation: 39 inverse-time/corner/inspector checks pass, including nonuniform timing, unwrapped rotary travel, stops/restarts, cancellation, numerical overflow, bounded output, complete paging and replaced-study identity. The final paging checks and rendered panel were also inspected (`/private/tmp/carvera-joint-corners-render-20261006.log`). Receipt: `/private/tmp/carvera-joint-corners-accepted-20261006.log`. Strict machine typing, focused UI typing, Ruff across 572 files and both architecture contracts pass. This advances the axis-demand inspector (geometry/process requirement 20) and dynamics model (process/backend requirement 17). Acceleration/jerk modeling, observed motion feedback, installed/native acceptance and physical qualification remain OPEN. The source postdates frozen DESKTOP236; its original packaging process remains active at this checkpoint.

## Contextual scene commands and native palette checkpoint

Search now routes directly to all eight scene components, using the existing inspector selection and navigation. Explode/reassemble actions use the inspector's unit-aware separation; explosion rechecks Preview at invocation and never changes pose mode or physical setup automatically. Installed DESKTOP235 keyboard opening, filtering, coordinate-inspector Enter navigation, unmatched-query guidance, Down selection and Escape dismissal were verified through native gestures/screenshots. The app returned to Live/Idle with zero RPM/feed and a fresh camera; all nine operator JSON paths remain unchanged. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop235-20261006/desktop235-native-palette-receipt.json`. Seven unit/integration command-palette checks pass, including all component routes, unit-aware separation, Live rejection and no-command assertions (`/private/tmp/carvera-component-palette-final-tests-20261006.log`). Focused command typing, Ruff lint/format across 571 files and both architecture contracts pass. New component command native coverage remains OPEN.

DESKTOP236 is packaging frozen `773945ff655f70a9f846572f40713a93bcc6a93a`, archive SHA-256 `4f33ac2a230601c4a242cd1d605ad407d297454f2545a70df54cedf8ce9e1f6d`, in original exec session 59111. Build request: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/build-request.json`. This immutable candidate includes feature planes, layout schema 4 and exploded inspection; newer palette routes are separate source work. Independent package verification, installation and native inspection acceptance remain OPEN until terminal build readback.

## DESKTOP235 native lens workflow acceptance

The recovered native bridge verified the labelled lens editor, rejection of invalid focal-length input, and successful local Apply of a temporary unmeasured prior. The prior was then cleared; reopening showed blank intrinsic fields and five zero distortion coefficients. Cancel and Return to live restored the Program view with Idle, spindle 0 RPM, feed 0 mm/min, a 0.3-second camera frame and 0.04-second telemetry. All nine operator JSON paths match their post-install hashes. No registration fit/save or actuation was issued. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop235-20261006/desktop235-native-lens-receipt.json`. This closes the installed lens editor workflow at frozen `86a67c5`; measured camera registration, synchronized capture and installed acceptance of later section/exploded source remain OPEN.

## Exploded machine-inspection source checkpoint

The inspector now provides unit-aware 0–100 mm assembly separation, automatic framing and reassembly. Rendering, picking, component framing and ATC slot overlays share presentation offsets. The cutter follows the spindle; nominal CAD, physical pose, setup, program and cutaway plane coordinates are retained. Preview is explicitly labelled exploded inspection; Live/Compare remain assembled and placement gestures require reassembly. Pending picks/framing and probe-preview references reject changed separation.

Portable schema-4 layouts retain separation and schemas 1–3 remain readable. Restoring an exploded layout from Live is rejected before presentation mutation. Source validation: 83 regressions and two GPU/UI checks pass (`/private/tmp/carvera-exploded-accepted-20261006.log`, `/private/tmp/carvera-exploded-gpu-ui-20261006.log`). Strict model typing and both architecture contracts pass. Final validation adds 42 interaction/layout checks, 16 compact section/layout checks, 33 model/library unit checks and two final rendering/Live-transition checks (`/private/tmp/carvera-exploded-final-ui-20261006.log`, `/private/tmp/carvera-exploded-compact-20261006.log`, `/private/tmp/carvera-exploded-final-unit-20261006.log`, `/private/tmp/carvera-exploded-final-render-20261006.log`). Ruff across 571 files, focused typing of five UI modules and both architecture contracts pass. Installed feature-plane/exploded/layout acceptance, camera registration/synchronized capture, backend/physical qualification and the full 350-requirement scope remain OPEN. No actuation was issued.

## Feature-aligned section source checkpoint

The section workbench now accepts arbitrary finite nonzero normals and can align to a current picked CAD face. Shared normalized plane math governs triangle intersections, GPU cutaways and surface picking. Angled plots/export use an orthonormal U/V basis; layouts retain normals in schema 3 while preserving legacy readability. Midplane repairs invalid distance drafts, and changed planes withhold late section results. The compact editor uses labelled X/Y/Z fields.

Validation: 133 section/layout/picking checks passed, including angled GPU pixel clipping and portable round trips (`/private/tmp/carvera-feature-plane-accepted-20261006.log`). All 15 final section/layout UI checks also pass (`/private/tmp/carvera-feature-plane-labeled-20261006.log`). Strict typing passes for both machine modules; focused UI typing and both architecture contracts pass. Installed feature-plane/layout acceptance, exploded views, camera registration/synchronized capture, backend/physical qualification and the full 350-requirement scope remain OPEN. No actuation was issued.

## Saved cutaway layouts and DESKTOP235 installed checkpoint

Named layouts now capture setup-bound component-axis cutaways and restore them before returning to the saved workbench task. Geometry/setup mismatch rejects restoration before pane or view changes; portable schema-2 exports retain section state and legacy layouts restore full components. Source validation: 30 layout unit/integration tests and 108 broader layout/section/picking regressions passed (`/private/tmp/carvera-saved-cutaway-tests-20261006.log`, `/private/tmp/carvera-saved-cutaway-regression-20261006.log`). Strict layout typing, focused UI typing, Ruff across 569 files and both architecture contracts pass. Arbitrary feature-aligned planes, exploded views and installed acceptance of this new persistence workflow remain open.

DESKTOP235 was installed from frozen source `86a67c5dcb07ef7e6f4b76da5077596c9d96e2d6`. The installer independently verified 525 files, zero mismatches and strict signature success at 2026-10-06T20:06:42Z. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop235-20261006/artifact-verification.json`. DESKTOP234 remains a recovery app. Native version 235 and fresh idle telemetry/camera were observed after launch. The UI bridge timed out during the subsequent camera-reference interaction; native lens workflow acceptance remains open. New lens-binding, cutaway and saved-layout source postdates the frozen installed package.

# Controller evolution acceptance ledger

## Component cutaway and DESKTOP235 built checkpoint

The section workbench now clips the selected nominal CAD component in the 3D
view, keeping either side of its X/Y/Z section plane. Shader uniforms preserve
the dense CAD buffers and setup geometry. Picking uses the identical nominal
plane after removing component motion; changes invalidate late pick results and
retained picked-surface probe previews. Components remember their planes during
in-session selection changes. Invalid or overflowing input restores the full
component. A responsive action grid preserves the coordinate field at 360 pixels.
Compact and wide source controls were rendered and inspected.

The final 113 section/scene/surface-inspection/calibration checks pass. The GPU
regression reads actual clipped/full pixels, including both half-spaces. Strict
typing passes on both changed machine modules, focused UI typing passes on three
modules, full Ruff lint/format passes for 568 files, and both architecture contracts
remain kept (281 files / 1500 dependencies). The initial offscreen test lacked an
OpenGL window and crashed; the harness now initializes it before creating the
buffer. Failed evidence remains retained. Final receipt:
`/private/tmp/carvera-cutaway-accepted-tests-20261006.log`.

Hosted run 37519912903 at `8f1c2ff59bdabd55aa8ef29b8bc6cc96fd48af39`
reports 2882 passed, 17 skipped and one calibration-bench freshness assertion
failure. Its synthetic packet aged in real time while navigating scope. The
test now supplies an explicit local bench clock and advances it to verify stale
status; production freshness limits are unchanged. The corrected focused suite
passes, while exact new-source hosted acceptance remains OPEN.

Original DESKTOP235 packaging completed with exit 0. Independent verification
at 2026-10-06T19:54:36.750212Z matches frozen
`86a67c5dcb07ef7e6f4b76da5077596c9d96e2d6` in all 525 packaged files,
with zero mismatches and strict signature verification passing. Receipt:
`/Users/wes/.codex/artifacts/carvera-desktop235-20261006/built-verification.json`.
At this earlier build checkpoint, DESKTOP235 was not yet installed. The installed receipt above supersedes that state; DESKTOP234 is retained as recovery.
Latest lens-binding and cutaway source postdates this frozen build. Installed
acceptance, arbitrary feature-aligned planes, exploded views, physical
geometry registration and the full overhaul remain OPEN. No actuation was issued.

## Camera lens reference-binding checkpoint

Loaded and successfully fitted pixel intrinsics now retain the image size and
camera source against which they were reviewed. Capturing a reference at another
resolution or source preserves the numbers but prevents fitting until the
labelled lens editor is reviewed and applied for that reference. Values are not
silently rescaled. Cancel preserves the old binding; clearing the job clears it.
Legacy files retain their known image-size binding without inventing a source.
The asynchronous fit identity includes the lens binding, so a late result cannot
replace a changed model. Apply remains a local draft operation with no file or
machine write, and does not qualify the intrinsic measurements.

The editor keeps a compact Review prior prompt above the scrollable fields when
the reference differs. Detailed context scrolls with the form while Apply and
Cancel remain visible. A first version of the longer prompt clipped the first
field at 360 pixels; that failed regression is retained, and the shorter prompt
passes the unchanged field-visibility requirement. Corrected 360- and 900-pixel
source renders were inspected. The final camera/reference/calibration/overlay
suite passes 126 tests, focused typing passes for both UI modules, full Ruff
lint/format passes for 568 files, and both architecture contracts remain kept.
Receipts are retained in `/private/tmp/carvera-lens-reference-accepted-20261006.log`,
`/private/tmp/carvera-lens-reference-final-typing-20261006.log` and
`/private/tmp/carvera-lens-reference-architecture-verified-20261006.log`.

This source postdates the original frozen DESKTOP235 operation at
`86a67c5dcb07ef7e6f4b76da5077596c9d96e2d6`. That operation remains live;
installed lens-binding acceptance, measured camera registration, synchronized
capture and the full controller overhaul remain OPEN. DESKTOP234 remains the
independently verified installed recovery checkpoint. No actuation was issued.

## DESKTOP234 native coordinate and startup configuration checkpoint

Frozen source `6eac6c722e88a50f6a47cad1e76df55991fe10e7` is installed
as DESKTOP234 with 524 independently matching packaged files, zero mismatches
and strict signature verification passing. DESKTOP233 recovery is retained.
Native pointer/keyboard review confirms that quarter-inch input converts to
6.35 mm and yields configured bed X -173.65 / Y -120 / Z -110 mm; unknown
measured fixture registration stays explicitly unknown. Invalid input clears
numerical results. Close, Program navigation and Return to live restore fresh
reported pose, Idle C1, zero RPM/feed and camera imagery. All nine tracked
operator JSON paths retain their hashes or absence. No actuation was issued.
This bounded coordinate draft/invalid/close scope is CLOSED.

The independently located installed-process log
`/Users/wes/.kivy/logs/kivy_26-10-06_35.txt` records one startup configuration
request, an 8192-byte download with matching advertised MD5, and remote download
success (lines 188, 194, 197). The native configuration-unavailable footer warning
is absent. This closes one startup transfer observation; inline progress/cancel
interaction and sustained reconnect stability remain OPEN. The later receiver
acknowledgement, rotated camera overlay and lens-editor changes are not installed
in DESKTOP234. Physical qualification and the full overhaul remain OPEN.
Receipt:
`/Users/wes/.codex/artifacts/carvera-desktop234-20261006/desktop234-native-coordinate-configuration-receipt.json`.

## Labelled camera lens-model draft checkpoint

Camera / Fit & exchange now opens a labelled editor for horizontal/vertical
focal length, principal point and radial/tangential distortion. The editor binds
to the frozen image size and current camera/connection owner. Cancel preserves
the current model; invalid values or changed reference/inputs/owner prevent
Apply. Successful Apply changes only local fitting inputs and invalidates the
previous fit/save/overlay identity. The existing pose solver receives edited
distortion, and loaded calibration coefficients populate the editor. Clearing a
job clears the lens prior. No file save or machine command occurs on Apply.

All 48 camera-overlay/reference checks pass, focused typing passes for both
affected UI modules, all 568 Python files pass Ruff lint/format, and both
architecture contracts are kept. Source renders at 360 and 900 pixel widths
were inspected. The initial compact render's fixed explanation left insufficient
field space; the explanation now scrolls with the form while actions remain
visible, and the regression requires the first editable field to be inside the
viewport. Failed bounds assertions and renders remain retained outside the
repository. This source is newer than frozen DESKTOP234. Installed interaction,
physical lens calibration, camera registration and exposure synchronization
remain OPEN.

## Camera stock rotation and native input guard checkpoint

The live camera stock outline now projects the same declared stock-center
rotation and work offset as the machine-view stock mesh, then applies the fresh
reported table displacement. Previously it projected an axis-aligned box even
when the configured stock was rotated. Independent corner/projection regressions
reproduce that failure at 30, 90 and -45 degrees before the correction; all 36
camera-overlay/reference checks pass afterward. Focused typing, full Ruff
lint/format and both architecture contracts pass. This source postdates frozen
DESKTOP234 and is not yet installed. Physical registration and exposure
synchronization remain OPEN.

Installed DESKTOP233 native pointer review confirms that Fit with missing
intrinsics reports the missing input inline, Save stays disabled, and Return to
live restores fresh reported pose while camera imagery remains available. No
correspondences or intrinsics were entered, no calibration was saved, and all
nine tracked operator JSON paths retain their hashes or absence. This bounded
input-rejection/live-restoration scope is CLOSED; actual camera registration
and the full overhaul are OPEN. Receipt:
`/Users/wes/.codex/artifacts/carvera-desktop234-20261006/desktop233-camera-input-guard-receipt.json`.

## DESKTOP217 installed stock comparison checkpoint

Frozen `abc3e2fa5afc1d48551a50829e62a56a718c8006` is installed as
DESKTOP217 at 2026-10-06T09:42:12.420657Z: 504 independently matching files,
zero mismatches and strict signature verification passing. DESKTOP216 recovery
is retained. Native direct saved-profile connection reports Idle C1. Unsaved
stock X 127 to 125 mm renders solid draft and visibly dashed previous dimensions
in XY/XZ, with Previous 127 / Draft 125 / Change -2 mm. Cancel/reopen restores
127 with Apply disabled. Final Cancel and Return to live restore fresh reported
pose, telemetry (0.41 s) and camera imagery (0.9 s). All ten tracked operator JSON
paths retain their hashes or absence. No actuation was issued. This bounded
size-comparison/cancel workflow is CLOSED; full application, measured mounting
and physical qualification remain OPEN. Newer vise comparison is not installed.
Receipt: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop217-20261006/native-stock-size-receipt.json`.

Completed owned DESKTOP151 records were copied to the external build archive,
verified against 2,893 file hashes and 3,390 manifest members with zero mismatch
and strict signature passing, then replaced by a resolving link at the old path.
The relocation receipt is retained beside the archived records.

## Previous-versus-draft vise placement checkpoint

The vise editor now draws the previous configured CAD envelopes in dashed gray
alongside the solid draft placement, retaining previous translation, rotation and
jaw shift. XY and XZ share one scale and bounds include both states. The amber
zero-jaw reference remains distinct from the previous configured jaw. Independent
corner calculations cover a nonzero CAD pivot, prior 15-degree rotation, prior
2 mm jaw shift, and X/Y/Z/rotation/jaw changes. All 59 setup-editor checks pass,
including invalid-draft clearing, unchanged active/saved setup and no commands.
The 800 by 600 comparison render was inspected. Full Ruff/format and architecture
checks pass. An initial fixture error is retained; the corrected fixture uses the
viewer workholding fields. This addition is newer than frozen DESKTOP217;
installed vise-comparison interaction and measured mounting/clearance remain OPEN.

Hosted run 37442505409 at exact `1bd3c84b0081880019cea127c93dfaca4d960dbb`
is green: 2,620 passed, 15 skipped, one warning in 858.92 seconds. Full raw logs
are retained. This verifies the frozen DESKTOP216 source, not the newer vise work.


## Stock dimension comparison and DESKTOP216 interaction checkpoint

Stock dimension editing now shows solid teal draft and dashed previous configured
sizes at a common stock-frame corner and shared XY/XZ scale. Both shrinking and
growing X/Y/Z remain in bounds; unconfigured stock has no invented predecessor.
Clicking a dimension retains field focus. Invalid drafts clear the comparison;
active/saved setup and command transport remain unchanged. All 54 setup-editor
checks pass; 13 final size/program-zero checks pass after the dash-width correction. The compact 800 by 600 render was inspected. Explicit dash gaps and
one-pixel previous outlines correct Kivy's previously solid reference rendering,
including the program-zero references. This source change is newer than installed
DESKTOP216; installed size-comparison acceptance is now closed by the DESKTOP217 checkpoint above. Program-zero native dash styling remains a separate OPEN check.

DESKTOP216 from frozen `1bd3c84b0081880019cea127c93dfaca4d960dbb` is
installed at 2026-10-06T09:28:49.719630Z, with 504 independently matching packaged
files, zero mismatches and strict signature verification. DESKTOP215 recovery is
retained. Native unsaved rotation 0 to 30 degrees and program-zero X -180 to -170
mm show Previous/Draft/Change +10 mm, rotated XY and projected XZ context, machine
zero and draft program zero. Clicking the X axis ray focuses/reveals X -170.
Cancel/reopen restores X -180 and rotation 0 with Apply disabled. Return to live
shows fresh reported pose, Idle C1, telemetry and camera imagery. Ten tracked
operator JSON paths are unchanged; no actuation occurred. Previous geometry is
gray but its dash styling is not correct in this package; the newer source fix is
not yet installed. Bounded draft/cancel interaction is verified; full application,
actual controller WCS and measured physical placement remain OPEN.
Receipt: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop216-20261006/native-program-zero-receipt.json`.
Hosted run 37441083635 at exact `b7c0a98e3272c15ac778312abd5e166322d7c823`
is green: 2,616 passed, 15 skipped, one warning in 852.71 seconds. Full logs remain
retained, and newer exact-source CI is not implied by that success.


## DESKTOP215 installed connection navigation checkpoint

DESKTOP215 from frozen `b7c0a98e3272c15ac778312abd5e166322d7c823` is
installed at 2026-10-06T09:18:51.767979Z. Independent verification finds 504
matching packaged files, zero mismatches and a passing strict signature check.
DESKTOP214 recovery is retained. Native pointer interaction verifies that the
header Connect action while disconnected opens Machine/Settings, and that the
header Connection action from Scene while connected opens the same controls.
Saved-profile direct connection reports Idle C1 with fresh telemetry and camera
imagery. Return to live restores the fresh reported pose. All ten tracked operator
JSON paths are unchanged; no actuation was issued. This closes the bounded
connection shortcut workflow. Full operator workflows and physical qualification
remain OPEN. The newer program-zero drawing is not in this frozen package.
Receipt: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop215-20261006/native-launch-receipt.json`.
Hosted run 37440492371 at exact `d6d0071a9b6f9bdd501309a8d47fad92bdca5286`
is green: 2,616 passed, 15 skipped, one warning in 863.05 seconds. Full raw job
logs are retained. Newer b7c0a98 and 84aa7bc runs remain active at this checkpoint.


## Declared program-zero displacement drawing checkpoint

Program-zero fields now project declared stock in machine coordinates. Solid
geometry shows the draft; dashed geometry shows previous configured stock.
XY includes center stock rotation and XZ shows its projected envelope. Program
zero and machine zero remain distinct, and clickable axis rays select the offset
field. No previous stock is invented when the baseline is unconfigured. All 48
setup-editor checks pass, including X/Y/Z displacement, independent rotated
corner math, projection bounds, invalid-draft clearing and unchanged saved/active
setup. A compact render was inspected. This is a declared preview transform;
controller WCS, measured mounting and installed interaction remain OPEN. The
addition is newer than frozen DESKTOP215 (`b7c0a98`).


## DESKTOP214 native stock-origin and rotation checkpoint

DESKTOP214 from frozen `30d319537f4b91ddd3d83d4e3342ac6c67e5fbfa` is
installed with 504 matching packaged files and strict signature verification;
DESKTOP213 recovery remains. Native unsaved X-origin editing shows Previous
-118.6 / Draft -120 / Change -1.4 mm with program-zero and corner references.
Rotation 0 to 30 degrees shows its solid XY footprint and dashed zero-angle
reference; XZ remains explicitly unrotated. Clicking the angle ray focuses the
rotation field. Cancel/reopen restores X -118.6 and rotation 0, with Apply disabled.
All ten tracked operator JSON paths are unchanged. No actuation occurred.
This closes that bounded draft/cancel workflow, not physical alignment or the
full setup application workflow. The newer Connection fix is not in DESKTOP214.
Receipt: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop214-20261006/native-stock-editor-receipt.json`.


## Collapsed reconnect input regression checkpoint

Native DESKTOP213 still swallowed the header Connection click. A new full-app
pointer regression at its 2340 × 1552 rendered content bounds reproduces the
failure when the reconnect notice is collapsed. Kivy dispatches through the
zero-height container to its disabled, overflowing child buttons. The hidden
reconnect row is now detached from the inspector; it is reattached in its original
position when recovery is visible. All 11 connection navigation/recovery checks
pass, including retry, cancel, legacy modal behavior and hidden-row ownership.
The failing pre-fix log is retained outside the repository. No controller command
was issued by these checks. Native acceptance remains OPEN: frozen DESKTOP214 is
building from earlier `30d3195` and does not contain this later correction.


## Program-frame stock origin drawing checkpoint

Selecting a stock-origin coordinate now places the draft unrotated corner against
program zero in XY and XZ, using one shared scale. A dashed reference shows the
previous corner, and axis rays select their owning origin field. The footprint,
zero and both corners fit the common projection bounds. The drawing explicitly
omits stock rotation and measured mounting; it does not imply that the corner is
a probed datum. All 44 setup-editor checks pass, including X/Y/Z corner edits,
axis selection, invalid-draft clearing and unchanged saved setup. A compact
render was inspected. Draft changes still require the existing setup review/application
path and send no controller commands. Native acceptance remains open; this source
addition is newer than installed DESKTOP213.

## DESKTOP213 installed stock comparison checkpoint

Installed DESKTOP213 matches frozen `756c6ad56a0a8611025be2dd87a6ce06887b1fc3`
in all 504 packaged files, with zero mismatches and strict signature verification.
Installation completed at 2026-10-06T08:45:40.501819Z; DESKTOP212 recovery remains.
Hosted run 37436120619 at that exact revision passes quality hooks and the full
suite: 2,605 passed, 15 skipped and one warning (851.26 seconds).
Native launch/title, saved-profile direct connection, stock dimension click focus,
Previous 127 / Draft 125 / Change -2 mm, Cancel and reopen restoring 127 mm,
and Return to live were read back. C1 reports Idle with fresh telemetry/camera.
All ten measured operator JSON paths remain unchanged. No actuation was issued.

The header Connection shortcut did not visibly navigate during native pointer
automation; the Machine tab and Connect profile path did. Its installed interaction
remains open. Five connection-navigation checks pass, including actual pointer
events through the app at 530 and 360 dp workbench widths. Those checks do not
explain or close the native discrepancy. Full native workflows, physical placement
and the newer stock-rotation illustration remain open.
Receipts: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop213-20261006/`.

## Stock rotation drawing checkpoint

Selecting stock rotation now shows its XY footprint using the simulation's
center-of-stock transform, with a dashed zero-angle reference and a clickable
angle ray. The XZ projection stays explicitly unrotated. Arc rendering uses the
model's normalized angle so large equivalent rotations remain bounded. Draft
edits, invalid input and dimension selection do not apply geometry, save operator
setup or issue controller commands. Positive, negative and right-angle cases are
checked against the simulation transform and an independently calculated signed
orientation. All 41 setup-editor checks pass, including an allowed 750-degree
equivalent rotation; a compact render was inspected. This source addition is newer than
frozen DESKTOP213 and its installed interaction gate remains open.

## Illustrated edit context and compact inspector checkpoint

Selected stock/vise dimensions now show previous value, draft value and signed
change beside the drawing. Unconfigured stock does not invent a previous value
or displacement. Stock rotation change summaries use degrees rather than mm.
A compact rendered stock comparison was inspected; the declared frame remains
explicit, and edits do not apply geometry or issue controller commands.

Hosted run 37434139632 at `10c8feead49c01f490742c35d5db4d55a2841bd2`
finishes with 2,591 passed, eight failed and 15 skipped (571.02 seconds). The full
job log is retained, including failures; full CI remains open. Compact tests now
establish the actual pane width and overflow height instead of inheriting OS
backing-store scale, full-page height or a resizable dialog's content height.
The bound-recording fixture declares list stock dimensions and rotation, matching
its owning archive contract; program/stock/offset validation remains enforced.
77 combined navigation/program/setup/lifecycle/recording checks pass at single
metric density; seven recording-setup contract checks pass separately. This does
not close the hosted, installed interaction or physical qualification gates.

## Residual ownership and DESKTOP212 native checkpoint

Single-stock stale-input refresh and change review now hide only their own
residual geometry. An independently displayed repeat-parts result is preserved;
explicit simulation/reset actions retain their existing replacement behavior.
The regression rejects the original clearing behavior and eight focused geometry
change/repeat-parts checks pass. Hosted full-suite acceptance remains open.

Installed DESKTOP212 matches frozen `d13002e8c5711e50c88d2684ec274f0b210ca814`
in all 504 measured packaged files, with zero mismatches and strict signature
verification. Installation receipt: 2026-10-06T08:10:25.351855Z. Native menu
navigation, drawing-dimension focus, an unsaved 76.2 to 75 length edit, Revert draft
back to 76.2 and Return to live were read back. C1 reported Idle with fresh
telemetry and camera. All ten operator JSON paths match their pre-install hashes.
DESKTOP211 recovery is retained. Newer compact metric and residual ownership
changes are not in this package; complete native and physical gates remain open.
Receipts: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop212-20261006/`.

## Compact metrics and hosted-suite checkpoint

Hosted run 37431953710 at `d13002e8c5711e50c88d2684ec274f0b210ca814`
passes the complete quality-hook step, including strict machine typing. Its full
test step finishes with 2,586 passed, 12 failed and 15 skipped. The failed layout,
recording and retained-simulation checks remain open; focused checks do not close
this full-suite gate.

Calibration metric cards and hole-planning actions now reserve more readable
minimum widths before forming multiple columns. The tool-replacement evidence
test declares its required program rather than inheriting a different program
from the shared app; a separate check retains the missing-required-cutter gate.
Heartbeat test doubles explicitly declare that their legacy modal is not an
inline recovery presentation. CI now reports named tests, slow-test durations and
thread stacks before the existing timeout, without changing its test set or timeout.
Native interaction and physical acceptance remain separate from this source work.

Requested scope: all 25 enhancements, including substantial workbench UI improvements.
An engine, a visible button, and an exercised machine workflow are separate gates.
No hardware qualification is claimed by this ledger. Latest source work is on
`feat/compact-recording-20261005` in the owned compact-recording worktree;
`feat/simulator-and-spindle-load` and the installed desktop are separate checkpoints.
The additional 25 workflow improvements are retained in
`controller-advanced-workflows.md`; they do not replace this scope.

| # | Capability | Implemented checkpoint | Remaining acceptance evidence |
|---|---|---|---|
| 1 | Contextual command palette | Search/ranking, availability recheck, keyboard popup and workbench entry | Native keyboard interaction, contextual action coverage and responsive visual review |
| 2 | Operation tree | CAM operations, line spans, tools, bounds, nominal timing, preview selection and revision-bound whole-operation path highlighting | Observed execution progress and installed/native interaction and layout acceptance |
| 3 | Portable jobs | Versioned SHA-bound archive, validation, asset installation, worker-prepared import preview, late-result ownership guard, exact calibration-image and pose custody | Native roundtrip including rest stock/calibration assets, persistent setup selection, complete measurement/photo workflow |
| 4 | Direct scene editing | Exact rendered-surface picking, stock/vise XY and Z handles, CAD-pivot vise Z rotation, declared-center stock Z rotation, independent grid/angle snapping, actual displayed cutter picking, async component framing, reviewed drafts with persistence/cancel safeguards and nominal component-axis cutaways with shader/picking agreement | Native interaction acceptance, general tilted rotation, calibrated hole snapping, installed feature-plane/exploded acceptance |
| 5 | Camera registration | Distortion/intrinsic engine, bounded pose fitting, residuals; frozen reference image/pose custody, point picking, sectioned workbench, schema-2 exchange and raised-stock outline | Physical correspondences and intrinsic measurements, native point-picking and fitted-file exchange acceptance, exposure synchronization |
| 6 | Live/Preview/Compare | One-packet observed pose; Preview/Live/Compare modes, independent markers and stale-data handling | Physical CAD registration, tool reconciliation and rotary pose integration |
| 7 | Tool passports | Sectioned revision-aware physical assemblies, dimension/CAD/drawing references, raw measurement attribution, physical holder preview and hash-bound facing/hole-stage recipe links | Measured holder/gauge geometry, qualified reach, complete asset validation and complete native workflow |
| 8 | Physical ATC inventory | Capability-bounded M889 parser, explicit query transport, bounded connection-scoped receipts and paginated configured-pocket/local-declaration review and nominal configured-target overlay and validated historical receipt exchange | Broader native viewport/orbit coverage and physical assembly/occupancy reconciliation |
| 9 | Two six-tool banks | Sequential usage planning, saved assembly selections, revision-bound preparation/measurement records, separate post-placement mapped receipts and fresh current-spindle TLO comparison | Safe stop/reload/reconcile/calibrate/resume workflow with physical qualification; preparation records do not enforce execution |
| 10 | Calibration bench | Unified assembly/tool-number evidence bench with repeatability statistics, revision/source-bound offset changes, post-placement receipt comparison and fresh current-spindle TLO; existing repeated calibration | Native bench acceptance, integrated measurement launch/transport, reference measurements and physical seating/offset qualification |
| 11 | Geometry probing | Existing probing workflows; exact nominal triangle/point/normal selection and ball-center approach/search/retract planning with projected scene review | Qualified reach/clearance, registered probe transport, measurement custody and measured datum transaction |
| 12 | Integrated CMM | Existing CMM primitives/export; retained nominal surface/setup association, workbench operator-entered receipts, signed limits/repeat statistics, reviewed portable exchange, CSV/HTML reports and searchable paged receipt/deviation history and reviewed atomic TSV/CSV batch entry | Registered compensated machine receipt capture, richer fitting/tolerances, complete native workflow and physical qualification |
| 13 | Surface maps | Persistent samples and bounded interpolation/exclusions; workbench provenance entry, measured-point plot, height queries, import/export and measured upper facing target | Probe transport capture and physical sample qualification; unsampled curvature remains unknown |
| 14 | Boundary-aware facing | Workbench polygon/scene-stock boundary, loaded cutter reach checks, final target/process inputs, async local program preview and cutter-bound recipes | Native complete workflow and physical travel/clearance qualification |
| 15 | Hole/thread workflow | Workbench hole locations, imperial/metric threads, optional spot/bore/chamfer stages, explicit cutter/angle/reach checks, async single-form and explicit multi-form tooth-stack previews and recipes | Native complete workflow, manufacturer tooth reference/clearance and thread-fit qualification, verified tapping qualification and actual backend adapter |
| 16 | Observed recipes | RPM baseline/shadow monitor and reviewed facing/hole-stage recipes bound to assembly revision, nominal cutter fingerprint and exact file hash | Actual cutting engagement/outcome evidence, complete process history and physical process qualification |
| 17 | Adaptive supervisor | Existing shadow proposals; bounded override command plans | Real transport age/ack/limits, machine-side protection and qualified adaptive actuation |
| 18 | Recorded timeline | Bounded status recording, continuous receipt playback with explicit gap/boundary stops, event replay/archive marker, exact selected-program association, declared setup custody/restoration; session-bound JPEG recording, validated bundles and native camera import/display/return-live; historical scene/tool restoration source-tested | Native receipt playback and corrected setup capture/restoration including retained calibration images, exposure/clock qualification, actual execution attribution, linked toolpath replay and complete recorded-run workflow |
| 19 | Collision checking | Workbench fixture/vise bounds, collision candidates and line navigation | Swept narrow phase/rotation, complete holders/machine structures and registration qualification |
| 20 | Stock removal | Canonical mm segments with bounded arcs; swept flat/ball/bull/drill/taper/chamfer/engraving/thread envelopes; rendered and persisted rest stock, workbench controls | Rotating-axis subdivision, true thread grooves, detailed holder/envelope metadata and native workflow validation |
| 21 | Recovery checkpoints | Canonical modal checkpoints, explicit verification inputs and conservative draft | Alarm/lost-position workflow, clearance/tool/WCS revalidation and qualified reentry |
| 22 | Multiple WCS | Coordinate backend; declared G54–G59 arrays, plans and full-array preview; source-tested multi-stock subtraction, persisted per-part occupancy and frame-aware path/cutter playback with reversible file/historical restoration | Probing/offset transactions, continuing machining from restored multi-stock results and repeat execution/inspection |
| 23 | Rotary workspace | General rotary forward geometry and limits | Chuck/jaws/tailstock setup, G93 program playback, indexed/wrapped/simultaneous validation |
| 24 | Capability adapters/IO | Versioned actual/declaration evidence, bounded Carvera command plans, lifecycle receipts | Transport adapters, fresh observed evidence, peripheral UX and verified acknowledgements |
| 25 | General five-axis | Head/table forward chains, pivots, limits, tool/work transforms, bounded inverse solving and angle unwind; cancellable declared-profile import and multi-seed workbench review with selected joint/limit/equivalent-angle results and local rank diagnostic; ordered joint-transition sampling, selectable rank trace, interior dependent-direction and full-turn review; fixed-orientation indexed work-point mapping, selectable point inspection and explicit route handoff | Native complete branch/path/indexed-review acceptance, between-sample singularity handling, physically qualified indexed 3+2 workflow, declared/observed TCP and actual capable backend |

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

DESKTOP134 checkpoint (source `03e651d`): installed manifest/signatures and
DESKTOP133 recovery verified. Native hole-stage recipe linking exercised explicit
stage selection, required provenance, save and independent event/hash readback.
Missing loaded pilot-drill restoration was rejected. Operator data was restored
and the app returned to Live with fresh reported telemetry/camera. Successful
native restoration with every required cutter loaded and physical workflow
qualification remain open; none of the original 25 requirements closes here.
See `tool-assembly-history.md` for the bounded acceptance receipt and gaps.

DESKTOP134 positive restoration checkpoint: compatible declared pilot drill and
single-form threadmill profiles were loaded through the native toolset library;
restoration populated the hole planner (1/4-20, G54, `10 20 8 6`) and reported
matched cutter geometry. Generating the preview then closed the UI with an
`AttributeError` because `Makera.loading_file` was not initialized before its
first load. The failure log and shutdown process sample are retained in
`/Users/wes/Downloads/carvera-desktop134-positive-20261004/`. Operator stores and
configuration were restored and verified. Source now initializes loading state
and reveals the hole-planner heading after disclosure layout. The strengthened
integration suite exercises the real local viewer handoff; 29 tests passed,
including generated drill/thread stages without machine commands. Ruff and
format checks passed. Packaging and native generation acceptance remain open.

DESKTOP135 checkpoint (source `de0afa7`): installed source manifest and strict
signature verification passed. Native recipe restoration and local drill/thread
generation succeeded without the first-load crash. The operation tree exposed
17 unresolved threadmill motion lines: generated arcs did not declare their
center mode. Source now emits G91.1 on a separate block followed by G90 before
any motion. The inspected official and community Robot.cpp handlers treat G91.1
as relative endpoint mode and always use incremental IJK centers; the following
absolute block is therefore required. This is source compatibility evidence,
not installed firmware or cutting qualification. Regression checks require all
generated arc lines to produce canonical segments while retaining unknown
initial approaches. Native acceptance of the corrected arc preview remains open.

DESKTOP136 native checkpoint (source `e31f1fb`): package, installed manifest and
strict signatures passed; DESKTOP135 recovery retained. Native local program
inspection and preview loaded the corrected 1/4-20 sample. Selected threadmill
operation shows 22 resolved motion lines and zero unresolved (previously 17
unresolved); its remaining warning is unknown dwell-unit timing. Screenshot,
program/hash, pinned firmware sources and receipts are retained in
`/Users/wes/Downloads/carvera-desktop136-20261004/`. Eight operator stores and
configuration were restored after preview. This closes the generated arc-mode
defect only; physical tooling, registration, cutting and the full hole/thread
workflow remain open.

Simulation tool readiness now lists all missing/incomplete required cutter
profiles before calculation, disables calculation until dimensions are supplied,
and routes each numbered issue to tool comparison. Program/scope/profile-keyed
caching avoids scanning all motion segments on repeated telemetry refreshes;
the UI check performs no CAD disk I/O. Calculation still verifies asset bytes
and builds full registered envelopes. An end-to-end generator/interpreter/tool
model/material-removal regression covers explicit drill and threadmill profiles;
true thread grooves remain unresolved by the outside-diameter model. Native
acceptance of the new readiness controls remains open.

DESKTOP137 native readiness checkpoint (source `8cc391d`): installed manifest
and strict signatures passed with DESKTOP136 retained as recovery. Native
simulation review listed both missing cutters, routed T3 to tool comparison,
then reduced issues from two to one to zero as drill-only and complete preview
toolsets were loaded. Calculation remained disabled until both required profiles
were ready. Screenshots and `native-acceptance.json` are retained in
`/Users/wes/Downloads/carvera-desktop137-20261004/`. Eight operator stores and
configuration were restored before relaunch; the stores still matched afterward.
The app returned to Live with fresh reported Idle/T1/TLO telemetry and Ubuntu
camera. No program upload or motion was performed. This closes cutter-readiness
UI acceptance only; stock/path frame review, full native material removal, true
thread geometry and physical workflow qualification remain open.

Stock/path alignment source checkpoint: simulation now reviews continuous +Z
cutting envelopes against declared stock before calculation, reports possible
engagement or a complete miss, and exposes stock bounds in program millimetres
with a direct Scene placement/work-offset review action. The review runs off
the UI thread, is cached by program/scope/tools/stock, cancels superseded work
and rejects older results. Rapid travel is excluded; tooltip position alone
does not substitute for the cutting envelope. Air-cutting previews remain
available. This is conservative geometry guidance, not material-removal,
clearance or physical-registration acceptance. Packaging and native acceptance
of these controls remain open; DESKTOP137 remains the installed build.

DESKTOP138 native checkpoint (source `cc1b62f`): installed manifest and strict
signatures passed, with DESKTOP137 retained as recovery. Native stock/path review
reported a complete miss against saved stock, opened Scene review, and then
reported possible engagement on 97 of 98 cutting segments against a temporary
10 × 10 × 8 mm stock volume. At 1 mm grid resolution the local drill/thread
preview reported 236 mm³ removed, 564 mm³ remaining and 66 conservative clearance
candidates. Three unresolved approach/travel lines (5, 11, 12) were excluded;
thread grooves and holder clearance remain unresolved. Native rest-stock save
was exercised; independent decompression verified the occupancy hash and all
800 cells, with 564 occupied. Receipts and screenshots are retained in
`/Users/wes/Downloads/carvera-desktop138-20261004/`. Operator stores/configuration
were restored; all eight stores still matched after relaunch, and Live viewing
returned with fresh reported Idle/T1/TLO and camera. No upload or motion occurred.
This closes the bounded native stock-alignment/calculation/save checkpoint, not
the full simulation requirement or physical qualification.

Native review exposed two usability defects: computed results stayed below the
viewport, and saving rest stock replaced the computed summary. Source now reveals
results after layout when the operator is still in the same task, preserves the
summary with a separate save receipt, and uses readable stock-bound text instead
of a missing arrow glyph. Installed acceptance of these source changes is open.

Result/save UX regression passed the real workbench calculation, saved snapshot
reconstruction, preserved summary and no-machine-command assertions (1 passed,
1 existing locale warning; 13.25 s). Ruff lint/format and diff checks passed.
The external-volume startup timeout and initial JSON list/tuple assertion failure
are retained alongside the final passing log in the DESKTOP138 evidence folder.
The source UI fixes await packaging/native acceptance.

DESKTOP139 native checkpoint (application source `9baf389`, navigation regression
revision `0f403c2`): installed manifest and strict signatures passed, with
DESKTOP138 preserved as recovery. Computation revealed the result summary in the
visible report area; native rest-stock saving preserved that summary and displayed
a separate save receipt. Independent decompression verified 800 cells, 564
occupied and 236 removed, the occupancy digest and the loaded program hash. Three
source scenarios passed: remaining on Simulation, moving to Operations and moving
to Scene while calculation finishes. Completion did not steal the selected task.
Receipts and screenshots are retained in
`/Users/wes/Downloads/carvera-desktop139-20261004/`. Normal operator stores and
configuration were restored; all eight stores matched after relaunch. Live viewing
returned with fresh reported Idle/T1/TLO 50.480 mm and Ubuntu camera. No upload or
motion occurred. This closes result-reveal/save-summary UX acceptance only; full
material removal, holder clearance, thread grooves, physical qualification and
the original 25 complete workflows remain open.

Tab-switch focus checkpoint: outgoing keyboard ownership is released through
Kivy's keyboard-owner registry and ancestor chain, avoiding a walk over every
control in the old page. Persistent toolbar focus remains active and field drafts
are preserved. Three focused navigation regressions passed (17.55 s); Ruff
lint/format passed. The first attempt's window-parent loop, subsequent storage
read stall and process samples are retained in the DESKTOP139 evidence folder
and `/tmp/carvera-focus-stall.txt`. This removes an avoidable traversal; it does
not establish the cause or resolution of the reported multi-second stall.
Packaging and native responsiveness acceptance of the focus change remain open.

Navigation timing source checkpoint: tab selection now retains bounded phase
timings for history, focus release, page activation and styling, plus separate
next-clock-turn and window-flip observations. Periodic UI refreshes retain their
own bounded totals and readiness/tool/simulation subphases. Machine connection
health displays the timings; the existing Spindle diagnostics export includes
both records and their limits. Capture performs no disk I/O or machine commands.
Failed and superseded selections cannot claim a later render observation.
The final source suite passed 21 tests (138.58 s, one existing locale warning),
including navigation history, focus preservation, event binding and export
readback. Ruff lint/format and diff checks passed. The first run's seven pure
passes and three Kivy tooltip/font startup timeouts are retained in
`/tmp/carvera-navigation-timing-tests.log`; passing output is in
`/tmp/carvera-navigation-timing-final-tests.log`. See `ui-responsiveness.md`.
DESKTOP140 predates this instrumentation; packaging/native workload measurement
and resolution of the reported stall remain open. No original requirement closes.

Combined recording/navigation source checkpoint (`02903ca`): integrated timing
retains camera-writer shutdown and measures active replay refresh separately.
The combined recording/setup/job/camera/navigation/export suite passed 84 tests
(95.65 s, one existing locale warning). Receipt:
`/tmp/carvera-recording-navigation-combined-tests.log`. Ruff lint/format and diff
checks passed. This remains a source checkpoint; neither recorded-run native
acceptance nor the tab-freeze requirement is closed.

Historical restoration source checkpoint: retained fixture/vise/tool assets now
restore into an explicitly labeled local preview, with archived-cutter selection
and reversible previous-scene restoration. Artifact preparation runs off the UI
thread and stale selections cannot publish. Exact original program bytes and
normalized inspector identity are validated separately. The final affected suite
passed 80 tests (67.30 s); wide/narrow renders were reviewed. See run-recording.md.

Retina dimension diagnostics exposed repeated test-window growth: framebuffer
pixels were being restored through a logical-size setter. Tests now retain
Window.system_size, and application close saves logical window dimensions
independently of widget dp scaling. This source correction does not prove the
reported tab stall resolved. Failed diagnostics remain preserved.

DESKTOP141 artifact verification passed at 2026-10-05T05:41:37Z: source revision
be8c6476735c0fee4077546ef517fbb92c803592, application checkpoint 02903ca, version
2.1.0-DESKTOP141. Independent source/staged/built checks reported no mismatches
(452/455/455 files); strict signature verification passed. Receipt:
/Users/wes/Downloads/carvera-desktop141-20261005/built-verification.json.
Later installed verification at 2026-10-05T06:06:44Z confirmed DESKTOP141,
455 installed files without mismatches and strict signatures. Receipt:
/Users/wes/Downloads/carvera-desktop141-20261005/artifact-verification.json.
Historical restoration and logical-size changes are later source work and are
not in this package. No original requirement is closed by these checkpoints.

DESKTOP142 artifact checkpoint: build process completed with exit zero. Independent
verification at 2026-10-05T07:12:54Z checked source revision
`88d31dd35209fcf970fd508e4bf302265225e3f4`, 455 source files and 458 staged/built
files without mismatches; strict signatures and version checks passed. Receipt:
`/Users/wes/Downloads/carvera-desktop142-20261005/built-verification.json`.
Installation was not attempted: the native computer-use bridge failed to start
both before and after a session reset. The existing installed controller was
not quit or replaced. The corrected setup binding, newer compact replay/camera
controls, async diagnostics export and mapped bank comparisons are later source.

DESKTOP143 now builds from a separate frozen checkout at `8a695a5`, including
those later changes. Its owned process is retained for subsequent terminal
readback and verification; starting the build does not establish a usable artifact,
installation, native responsiveness or physical workflow qualification.

DESKTOP143 artifact verification passed at 2026-10-05T07:43:29Z: source
`8a695a5b089683b40ac91bd47d4247fff5828f61`, 456 source files and 459 staged/built
files without mismatches, matching version and strict signatures. Receipt:
`/Users/wes/Downloads/carvera-desktop143-20261005/built-verification.json`.
Installation remains unattempted. Native access subsequently recovered; installed
DESKTOP141 displayed connected/Idle, fresh reported telemetry and Ubuntu camera.
That observation does not qualify the newer source or physical setup.

Direct scene interaction source checkpoint: exact indexed-triangle selection runs
off the UI thread and rejects stale scene/view results. Stock/vise handles create
XY or Z placement drafts with grid snapping, retaining the existing reviewed
apply/cancel and per-machine persistence path. Full homogeneous unprojection
replaces unsuitable affine matrix helpers. The focused interaction suite passed
22 tests (46.95s, one existing locale warning); existing setup-editor regressions
passed in the earlier combined run. Failed projection attempts and test-fixture
errors remain in `/tmp/carvera-scene-interaction-tests.log` and
`/tmp/carvera-scene-interaction-final-tests.log`. Both architecture contracts
passed (216 files, 936 dependencies). See scene-interaction.md for remaining scope.

Final scene/window-frame checkpoint: 23 focused tests passed (77.37s, one
existing locale warning), including a real rendered-stock handle drag into a
reviewed draft, cancellation and task visibility. Window-space overlay and touch
conversion now share the exact GL viewport origin; the earlier visual offset was
corrected. Screenshot `/tmp/carvera-scene-handle0004.png` was reviewed. Final
receipt: `/tmp/carvera-scene-window-frame-tests.log`. Ruff lint/format and both
architecture contracts passed. Compact interaction controls precede the component
inspector. Native installed acceptance and the remainder of requirement 4 stay open.

Vise rotation source checkpoint: 28 combined tests passed, with actual projected
ring gestures about the registered CAD pivot and reviewed apply/cancel/save.
Twelve pure checks passed after normalizing angular vectors for overflow safety.
The compact Scene panel now exposes independent translation/angle snap controls.
The source render was reviewed; both import contracts passed. Receipts and
remaining scope are in scene-interaction.md. DESKTOP144 is building from frozen
`4aa016989ab2303f7fac15e945f7b7d7e1a9646f` and does not include this later rotation
work. No original requirement closes at this source checkpoint.


Displayed cutter/frame source checkpoint: actual shader-transformed cutter/holder
triangles participate in selection with machine CAD shown or hidden. Clip-range
selection and geometry/view identity checks reject stale results, including a tool
replacement using the same number. Frame selected computes bounds off the UI thread
and preserves a camera adjustment or task change made during the request. The
combined interaction suite passed 35 tests (173.86s); the later task-context guard
has a focused regression receipt in `/tmp/carvera-framing-context-tests.log`.
See scene-interaction.md. These changes are later than DESKTOP144's frozen source;
installed acceptance and the remainder of requirement 4 remain open.


Final review added a Scene-task guard to asynchronous framing. Its focused test
process is still live but has not reached collection: sampling shows Python startup
blocked in a filesystem directory read. Receipt log:
`/tmp/carvera-framing-context-tests.log`; process sample:
`/tmp/carvera-framing-startup-sample.txt`. This added regression remains OPEN;
the earlier 35-test result does not prove the later guard. Local Ruff lint/format,
diff checks and both architecture contracts passed after the guard was added.
DESKTOP144's original build remains live in code signing; no replacement build or
installation was started. A fresh native observation still showed DESKTOP141,
Idle, fresh reported telemetry and camera. No machine commands were issued.


Final scene context/identity source acceptance: four focused tests passed (92.36s)
and exited zero, closing the added task-change framing regression. The cutter
inspector describes the displayed mesh identity and flags a different pending tool,
rather than attributing the requested tool's dimensions to old geometry. Receipt:
`/tmp/carvera-frame-inspector-final-tests.log`. The earlier fixture timeout and
cleanup failure remain preserved. Ruff and both architecture contracts passed.
Stock/general rotation and installed scene interaction acceptance remain open.


Oriented-stock backend checkpoint: fixed Z rotation/pivot now carry through cell
centers, sweep range selection, continuous material removal, rest-stock vertex and
normal rendering, clone/target comparison and schema-2 rest-stock snapshots. The
combined engine/preview suite passed 41 tests (1.32s); both import contracts and
Ruff checks passed. Receipt: `/tmp/carvera-oriented-stock-render-final-tests.log`.
Scene declarations/editor/persistence, job/recording setup binding and facing/path
integration have not yet adopted the parameter. Requirements 4 and 20 remain open.


Declared stock orientation integration: center-pivot program-Z rotation now flows
through the Scene editor/schema-2 save/restart, declared stock mesh/wireframe,
simulation context/calculation/rest-stock reconciliation, portable job declarations,
recording bindings, historical geometry and copied facing footprint. Legacy Scene
schema 1 defaults to zero and is migrated only on save. Geometry, persistence,
custody and reviewed editor source tests passed; see scene-interaction.md for exact
receipts. AABB engagement review remains conservative. Direct rotation gestures,
tilted frames and installed/native workflow acceptance remain open.


Direct stock rotation gesture source checkpoint: the projected ring uses the declared
stock center even with asymmetric rest geometry. Snapped release opens a reviewed
stock-angle draft; Apply persists, Cancel preserves setup, retained drafts are not
overwritten and no controller commands are sent. The combined interaction suite
passed 40 tests (179.40s); the additional residual-pivot/retained-draft check passed
(15.09s). The source render was reviewed; Ruff and both import contracts passed.
Receipts are in scene-interaction.md. Installed acceptance and the rest of requirement
4 remain open; the original DESKTOP144 build was not restarted or replaced.

Nominal surface-reference and measurement source checkpoint: retained source
triangle/point/normal references reject stale geometry/setup/cutter/pose. Unit-aware
surface review calculates ball-center approach, contact, search limit and retract,
with explicit winding reversal and normal/axis travel. A projected scene line hides
with its group/task and is discarded on changed setup/geometry/pose. Signed
local-plane deviation requires an explicitly supplied registered compensated
ball-center position; no firmware trigger is silently substituted. No transport,
offset or datum mutation exists in this planner. The combined engine/interaction
suite passed 53 tests (206.48s, one existing locale warning), before final layout
and overlay-visibility refinements. Receipt: `/tmp/carvera-surface-measurement-tests.log`.
Two final review tests passed (18.05s), followed by two narrow-window checks
(15.33s); wide/narrow source renders were reviewed. Ruff and both architecture
contracts passed. Installed/native acceptance remains separate. See scene-interaction.md.
Requirements 4, 11 and 12 remain open.

DESKTOP144 artifact verification passed at 2026-10-05T09:15:13Z: frozen source
`4aa016989ab2303f7fac15e945f7b7d7e1a9646f`, 461 source and 464 staged/built files
without mismatches, matching version and strict signatures. Receipt:
`/Users/wes/Downloads/carvera-desktop144-20261005/built-verification.json`.
Installation was not attempted; DESKTOP141 remains installed. Later rotation and
nominal surface-measurement work are absent from DESKTOP144.

Retained surface inspection source checkpoint: Scene planning now saves immutable
nominal/setup declarations; Setup opens retained feature/receipt history, signed
normal limits and repeat statistics. Raw triggers and missing registration or
compensation references remain unevaluated. Local records identify operator-entered
evidence and the explicit coordinate frame; the content hash is not calibration or
physical-registration proof. First-load/save/reload run off the UI thread, duplicate
gestures are bounded, closed views do not reopen and feature changes clear inputs.
The combined suite passed 34 tests (97.13s); three later reload/UI checks passed
(22.71s). See surface-inspection.md for receipts, scope and remaining work.
Installed/native acceptance, transport/measurement qualification and requirements
11/12 remain open. DESKTOP141 remains installed.

Inspection exchange/report source checkpoint: exact JSON-normalized feature/receipt
bundles, readback-hashed exports, signed-plane CSV and printable HTML reports are
integrated into the records view. Selected/all-feature export and reviewed import
were exercised in source UI tests. Import rechecks reviewed source bytes, rejects
identity conflicts and merges independent receipts idempotently without changing
machine setup/offsets. The final combined suite passed 38 tests (23.64s), with later
report-column and all-feature scope checks. Offline print QA corrected stacked
metrics and appendix/table ordering; both final pages were reviewed. Browser
local-file navigation was blocked, so browser rendering remains unverified.
See surface-inspection.md for exact receipts. Installed/native and physical
acceptance remain open; the original 25 complete workflows are not closed.


DESKTOP145 installed/native scene checkpoint: source `33de5ab` was independently
verified and installed at 2026-10-05T10:26:29Z (469 installed files, no manifest
mismatches; built/installed/recovery strict signatures passed). Native component
picking selected stock triangle 10 with +Z winding normal. Surface measurement
review displayed nominal surface, ball-center, approach/retract and search-limit
coordinates; local preview and Frame selected were exercised, leaving Scene hid
the overlay, and Fit view restored full machine framing. All nine operator-store
baseline entries still matched after review. Reported Idle/T1/TLO 50.480 mm, zero
RPM/feed, fresh telemetry and live camera were observed. Receipt:
`/Volumes/Wes Storage/Archives/Downloads/carvera-desktop145-20261005/native-scene-measurement-acceptance.json`.
No explicit motion/upload/offset/calibration/tool-change command was issued. This
closes this bounded picking/planning/framing UI checkpoint; native rotation/drag,
retained inspection exchange, measured registration and physical probing remain
open. Later operation highlighting (`3bf0ff5`) is absent from DESKTOP145.


ATC coordinate-readback source checkpoint: explicit M889 dispatch and bounded
header/Tool/ok collection now integrate with a lazy six-row Setup panel. Local
assignments, configuration coordinates and unknown physical contents remain
distinct. Reconnect, timeout, stale/busy state, failed transport and ambiguous
response checks passed. Final workspace/receive/navigation/pocket suite: 48 passed
(60.89 s); narrow/wide source renders reviewed. See atc-inventory.md for exact
receipts and limits. Installed/native query, slot overlay and physical tool/pocket
reconciliation remain open; requirement 8 is not closed.


ATC/scene source verification follow-up: retained receipt exchange passed 52
engine/transport tests and two narrow/wide historical UI checks. The complete
scene/panel run passed 34 test bodies with one test-mock teardown error; its
corrected exact visibility/cache regression passed separately, including finite
empty-bounds framing. Failed logs remain retained. Source now prevents periodic
visibility synchronization from triggering scene edits and fits cached rendered
bounds. Native ATC receipt/overlay acceptance and the reported tab freeze remain
OPEN. See atc-inventory.md and ui-responsiveness.md for exact receipts.


DESKTOP148 installed/native ATC checkpoint: frozen source
`787841a5ad304e83c01cc174753aee7e5ce98520`, version 2.1.0-DESKTOP148,
474 packaged/installed controller files without mismatches and strict signatures
verified. DESKTOP147 failed native startup on a missing packaging namespace;
it was preserved and DESKTOP145 was restored before fixing the dependency,
regenerating/checking the lockfile and rebuilding. DESKTOP145 recovery remains
available. Native connection to C1/2.1.0c at 192.168.0.79:2222 succeeded. Explicit
ATC readback returned seven configured positions (T0 through T6); native save,
independent hash/semantic validation, historical import and T6 pagination passed.
A reconnect invalidated current inventory without turning the saved record into
live evidence. All nine operator-store baseline entries still matched. Receipt:
/private/tmp/carvera-desktop148-20261005/native-atc-receipt-acceptance.json.
No motion, upload, tool change, offset or calibration was issued. Native target
overlay, physical rack registration/occupancy, camera-forward recovery and the
reported tab freeze remain OPEN. No original complete requirement closes.

Later source `ed05921` reveals connection controls directly from the header action
and reveals the configured-position panel when opened. A rendered regression
passed (18.26 s), verifying visible Connect profile controls, no machine commands
and cancellation of the reveal after changing tasks. Receipt:
/tmp/carvera-connection-navigation-final-tests.log. These entry-point improvements
are not in DESKTOP148 and require installed/native acceptance.

DESKTOP149 checkpoint: asynchronous artifact-path validation/selection and the
connection/ATC entry-point reveals are installed from 14498f8. Eleven focused
picker/navigation tests passed; installed manifest/signatures and native import/
entry-point behavior were verified. Native ATC target show/page/hide also worked,
but full-machine labels overlap and remain pending UI refinement. A connection-loss
popup recurred during path entry and automatically recovered; neither the tab
freeze nor broader native performance is closed. Camera remains unavailable.
All nine operator-store baseline entries matched. Receipt:
/private/tmp/carvera-desktop149-20261005/native-picker-navigation-acceptance.json.
No physical action/qualification or complete original requirement closes here.

DESKTOP150 installed/native checkpoint: source 968205698f6e9a7afe6e18839b37cd6cfdf1af4d,
474 installed controller files without mismatches and strict signatures passed;
DESKTOP149 recovery preserved. The full-machine ATC caption-overlap defect was
corrected and reviewed natively: T0-T5 captions are separated with anchored
leaders, T6 pagination and hide work. Four focused layout/rendered tests passed
(19.45 s, one SSL runtime warning); all nine operator-store entries matched.
Receipt: /private/tmp/carvera-desktop150-20261005/native-atc-caption-acceptance.json.
The app was left Live with fresh reported Idle telemetry, overlay hidden and
camera unavailable. Short-pane/orbit breadth and physical registration/occupancy
remain OPEN; no original complete requirement closes. The receive-path blocking
storage audit is recorded in ui-responsiveness.md for the next implementation.


Telemetry persistence responsiveness checkpoint: the receive-thread blocking
storage path is replaced by a bounded background writer, with gap/loss/error and
shutdown observations displayed/exported in Spindle diagnostics. The final
affected suite passed 34 tests (15.57 s), including deliberately stalled storage
while status parsing and a UI-clock age read proceed. See ui-responsiveness.md for
receipts and durability limits. This is source validation; the native intermittent
freeze and all original complete requirements remain open.


DESKTOP151 installed/native telemetry checkpoint: frozen source
8d533eea02a7dd91ea587b61a27dadc8e7444827; installed at
2026-10-05T14:04:06.293880Z, 475 files without manifest mismatches and strict
signatures passed. DESKTOP150 recovery is retained. Native Spindle review displayed
background storage counts; native export to internal storage completed and independent
JSON/log readback verified the persistence snapshot and connection generations.
All nine operator-store baseline entries still matched. Receipt:
/private/tmp/carvera-desktop151-20261005/native-telemetry-acceptance.json.

The native responsiveness defect is not resolved: opening the export picker timed
out twice before recovering; path paste again triggered connection loss and automatic
reconnection. The saved observation stream contains a 73.671468959-second maximum
arrival gap in the retained initial readback. Zero log-queue losses does not mean
zero missed machine packets. During the stall, sample 75986 shows the main rendering
thread and other Python threads waiting in PyEval_RestoreThread, with one Python
thread inside lstat. This is a concrete process-wide blocking lead, not proven
attribution to a particular Python source call. Process sample:
/private/tmp/carvera-desktop151-20261005/native-export-process-sample.txt.
Next: qualify the exact blocking path and isolate filesystem work from the process
where needed; a thread alone cannot protect against an operation holding the GIL.
Do not suppress the received-status timeout. The app was left Live/Idle with fresh
reported status, no program selected and camera unavailable. No motion, upload,
tool change, offsets or calibration were issued. No original requirement closes.


Isolated artifact-browser source checkpoint: folder resolution/listing, Jobs creation
and selection existence checks now run in a separate metadata-only process. Source
and frozen worker entry points dispatch before Kivy/controller imports. Requests
have a four-second deadline and cancel on changed navigation/dismissal; the parent
retains at most two helper slots, including kernel-blocked children that cannot yet
be reaped. Timeout/error messages keep selection disabled and permit another
location. Existing one-active/one-latest scheduling and stale-selection guards remain.

A RecycleView replaces the 250-widget cutoff with reusable visible rows, preserving
all matching entries, folder-first sorting and selected filenames. Text is left
aligned and shortened to fit. The 1,500-entry rendered regression reaches the last
entry, filters back to the first, verifies rebinding and rejects selection after
dismissal. Final combined suite: 23 passed (27.72 s, one SSL warning); later frozen
stream/bootstrap adaptation: seven engine/bootstrap tests passed (2.05 s). Receipts:
/tmp/carvera-isolated-picker-final-tests.log and
/tmp/carvera-isolated-picker-bootstrap-tests.log. Initial scheduled-metadata test
interference and missing RecycleView layout binding failures remain retained.

This contains a class of process-wide filesystem stalls; it does not prove the
precise source of DESKTOP151's lstat/GIL sample or resolve all native tab freezes.
Frozen helper output, installed folder timeout/retry, native recycled-row behavior
and connected tab responsiveness require separate verification.

DESKTOP152 installed checkpoint: eba45ca, 476 installed files without manifest
mismatches and strict signatures passed at 2026-10-05T14:17:27Z. Frozen metadata
helper pipe roundtrip passed. Native export picker opened and displayed 254 entries,
but scrollbar input caused an uncaught focus exception: ordinary ScrollView.scroll_to
expects a ClockEvent where RecycleLayout exposes a method. The app entered Python
finalization and remained live; process/exception evidence is retained in
/private/tmp/carvera-desktop152-20261005/. No native picker acceptance is claimed.

Recycled-row focus correction: the artifact viewport now reveals attached rows
without ordinary Layout trigger internals. Rows have centered text and a nine-dp
bar with content/bar scrolling. The strengthened regression reproduced the exact
native AttributeError before the correction; after correction, actual pointer
selection, scrollbar drag, focus, filtering/rebinding and post-dismissal protection
passed in the 1,500-entry list. Combined picker/focus/filesystem checks: 28 passed,
one existing SSL warning, 25.48 seconds. Before/after logs:
/tmp/carvera-recycled-focus-before.log and /tmp/carvera-recycled-focus-after.log.
Installed acceptance and overall responsiveness remain open.

DESKTOP153 installed/native picker checkpoint: frozen b3e3fc8bbaa75a535e4ddb4cba719ca74413accc,
476 installed files without mismatches and strict signatures passed at
2026-10-05T14:28:14.976856Z. Failed DESKTOP152 is preserved; DESKTOP151 recovery
remains available. Native scrollbar dragging reached the bottom of the 254-entry
external Downloads listing, focused row selection worked, internal-folder navigation
worked and two diagnostics exports completed with independent JSON/hash readback.
All nine operator-store entries still matched. The current native log contains
neither the recycled-focus exception nor a connection-loss event.
Receipt: /private/tmp/carvera-desktop153-20261005/native-picker-acceptance.json.

Connected empty-program Scene/Position/Setup/Console/Machine/Camera/Program/Spindle
navigation callbacks measured 1.18-1.88 ms, next-clock observations 9.67-84.50 ms,
and window-flip notifications 7.42-75.56 ms. The final 300-arrival diagnostics window
had zero gaps above its 0.5-second threshold and maximum interval 0.311 seconds.
These measurements exclude input dispatch and display presentation and do not
qualify loaded programs, camera/replay workloads or the complete tab-freeze issue.
Startup again timed out the UI bridge; the initial Job frame notification was
3.43 seconds after its callback. Startup sample is retained in the same folder.
Camera remains unavailable. No upload, motion, tool change, offset or calibration
was issued. This closes the bounded recycled-row focus/scroll/save regression;
all original complete requirements remain open.

Deferred-probing startup source checkpoint: the probing workbench is now created
on first request, with immediate settings readiness, current jog-mode controls,
retained edits and keyboard-jog restoration. 53 integration and 83 probing/config
checks passed; see ui-responsiveness.md for receipts and profiling limitations.
A test-isolation incident changed the operator's saved single-axis probe diameter
to 4.25 mm; the previous value is unknown and must be reviewed before probing.
The hard-coded settings path is corrected to respect KIVY_HOME and explicitly
isolated by the test fixture. No physical action occurred. Native/package
acceptance and all original 25 full requirements remain open.

DESKTOP155 installed checkpoint: frozen source
83781d67a8c0bfa181b38ac6dbeb88feab36d2d9, 476 installed files with no manifest
mismatches and strict signatures passed at 2026-10-05T14:59:24Z. DESKTOP154 recovery
is preserved. Same-process startup recovered after UI-bridge timeout; explicit
saved-profile reconnect, fresh reported Idle telemetry, Live mode, Scene and Setup
navigation were observed. Camera remains unavailable. All 18 entries in the expanded
post-incident operator-store baseline matched; this does not restore/prove the
unknown original probe diameter. Native first-use probing with a probe installed
remains open. The log contains a caught missing-MDI-history configuration traceback,
no AttributeError and no connection-loss event. Receipt:
/private/tmp/carvera-desktop155-20261005/native-startup-navigation-acceptance.json.
No motion/upload/tool change/calibration/offset action was issued. Startup and
complete responsiveness acceptance remain open; no original requirement closes.

Scene restoration reuse source checkpoint: machine-owned fixture/vise components
reuse the loaded assembly only after current bounded bytes and resolved asset
path match. Successful startup profile restoration no longer seeds the scene twice.
24 affected tests passed; all real CAD vertices/indices/canonical metadata matched.
See ui-responsiveness.md for receipts and limits. Native startup, background CAD
preparation and full responsiveness acceptance remain open.

DESKTOP156 installed/native restoration checkpoint: frozen source
b8c68f0fda0f95a46fce1f5a1fb70eecb48f4f19, 476 installed files without manifest
mismatches and strict signatures passed at 2026-10-05T15:08:23Z; DESKTOP155 recovery
retained. This launch returned through the UI bridge without a timeout (12.73 s,
including automation overhead). Saved machine, Saunders plate, Mod Vise and stock
rendered. Explicit saved-profile connection completed configuration readback;
Live/Scene navigation and fresh reported Idle telemetry were observed. All 18
post-incident operator-store entries matched. Camera remains unavailable; unknown
original probe D remains unresolved. Receipt:
/private/tmp/carvera-desktop156-20261005/native-scene-restoration-acceptance.json.
No physical action was issued. Background CAD preparation, comprehensive native
performance and all original complete requirements remain open.

Background machine-profile source checkpoint: startup and library selection
prepare CAD on one worker with one latest pending request. Current scene is
retained during preparation; publication rejects superseded generations, disposed
owners and changed scene/recording context. Library feedback distinguishes
preparing, loaded and rejected states. 52 broad affected tests and a later
10-test lifecycle run passed; see ui-responsiveness.md for receipts/limits.
No machine commands were issued. GPU publication and initial default loading
remain synchronous; installed/native acceptance and all 25 full workflows remain open.


DESKTOP157 installed/native profile checkpoint: frozen source 20dbf18, 476
installed files without mismatches and strict signatures passed; DESKTOP156
recovery retained. Saved assembly/scene restoration and native library selection
succeeded; explicit reconnect completed and Live/Scene showed fresh reported Idle
telemetry. Initial startup UI-bridge timeout still occurred and recovered in the
same process. All 18 post-incident operator stores matched, camera unavailable,
unknown original probe D unresolved. Receipt:
/private/tmp/carvera-desktop157-20261005/native-profile-acceptance.json.
No physical action or complete original requirement closes.

Subsequent source batches profile publication into one final rendered scene,
retaining hidden state and restoring visibility on failure. Twelve lifecycle
checks and 44 affected scene/workspace/profile-draft checks passed; native package
acceptance remains pending.
See ui-responsiveness.md. Overall responsiveness and all 25 full workflows
remain open.


DESKTOP158 installed/native publication checkpoint: source
5e5ee511db46d0eecb933f8bfc5d6f5176661f5a, installed at
2026-10-05T15:25:16Z; 476 files without mismatches and strict signatures passed.
DESKTOP157 recovery retained. Native Use machine profile reported Loaded and
rendered the saved machine, plate, vise and stock. Explicit reconnect completed;
Live/Scene and fresh reported Idle telemetry were observed. Same-process startup
again recovered after a UI-bridge timeout; the UI reported a 3.57 s largest
interval since launch, without attribution or input/presentation timing proof.
All 18 post-incident operator-store entries matched. Camera remains unavailable,
unknown original probe D remains unresolved, and the caught missing mdi_history
configuration traceback remains. Receipt:
/private/tmp/carvera-desktop158-20261005/native-profile-publication-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. This closes the
bounded installed profile-publication regression only; default CAD loading,
final GPU construction, comprehensive responsiveness and all 25 full workflows
remain open.


Deferred default-CAD source checkpoint: viewer construction performs no default
asset I/O; scheduled background preparation retains the schematic and rejects
changed owners/base profile/setup. Saved profile selection and workspace disposal
cancel/invalidate default publication. Blank CAD selections retain default
fallback semantics. Twenty lifecycle checks passed; see ui-responsiveness.md for
receipts. Forty-four affected regression checks passed; packaging/native startup and
complete responsiveness acceptance remain open. All original 25 full requirements remain open.


DESKTOP159 installed/native startup checkpoint: frozen source
de5f15bbefdca0ce4ffd4c0d2b087248945936c8, installed at
2026-10-05T15:33:16Z with 476 files without mismatches and strict signatures
passed; DESKTOP158 recovery retained. Saved custom assembly restored; native
profile-library selection reported Loaded and preserved machine/plate/vise/stock.
Fresh reported Idle telemetry and Live/Scene were observed. Initial UI-bridge
timeout still occurred and recovered in the same process; no startup speed
claim is made. Native default-only startup and transient loading-caption visual
acceptance remain open. All 18 post-incident operator stores matched. Camera
unavailable, unknown original probe D unresolved, caught missing mdi_history
traceback remains; no AttributeError or connection-loss event in the current log.
Receipt: /private/tmp/carvera-desktop159-20261005/native-default-preparation-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. Default CAD I/O is
removed from viewer construction; final GPU construction, other startup work
and comprehensive responsiveness remain open. All 25 full workflows remain open.


Profiled CAD-bounds source checkpoint: loaded groups are immutable indexed
snapshots with exact bounds prepared during loading, removing repeated CAD scans
from scene publication. Mutable geometry remains fully revalidated. All real
asset coordinates/indices/canonical metadata and complete scene bounds match the
previous implementation. 34 validation and 49 affected engine checks passed;
rendered/package/native acceptance pending. See ui-responsiveness.md for source
profiling, native sample and exact comparison receipts. No complete original
requirement or overall responsiveness gate closes.

The rendered scene/profile/default-preparation/interaction suite passed 50 tests
(64.62 s, one existing SSL warning). Receipt:
/private/tmp/carvera-geometry-snapshot-rendered-tests.log. Ruff/format/diff passed.
All 18 post-incident operator-store entries matched. Native package acceptance
and comprehensive responsiveness remain open.


DESKTOP160 installed/native bounds checkpoint: frozen source
e3909b717090764055582a0a05b35f3b62b72e76, installed at
2026-10-05T15:44:40Z; 477 files without manifest mismatches and strict
signatures passed. DESKTOP159 recovery retained. Native profile selection
reported Loaded; saved machine, Saunders plate, Mod Vise and stock rendered.
Live/Scene displayed fresh reported Idle, T1/TLO 50.480 and zero RPM/feed.
Startup again timed out the UI bridge and recovered in the same launch;
no comprehensive responsiveness claim is made. All 18 post-incident operator
store entries matched, camera remains unavailable and original probe D remains
unknown. Current log contains no AttributeError or connection-loss event.
Receipt: /private/tmp/carvera-desktop160-20261005/native-bounds-acceptance.json.
No upload/motion/tool change/offset/calibration was issued. This closes bounded
installed immutable-CAD publication acceptance only; overall responsiveness
and every original complete requirement remain open.


Camera recovery/diagnostics checkpoint: no local listener at the saved
127.0.0.1:18091 snapshot URL; camera Ubuntu peer 100.93.125.40 is online in
current Tailscale state. Read-only remote service inspection is waiting on the
existing account SSH authentication check opened in Chrome (session 5164).
No forwarding process or remote service change has been started.
Source camera failures now distinguish refused local forward/service, refused
remote port, timeout, DNS, TLS and HTTP access/path/service failures without
echoing request or exception details. Existing decoder messages are allowlisted.
20 camera regressions passed; Ruff/format/diff checks passed. Logs:
/tmp/carvera-camera-diagnostics-tests.log and
/tmp/carvera-camera-diagnostics-isolated-tests.log. A startup filesystem-stat
stall sample is retained in /tmp/carvera-camera-tests-sample.txt; the original
run eventually completed. New diagnostics are not installed; DESKTOP160 remains
the installed build. Camera live recovery and all full requirements remain open.


Command palette coverage/keyboard checkpoint: DESKTOP160 native Cmd+K opened
the palette, typed camera search filtered results, arrows changed selection
and Enter opened Camera. Native arrow selection exposed short result lists
falling to the bottom because row rebuilding preceded layout. Source now
reveals after layout, keeps fitting result lists at the top and uses the
shared DesktopScrollView. Eight additional actions route directly to Operations,
Simulation, Run record, Job package, View/playback and Live/Preview/Compare pose.
These route local controls only; they do not generate/upload/run a program.
Three pure command checks and one rendered keyboard/lifecycle/no-command check
passed; existing SSL warning remains. Receipts:
/tmp/carvera-palette-coverage-tests.log and /tmp/carvera-palette-rendered-tests.log.
New action coverage and scrolling fixes are not installed; native responsiveness
and complete contextual coverage acceptance remain open. Camera recovery still
waits on the existing Tailscale authentication check. No original requirement closes.


DESKTOP161 installed/native palette and camera checkpoint: frozen source
9ea6362bce66e1fd4ba458d45bc2434aee8cd719, installed at
2026-10-05T15:58:19Z; 477 files matched and strict signatures passed.
DESKTOP160 recovery retained. Native camera search/Down selection retained
short rows at the top; portable archive/Enter opened Job package; live machine
pose/Enter set Live view. The local camera refusal recovery message rendered.
Explicit saved-profile reconnect reported fresh Idle telemetry; machine, plate,
vise and stock rendered. All 18 post-incident operator-store entries matched.
Startup bridge timeout recovered in the same launch; no overall responsiveness
claim. Current log contains no AttributeError or connection-loss event.
Receipt: /private/tmp/carvera-desktop161-20261005/native-palette-camera-acceptance.json.
Initial packaging failed on missing msgfmt in non-login PATH; failed log retained,
then the same frozen source built with installed compiler PATH explicitly supplied.
Camera recovery still requires existing Tailscale authentication; original probe D
remains unknown. No upload/motion/tool change/offset/calibration was issued.
Bounded palette reveal/navigation and local-camera-error acceptance close;
complete contextual coverage, comprehensive responsiveness and all 25 requirements
remain open.


Repeat-array visualization source checkpoint: all declared stock instances render
in their machine frame with shared table motion and stock visibility. The active
stock retains independent editing and rest-stock geometry; other nominal instances
are explicitly display-only. Input/profile/single-stock changes clear the array;
historical preview/return retains the declaration and selected instance. Declared
arrays cannot acquire confirmed physical alignment through viewer configuration.
22 unit/rendered checks passed; 49 affected checks passed in a combined run that
exposed two derived-buffer restoration comparisons. Both historical cases and the
array workflow passed after correcting retained-state ownership (three passed).
See repeat-parts.md for logs and remaining scope. Package/native acceptance, full
WCS-aware simulation, offset transactions and every original complete requirement
remain open. No physical action occurred.


DESKTOP162 installed/native repeat-array checkpoint: frozen source
56923aad0700c250e9d8c9f5fe881632eaa5b66e, installed at
2026-10-05T16:17:38Z; all 479 manifest files matched and strict signatures passed.
DESKTOP161 recovery retained. Native Setup built a two-row/three-column G54–G59
array, previewed Part 1 then Part 6, and hid the other instances while preserving
the active stock. No plan was saved. Restart restored the saved machine, Saunders
plate, Mod Vise and stock; final Live view showed fresh reported Idle/T1/TLO 50.480,
zero RPM/feed and Ubuntu camera frames. All 18 post-incident store entries matched.
Receipt: /private/tmp/carvera-desktop162-20261005/native-repeat-array-acceptance.json.
The pending Tailscale check completed; remote camera HTTP 200 was verified and a
localhost-only forward restored. Standard SSH rejected a stale known-host key; it
was not bypassed. The Tailscale wrapper independently verifies the node key advertised
by its coordination server. Forward session 74745 is live; automatic forward
lifecycle management remains open. Startup again timed out the UI bridge before
recovering in the same process; full responsiveness remains unresolved. Native
review also found excessive planner height and result placement below the viewport.
Native plan save/restore, native archived-array restoration, WCS-aware multi-stock
simulation and physical qualification remain open. No upload/motion/tool change/
offset/calibration was issued. No original complete requirement closes.

DESKTOP163 installed/native planner checkpoint: frozen source
8bdeaad4ca42d62f509c71a6536ea56b963e540e, installed 2026-10-05T16:37:50Z;
480 files matched and strict signatures passed. DESKTOP162 recovery retained.
Native Array layout / Review controls, two-part build/preview, automatic review
transition and missing-program simulation guard were exercised. Restart restored
the saved actual-scene draft; Live displayed fresh reported Idle/T1/TLO 50.480,
zero RPM/feed and camera frames. All 18 post-incident operator stores matched;
no repeat plan was saved. Receipt:
/private/tmp/carvera-desktop163-20261005/native-repeat-review-acceptance.json.
First launch observation timed out and recovered; comprehensive responsiveness
remains open. A misleading old active-stock warning was corrected subsequently
in source (rendered regression passed); that wording correction is not installed.
Native calculation with loaded program/tools, persisted multi-stock results,
frame-aware playback and registered machine workflow remain open. Architecture
contracts were not rerun because importlinter is absent from this isolated runtime.
No motion/upload/tool change/offset/calibration occurred. No original complete
requirement closes.


DESKTOP164 native declared-playback checkpoint: frozen source
`cb14960e057a0956b085cfad7cdded7396a62a19`, installed at
2026-10-05T16:49:28Z; 481 files matched and strict signatures passed.
Native two-part G54/G55 preview enabled declared-frame path/cutter playback,
excluded one unresolved initial line, moved the displayed cutter to the second
stock, reached line 13 and restored original file playback. Restart discarded
the unsaved array/program and restored the saved plate, vise and stock. Final
Live showed fresh reported Idle/T1/TLO 50.480, zero RPM/feed and camera frames.
Receipt: /private/tmp/carvera-desktop164-20261005/native-repeat-playback-acceptance.json.
Seventeen post-incident operator-store entries matched; program-places.json
changed through the intentional local-file inspection. Original probe diameter
remains unknown. No upload/motion/tool change/offset/calibration was issued.
Native multi-stock calculation/persistence and physical qualification remain open.
Connection loss/reconnect coincided with picker navigation; Return to Live
observation later took 23.55 seconds. Comprehensive responsiveness is not closed.

Native review found contradictory playback state text: the action reported
declared-WCS mode while the stock note retained its old single-frame warning.
Source now derives the stock note from the actual viewer state on enable/restore.
Two rendered repeat-part/playback regressions passed (44.64 s, existing SSL warning),
including exact original path restoration and no-machine-command assertions;
Ruff/format/diff checks passed. Log: /tmp/carvera-repeat-playback-status-tests.log.
This correction is later source and is not installed in DESKTOP164.
No original complete requirement closes.


Multi-stock persistence/compact review source checkpoint: array calculations now
retain per-part compressed occupancy in addition to rendered geometry. Results &
files saves/loads a bounded .cvstocks bundle with exact program/array/profile/tool/
workholding/CAD context, occupancy integrity, placement/volume/resolution checks
and shared voxel/face limits. Assets are freshly hashed off the UI thread. Atomic
saving preserves previous files on pre-publication cancellation. Loading builds
all stocks before publication and rejects changed context or late cancellation.
Collision candidates/summary quantities persist; detailed contact geometry is
explicitly unavailable after load. Active-part viewing does not invalidate results.
Array layout, Review & simulate and Results & files separate controls from reports;
preview actions share a compact row and calculation reveals results only when the
operator remains on the review task.

Affected engine/rendered/historical checks passed 45 tests (31.38 s, existing SSL
warning); final strengthened archive/publication checks passed 11 tests (18.67 s),
including changed/cancelled load publication and previous-file preservation.
Logs: /tmp/carvera-repeat-result-final-corrected-tests.log and
/tmp/carvera-repeat-result-publication-tests.log. Ruff/format/diff checks passed.
The original report-equality assertion was corrected to reflect explicitly omitted
detailed contacts; its failure remains in /tmp/carvera-repeat-result-unit-tests.log.
The initial broad invocation named a missing test file and ran no tests; that
receipt remains in /tmp/carvera-repeat-result-final-tests.log. Operator readback:
/tmp/carvera-repeat-result-operator-readback.json; the program-places change already
recorded during DESKTOP164 native file inspection remains the only changed entry.
Original probe diameter remains unknown. DESKTOP164 is still installed; this
checkpoint awaits packaging/native result exchange and layout acceptance. Physical
workflows and all original complete requirements remain open.


DESKTOP165 native multi-stock checkpoint: frozen source
`4ece4660367789e03f3a875d637abf9092295292`, installed at
2026-10-05T17:06:46Z; 482 manifest files matched and strict signatures passed.
Native two-part G54/G55 calculation at 1 mm resolution reported 41 mm³ removed
and 15,959 mm³ remaining per stock. Save and matching-load retained both reports,
rendered stocks and explicit missing-detailed-contact qualification. Independent
bundle and occupancy verification confirmed 16,000 binary cells per stock and
15,959 occupied cells, exact placements and hashes. Receipt:
/private/tmp/carvera-desktop165-20261005/native-repeat-result-acceptance.json.
The temporary simulation-only tool profile was removed by restoring exact original
profile bytes while closed. Restart restored the saved actual scene; Live showed
fresh reported Idle/T1/TLO 50.480, zero RPM/feed and camera frames. Seventeen store
entries matched; the recent-program entry changed intentionally. Original probe
diameter remains unknown. No upload/motion/tool change/offset/calibration occurred.
The picker initially entered Downloads; cancellation left helpers stopping and
briefly rejected the local result folder. Retrying the same folder recovered.
Full responsiveness remains open. This closes bounded native multi-stock
calculation/save/load acceptance, not physical registration or the original full
multiple-WCS requirement.

Artifact-browser follow-up: accepted folders are reused within the session per
artifact suffix set, shared by save/load. Invalid callbacks and mere navigation
do not replace the last accepted folder. The rendered picker suite passed all
12 tests (16.88 s, existing SSL warning), including accepted-folder reuse,
artifact-type separation and rejected-callback preservation. First-use fallback
now explicitly isolates its session state in the test; the original failure is
retained in /tmp/carvera-picker-accepted-folder-tests.log. Final receipt:
/tmp/carvera-picker-accepted-folder-final-tests.log. Ruff/format/diff checks passed.
This source change is later than DESKTOP165 and awaits installed/native acceptance;
it reduces repeated visits to unrelated storage but does not close overall
responsiveness or filesystem-helper lifecycle recovery.


DESKTOP166 installed/native picker checkpoint: frozen source
`1f3722979b346f109a5e58f9db0f7d049400ce90`, installed at
2026-10-05T17:20:08Z; 482 manifest files matched and strict signatures passed.
Native profile export to the owned receipt folder succeeded; Import opened that
accepted folder immediately with the exported file visible. Import was cancelled.
Independent exported JSON matched the current profiles; all 18 operator-store
entries matched the pre-update baseline. Native Downloads-to-local-folder
navigation recovered without manual retry in this run. Live showed fresh reported
Idle/T1/TLO 50.480, zero RPM/feed and camera frames. Receipt:
/private/tmp/carvera-desktop166-20261005/native-picker-acceptance.json.
DESKTOP165 recovery retained. The initial build invoked the wrong runtime and
exited because PyInstaller was missing; the corrected isolated dependency runtime
built successfully. Both logs are retained. No upload/motion/tool change/offset/
calibration occurred. Accepted-folder reuse native acceptance closes; pathological
blocked-storage recovery, persistent folder preferences and broader responsiveness
remain open. No original complete requirement closes.


DESKTOP167 native shared-header checkpoint: frozen source
`52e09b85c75bcfe7928db060856681e680aa4ed5`, installed at
2026-10-05T17:28:17Z; 482 manifest files matched and strict signatures passed.
Native standard-width review confirmed nine top tabs in one row, status/profile
metadata and connection/hold/STOP on one row, readable setup evidence and more
visible Setup controls. Narrow layout remains rendered-test evidence only.
Receipt: /private/tmp/carvera-desktop167-20261005/native-header-acceptance.json.
The same build recovered from a filesystem-open stall without restart; its sample
is retained. All 18 operator-store entries matched; Live showed fresh reported
Idle/T1/TLO 50.480, zero RPM/feed and camera frames. DESKTOP166 recovery retained.
Setup and Return-to-Live combined native input/AX/screenshot calls took 57.13 and
60.89 seconds respectively. These durations do not isolate app/input/observation
latency; full responsiveness remains unresolved. Next diagnostic separates those
phases and inspects application navigation timings. No upload/motion/tool change/
offset/calibration occurred. Layout acceptance closes at standard width only;
no original complete requirement closes.


DESKTOP167 responsiveness diagnosis: native diagnostics exported and independently
read at 2026-10-05T17:36:24Z. Setup callback was 1.17 ms, next clock turn 467.71 ms
and flip notification 455.51 ms; Monitor callback was 1.25 ms, clock turn 41.53 ms
and flip 37.35 ms. The retained 60 recent refreshes peaked at 5.74 ms, but 2,210
older refreshes had been evicted. Separately measured Scene native calls took
0.52 s input, 1.17 s accessibility and 0.81 s screenshot. This does not explain
previous combined minute-long calls or prove input dispatch/presentation latency.
The picker timed out on Downloads and initially on the owned folder; same-folder
retry recovered. A transient controller reconnect also recovered in the same
process. Native export receipt, JSON and process sample are retained in
/private/tmp/carvera-desktop167-20261005/; navigation-diagnosis-receipt.json
records the exact export digest and confirms all 18 operator stores matched.
No upload/motion/tool change/offset/calibration occurred.

Source follow-up preserves the slowest callback, clock-turn and flip observations
independently of recent-record eviction, plus the longest callback-start interval
with adjacent identities. Retention remains bounded; exports are independent
copies. Failed callbacks remain explicitly failed without invented render proof.
The Machine timing note now uses the session maximum refresh instead of the
recent ring maximum. Start intervals are cadence evidence, not causal evidence;
navigation intervals include operator idle time. Engine, rendered navigation and
async-export checks passed 17 tests (18.06 s, existing SSL warning), including a
five-second refresh exported after ring eviction. Ruff/format/diff checks passed.
Log: /tmp/carvera-retained-slow-timings-final-tests.log. This source change awaits
packaging/native acceptance; installed DESKTOP167 predates it. Overall freeze
resolution and all original complete requirements remain open.


DESKTOP168 native timing-retention checkpoint: source
`9dbc1fa4d67e2a7f4beaa202d364663595338088`, installed at
2026-10-05T17:40:33Z; all 482 manifest files matched and strict signatures passed.
DESKTOP167 recovery retained. The first native observation timed out during
startup; the same running process was subsequently observed without restart.
Native diagnostics export independently confirmed a 23.01 ms maximum refresh
(sequence 1) persisted after 553 records were evicted, outside the 60 recent
records. It also retained a 4.44 s startup refresh-start interval and 5.61 s
initial flip notification. These identify diagnostic intervals, not their cause
or screen presentation. Source-controlled slow-refresh export and failure
semantics passed the prior 17-test affected suite. Native Setup/Spindle switches
and export succeeded; folder navigation needed no retry in this run. Live showed
reported Idle, T1/TLO 50.480, zero RPM/feed and fresh camera/telemetry. All 18
operator-store entries matched. Receipts:
/private/tmp/carvera-desktop168-20261005/artifact-verification.json and
/private/tmp/carvera-desktop168-20261005/native-timing-acceptance.json.
This closes native session-maximum export acceptance only; root-cause diagnosis,
full responsiveness and all original complete requirements remain open.


UI stall-capture source checkpoint: an independent background monitor samples the
UI thread after a one-second missed heartbeat. It retains at most 20 episodes,
three samples per episode and 32 stack locations per sample, with recovery time,
heartbeat gap and last page context. Capture stores source basenames/functions/
line numbers only; no source reads, local values or full paths. Recovered-during-
sampling races are rejected; disposal cancels the heartbeat and signals worker
shutdown without joining on the UI thread. Signal diagnostics exports these
bounded observations. OS suspension, debugger pauses and GIL starvation remain
explicit alternative explanations; sampled locations do not prove root cause.
Engine/thread/export/rendered navigation checks passed 20 tests (14.84 s,
existing SSL warning); Ruff/format/diff passed. Log:
/tmp/carvera-ui-stall-capture-final-tests.log. Packaging/native capture acceptance
and overall freeze resolution remain open. DESKTOP168 remains installed.


DESKTOP169 native stall checkpoint: source
`48f2f819960ee8727076c44430b081dd6f1bd5cb`, installed at
2026-10-05T17:47:21Z; all 483 manifest files matched and strict signatures passed.
DESKTOP168 recovery retained. Existing Workshop Carvera profile was explicitly
connected; Live returned with fresh reported Idle, zero RPM and camera/telemetry.
Native diagnostics captured five recovered heartbeat episodes without artificial
machine actions. Startup samples were in Kivy drawing/buffer flipping (1.98,
1.26 and 1.14 s gaps). Two file-browser paste episodes were sampled in
clipboard_sdl2.get via TextInput.paste, with recovered heartbeat gaps 12.66 and
9.69 s. These locate a clipboard-related UI freeze; they do not establish the
cause of every prior tab delay. The background monitor may itself be delayed by
the GIL. Native export/readback verified bounded samples and recovery timestamps.
All 18 operator stores matched. Receipts and exact export digest:
/private/tmp/carvera-desktop169-20261005/native-stall-acceptance.json.
No upload/motion/tool change/offset/calibration occurred. Clipboard isolation and
native paste/cancellation/selection/undo acceptance are the next actionable fix;
startup rendering and overall responsiveness remain open. Native bounded stall
capture/export/recovery closes only this diagnostic checkpoint.

Async clipboard source checkpoint: modern workspace Fields on macOS use a
background pbpaste helper instead of SDL clipboard reads on the UI thread.
Reads have a two-second deadline, 1 MiB byte cap and two-helper concurrency cap;
helpers retain their slot until reaped. Text/cursor/selection/focus/attachment/
editable changes cancel or reject stale completions. Replacement uses existing
TextInput selection and insertion primitives, retaining normal filtering and
undo behavior; pending/error borders provide feedback. Non-macOS providers are
unchanged. Clipboard contents never enter diagnostics. Focused helper, blocked
read/clock, cancellation/supersession, selection/undo and existing keyboard tests
passed 24 tests (21.19 s, existing SSL warning). Log:
/tmp/carvera-async-paste-final-tests.log. Ruff/format/diff checks passed.
Installed native paste acceptance, startup rendering and overall responsiveness
remain open; this does not close any of the original 25 full requirements.

DESKTOP170 native paste checkpoint: source
`0e6f81ded724f4b7696425bf7b9d7dd8b9038159`, installed at
2026-10-05T17:59:33Z; all 484 files matched and strict signatures passed.
DESKTOP169 recovery retained. Native directory and filename paste were visually
read back; undo restored the empty filename field; diagnostics saved and read
back successfully. This session retained only two startup heartbeat episodes
(3.83 s resource/image lookup and 1.70 s profile scene construction), both recovered
before file-picker testing. No clipboard-stack episode was recorded during the
three native paste interactions. Input wrapper durations include input/tool
latency and do not measure isolated app response or prove every freeze resolved.
All 18 operator stores matched; Live returned with fresh reported Idle, telemetry
and camera. No upload/motion/tool change/offset/calibration occurred. Receipt:
/private/tmp/carvera-desktop170-20261005/native-paste-acceptance.json.
This closes the native directory/filename paste and undo checkpoint only.
Comprehensive clipboard behavior, error-message presentation, legacy fields,
startup rendering/scene construction and overall responsiveness remain open.

Prepared workholding checkpoint: loaded assemblies retain at most two immutable
workholding placements with prevalidated bounds. Neutral placement reuses loaded
CAD; worker preparation transforms selected or saved vise placement before profile
publication. Cache hits never wait for another placement's transform. Each render
constructs one scene per distinct assembly, instead of recomputing the same
machine/fixture/vise assembly up to three times. Stock geometry remains separately
constructed and never enters the placement cache. Focused geometry, async profile,
saved setup and historical scene checks passed 65 tests (24.43 s, existing SSL
warning). Log: /tmp/carvera-placement-preparation-final-tests.log.
The installed Saunders/Mod Vise asset source benchmark used the actual saved
placement: 30,012 workholding vertices, 0.150 s cold preparation and 0.022 ms mean
warm scene construction over 100 calls. This is source timing, not native UI
latency. Receipt: /private/tmp/carvera-placement-performance-20261005.json.
Native acceptance and overall responsiveness remain open; GPU construction,
uncached interactive placements and resource/image lookup can still block.

Render-buffer preparation checkpoint: immutable CAD snapshots retain at most two
exact work-offset/scale triangle-buffer frames. Buffers preserve indexed order,
normals, colours and unsigned-short limits; finite frame/overflow checks reject
invalid render coordinates. Cache hits do not wait for another frame's conversion.
Default and selected machine-profile workers warm these pure buffers before UI
publication. Renderer copies cached immutable buffers for GPU inputs rather than
re-translating every CAD vertex; mutable stock/schematic geometry retains its
existing path. Snapshot deepcopy/pickle preserve immutable geometry and omit
transient cache state. Profile publication rejects a changed program scale.
An exercised clearance-to-motion test found the operation card could be inserted
before its toolbar was attached; selection now attaches that toolbar first.
Final affected geometry/profile/default-load/inspection/section tests passed
81 tests (22.00 s, existing SSL warning), after the retained initial navigation
failure. Logs: /tmp/carvera-render-buffer-tests.log and
/tmp/carvera-render-buffer-final-tests.log. Ruff/format/diff checks passed.
Actual 370,746-vertex CAD source benchmark: 0.830 s cold worker preparation,
0.016 ms warm group lookup and 10.73 ms including mutable GPU-input copies over
100 runs. GPU construction and native latency are excluded. Receipt:
/private/tmp/carvera-render-buffer-performance-20261005.json.
This checkpoint is source-tested only. DESKTOP171 remains the separate c7a90f0
build waiting on external-volume signing writes; no second build was started.
Component import, uncached interactive placement, GPU construction, startup
image/resource work and comprehensive native responsiveness remain open.

Asynchronous component-selection checkpoint: fixture and vise CAD selection,
import and external saved-component restoration prepare profiles and render
buffers on independent background lanes. Each lane retains one active and one
latest pending request; replaced requests do not publish. Scene/profile/selection/
placement/scale changes reject late results, and disposal closes publication.
Loaded machine-owned components restore directly from the already prepared
assembly. External restoration waits until saved numeric geometry is restored
before preparing its frame. The current geometry remains visible while loading;
independent pending/error feedback prevents one completed component from hiding
another pending component or failure. No CNC commands are sent by this workflow.
Affected tests passed 26 tests (17.29 s, existing SSL warning), including blocked
worker/UI clock, bounded coalescing, independent lanes, stale results, import
registration, saved numeric restoration and retained pending/error feedback.
Log: /tmp/carvera-component-loading-final-acceptance-tests.log.
Ruff lint/format and diff checks passed. Import-linter is unavailable in this
runtime, so its architecture contracts were not rerun for this checkpoint.
This remains source-tested: GPU construction, native CAD import/selection and
overall tab responsiveness require installed verification. DESKTOP171 uses the
earlier c7a90f0 source and is not evidence for these changes. All original 25
complete workflows remain open.

Immutable CAD mesh-retention checkpoint: scene rebuilds retain each unchanged
immutable machine/fixture/vise mesh by snapshot identity, exact work-offset/scale
frame and visibility. Replacing a component rebuilds its group; hiding/showing,
removing/reintroducing or changing its render frame invalidates that group.
Mutable stock/rest stock remains uncached. Retained keys are bounded by scene
groups, and identity comparison avoids equality/hash traversal of vertex streams.
Absent geometry groups clear their instructions without clearing live/preview
marker contexts. Observed markers retain their meshes in unchanged frames and
reproject when work offset/scale changes. Uniforms and inspection geometry still
refresh independently of mesh construction.
Actual Kivy mesh-identity/coordinate tests and affected component, section,
recording, scene-persistence and pose-context checks passed 44 tests (38.70 s,
existing SSL warning). Log: /tmp/carvera-gpu-mesh-reuse-acceptance-tests.log.
Initial failures are retained in /tmp/carvera-gpu-mesh-reuse-tests.log: a new
coordinate assertion assumed zero work offset, and the local viewer fixture left
deferred default CAD loaders to start during later integration clock pumping.
The fixture now explicitly cancels those unneeded loaders and declares its
coordinate frame. Ruff lint/format and diff checks passed. Installed/native
responsiveness remains open; this does not measure native GPU latency or close
any original full capability.

Retained-build relocation completed at 2026-10-05T18:34:06Z. Owned build roots
160–163 were copied to /Volumes/Wes Storage/CarveraBuilds/retained-builds,
independently hash/mode/link/directory verified, and their original paths retained
as symlinks. Receipt: /private/tmp/carvera-build-relocation-20261005.json.
DESKTOP171 advanced past PyInstaller signing to the build script's final signing
process (PID 94415); build PID 84711 and exec session 18059 remain live. Receipt:
/private/tmp/carvera-desktop171-final-signing-wait-20261005.json.
No duplicate build, package installation or CNC command occurred in this checkpoint.

Reviewed setup preparation checkpoint: stock/origin and vise Apply requests warm
all distinct selected CAD assemblies and placement/render buffers on background
workers before the existing reviewed local transaction publishes geometry or saves.
Workspace-owned bounded lanes retain one active and one latest pending request
per editor kind. Repeated activation does not create another worker. Pending
feedback disables Apply while Cancel, Keep draft and Reload remain available.
Closing/reloading invalidates publication; changed raw fields, baseline geometry,
profile/component identity, render scale or disposed ownership reject results.
Preparation failures retain the active scene and editable draft. Existing optimistic
saved-file checks and rollback semantics remain in the publication transaction.
Completed surface selections now retain their viewport identity so resizing cannot
revive an old measurement reference merely because immutable CAD meshes were reused.
Final setup/gesture/drawing/rollback and blocked-worker rejection tests passed
60 tests (84.37 s, existing SSL warning); 11 focused asynchronous cases also passed.
Log: /tmp/carvera-setup-preparation-final-tests.log. The initial failure log remains
/tmp/carvera-setup-preparation-tests.log: an obsolete drawing caption expectation
and a missing completed-pick viewport guard. Ruff lint/format/diff checks passed.
Native preparation, GPU construction and comprehensive responsiveness remain open.

DESKTOP171 build session 18059 completed with exit 0. Its frozen source remains
c7a90f09ef7119ec7c4f8f6d84067f8e5dfe9d7b; it excludes subsequent source changes.
Artifact verifier session 19706/PID 99455 remains live waiting on an external-volume
read. No installation occurred before successful independent artifact verification.
DESKTOP170 native pre-install export at 2026-10-05T18:46:44Z retained fresh reported
Idle, RPM/feed 0 and camera updates, but telemetry persistence had stopped with
ENOSPC: 8,583 written, one failed and 3,784 rejected records at export. Export:
/private/tmp/carvera-desktop170-20261005/native-before-desktop171.json.
All 18 tracked operator stores still match their baseline hashes. Failed persistence
and the missing run segment remain open; fresh live telemetry does not recover it.
Next recording action is explicit persistence recovery with a retained gap record.
No upload, motion, tool change, offset change or calibration occurred here. The
original 25 complete capabilities remain open.

Explicit recording-recovery checkpoint: the Spindle diagnostics panel can start
one asynchronous new recording segment after a drained writer failure. Recovery
creates a unique segment exclusively, flushes and independently reads back its
gap record before the controller publishes the replacement writer. Publication
rechecks connection generation and writer ownership and queues the final loss
boundary before subsequent samples. Failed/partial files, failed recovery attempts
and earlier loss counts remain visible and exportable. Repeated activation cannot
spawn duplicate pending recoveries; connection changes and shutdown reject late
publication. No transport command, monitor reset or reconstruction of missing
telemetry occurs. Responsive controls expose pending, failed and resumed states.

Recovery/log/UI/receive regression checks passed 27 tests (18.41 s, existing SSL
warning): /tmp/carvera-telemetry-recovery-acceptance-tests.log. Adaptive monitor
and telemetry-quality regressions passed 27 tests (1.88 s):
/tmp/carvera-telemetry-recovery-monitor-tests.log. Ruff lint/format and diff checks
passed. The earlier combined failure remains in
/tmp/carvera-telemetry-recovery-final-tests.log: the steady-state receive test left
the automatic configuration download enabled while pumping the UI clock. The
fixture now explicitly marks configuration loaded, retaining all receive-lock,
storage-count and no-transport assertions. Recovery remains source-tested;
installed recovery interaction and complete recorded-run acceptance are open.

DESKTOP171 independently verified all 484 manifest files and strict signatures at
2026-10-05T18:52:14Z, then installed with the same checks at 18:59:48Z.
Source remains c7a90f09ef7119ec7c4f8f6d84067f8e5dfe9d7b and excludes later
rendering, setup and recording-recovery changes. Receipts are built-verification.json
and artifact-verification.json in
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop171-20261005.
DESKTOP170 remains at /Applications/Carvera Controller Community DESKTOP170 recovery.app.
Pre-install native export at 18:59:24Z reported Idle, RPM/feed zero and retained
8,583 written, 7,117 rejected and one failed record. Its missing telemetry remains
unrecoverable: /private/tmp/carvera-desktop170-20261005/native-pre-install-refresh.json.
Native DESKTOP171 acceptance is separate from verified installation.

DESKTOP171 native receipt at 2026-10-05T19:01:37Z independently retained connected
Idle, RPM/feed zero, 416 written/zero rejected/zero failed telemetry records and
the live Ubuntu camera. All 18 tracked operator stores still match their baseline.
Receipt: /private/tmp/carvera-desktop171-native-acceptance-20261005.json; raw native
export: /private/tmp/carvera-desktop170-20261005/native-desktop171-acceptance.json.
Three startup UI-heartbeat gaps of 1.22, 2.89 and 2.89 seconds remain observed;
one tested Job-to-Monitor navigation had a 1.22 ms callback and 39 ms window flip.
These limited observations do not establish comprehensive responsiveness.
DESKTOP172 build session 99180 uses frozen committed source
7b069cd4f5f8144bc76338c522914449d1713740 in
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop172-20261005.
Its new recording recovery and later rendering/setup changes require independent
artifact verification, installation and native exercise. The full 25-item scope
remains open; no new physical machining qualification is claimed.

Release-note startup checkpoint: native DESKTOP171 stall samples included hidden
TextInput layout in check_ctl_version. Controller/firmware update detection now
retains full notes without assigning them to a rendered TextInput until the Updates
dialog opens. A styled read-only viewer provides previous/next controls and page
counts; each page is bounded to 2,048 characters and 40 newline boundaries, including
oversized individual lines. Lossless pagination preserves Unicode, CRLF and every
source character. Dismissal clears rendered text/focus, and refreshing clears stale
notes and both version-check flags. Version labels use available horizontal space.
Full notes remain accessible rather than being truncated to a preview.
20 pagination, dialog, update-version and receive-heartbeat checks passed (13.59 s,
existing SSL warning): /tmp/carvera-release-notes-acceptance-tests.log.
Initial 10 checks passed in /tmp/carvera-release-notes-tests.log. Ruff lint/format
and diff checks passed. Native startup improvement and complete Updates UX remain
unverified; DESKTOP172 predates this source change.

DESKTOP172 build session 99180 finished with exit zero; independent verification
at 2026-10-05T19:05:10Z matched 486 files and strict signatures. Installation at
19:05:50Z repeated those checks and retained DESKTOP171 as a recovery application.
Source is 7b069cd4f5f8144bc76338c522914449d1713740. Native process 30194 displayed
DESKTOP172, the live Ubuntu camera, fresh reported pose and workbench/profile
navigation. Its persisted record at 19:08:48Z reported Idle, RPM/feed zero and
sequence 687 with zero earlier rejects/failures; all 18 tracked operator stores
remain unchanged. Receipt: /private/tmp/carvera-desktop172-native-observation-20261005.json.
Retained native navigation export and recording-recovery error-path exercise are
still open: scroll automation did not reach diagnostic controls, and a wheel
attempt changed scene zoom. This observation does not close responsiveness.
DESKTOP173 uses frozen b707847600d08329235883a3067afdb592f68ea9 and contains
the bounded release-note viewer; its build, artifact and native gates are separate.

Spindle workbench ergonomics checkpoint: live RPM/droop/proposal metrics remain
visible above three compact Signal, Diagnostics and Baseline sections. Each section
has its own scroll position; section switching sends no controller command.
Diagnostics export and recording-recovery controls now appear immediately after
the heading, before verbose quality metrics. The command palette opens each
section directly and offers local diagnostics export with a fresh duplicate-export
availability check. Plot construction during refresh is limited to visible Signal.
Adaptive snapshots expose the retained fault separately from the latest sample;
fresh packets do not clear it. The UI distinguishes current complete telemetry
health from a latched fault and suppresses the proposed-feed value for faults or
an off monitor. The reset action is labeled Reset monitor to reflect its effect.
No adaptive actuation or fault-clearing policy changed.

Monitor, diagnostics, receive, palette and adaptive regressions passed 37 tests
(15.85 s, existing SSL warning): /tmp/carvera-monitor-sections-acceptance-tests.log.
The initial 35-test log remains /tmp/carvera-monitor-sections-tests.log. Final
styling checks passed four cases (12.59 s):
/tmp/carvera-monitor-sections-styling-tests.log. Native layout/scrolling, keyboard
export and complete adaptive supervision remain open.

DESKTOP173 build session 15762 completed with exit zero. Independent verification
at 2026-10-05T19:11:53Z matched all 488 manifest files and strict signatures;
receipt: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop173-20261005/built-verification.json.
Its source remains b707847600d08329235883a3067afdb592f68ea9, excluding the
spindle-section changes. It is retained as a verified artifact; DESKTOP172 remains
installed while a combined newer package is prepared for native verification.

Global recording-health checkpoint: a compact footer action appears for a failed
telemetry writer, current rejected/failed records or retained earlier losses. It
distinguishes Telemetry log stopped from Telemetry gap and opens Monitor →
Diagnostics from any workbench page. Healthy/not-started recording has no visible
alert. Opening it never retries persistence, clears losses or sends CNC commands.
22 alert, spindle, diagnostics and receive checks passed (14.74 s, existing SSL
warning): /tmp/carvera-recording-alert-tests.log. Ruff lint/format and diff checks
passed. The installed footer interaction remains unverified; DESKTOP174 predates
this change. Complete recording recovery and all 25 full workflows remain open.

DESKTOP174 installed/native checkpoint (2026-10-05): frozen source
10ab103f65625bbdaf3b2e98293f9f754517f678 independently verified 488 files and
strict signatures, then installed at 19:20:23Z retaining DESKTOP172 for recovery.
Native Signal, Diagnostics and Baseline navigation and Command-K search/Return
invocation of diagnostics export were exercised. The exported receipt at
19:21:30Z retained a connected controller, 234 written telemetry records, zero
rejects/failures and unchanged hashes for all 18 tracked operator stores.
Native receipt: /private/tmp/carvera-desktop174-native-acceptance-20261005.json;
raw export: /private/tmp/carvera-desktop170-20261005/native-desktop174-acceptance.json.
Job-to-Monitor callback was 1.19 ms and window-flip notification 18.04 ms, but
startup heartbeat gaps of 2.56, 1.47 and 1.83 seconds remain observed. A latched
stale-telemetry monitor fault remained visible despite fresh packets; no feed
proposal was shown. No reset, adaptive actuation, motion, upload, tool change,
offset change or calibration was invoked. This closes the narrow installed
section-navigation and keyboard-export checks, not comprehensive responsiveness,
recording recovery error-path acceptance or any original full workflow.
The global recording-health footer at 2363de0 is newer than this installed build.

DESKTOP174 follow-up tab receipt at 19:26:27Z exercised all eight main workbench
tabs. Callback durations were 1.17–2.18 ms and window-flip notifications
6.26–75.16 ms, with no additional recorded heartbeat stalls beyond the three
startup episodes. Recording retained 1,521 written/zero rejected/zero failed
records. Raw receipt: /private/tmp/carvera-desktop170-20261005/native-desktop174-tabs.json.
This unloaded navigation sample does not qualify loaded-program workloads or
actual input-to-presentation latency. Broad local checks initially found 14
failures among 1,596 cases; older test doubles lacked added highlighting,
playback-refresh and diagnostics interfaces. Updated doubles preserve original
workflow assertions; all 42 affected-file cases passed. Full rerun remains pending.

PR checkpoint regression rerun: all 1,596 unit and focused monitor/telemetry/receive/
release-note integration cases passed in 107.45 seconds using Homebrew Python 3.9
and the installed package's HIDAPI library. Log:
/private/tmp/carvera-pr-checkpoint-tests-final-20261005.log. Full repository Ruff
lint and diff checks pass. Prior failed collection and 14-failure broad-run logs
remain retained. Draft fork PR #27 contains accumulated work; hosted CI and full
native/physical acceptance remain separate gates.

Camera calibration-reference checkpoint: the camera workbench captures an exact
immutable JPEG and separately received fresh machine pose, retaining source hash,
camera/connection generation and timestamps without storing the camera URL.
A contained frozen preview supports known XYZ point entry and pixel picking with
correspondence crosses; the main camera stays live. Fits use this reference rather
than the latest camera frame. Changed fields, camera/connection or machine-profile
ownership discard late results. Input changes require refitting before save and
withhold the draft overlay.
Schema-2 .cvcal files retain the JPEG hash, numeric correspondences, intrinsics and
reference pose; bounded decode validates dimensions, timestamps and identity.
Read/write/fit work is asynchronous and one-at-a-time. Exclusive export preserves
earlier files and independently reads back the written bytes; partial failures
remain retained. Schema-1 files remain readable but have no reference image and
their overlay is withheld. Exposure synchronization, intrinsic measurements and
physical correspondence qualification remain open.
59 camera archive/projection/overlay/client/reference and recorded-run regressions
passed in 24.86 seconds (existing SSL warning). Log:
/private/tmp/carvera-camera-reference-qualified-source-tests-20261005.log. Ruff
lint/format and diff checks pass. Installed DESKTOP174 predates this checkpoint;
native capture/picking/file roundtrip and portable-job/run calibration-image
association remain open. No original complete workflow closes here.

Calibration export readback is bounded to the bytes written plus one, so a
concurrent file enlargement cannot cause an unbounded read. Archive regressions
pass 12 cases after this change; this readback refinement is newer than the frozen
DESKTOP175 source 77bd48b24876f843de1a3fcf5afa26e293612eb9.

Portable calibration custody checkpoint: job and recorded-run setup archives now
retain a hash-checked .cvcal asset containing the exact reference JPEG, pose and
correspondences. UI capture snapshots declarations; encoding/validation occurs in
the archive worker. Imports validate calibration before asset installation, replace
the complete calibration panel state, and clear old imagery when the imported
setup has no reference. Legacy numeric registrations remain readable. Corrupt
inner image hashes are rejected even if the enclosing archive hash was recomputed.
77 focused portable-job, recording-setup and camera regressions passed in 23.13
seconds; log /private/tmp/carvera-portable-camera-tests-20261005.log. This source
checkpoint is newer than installed DESKTOP175.

DESKTOP175 package/install verification: frozen source
77bd48b24876f843de1a3fcf5afa26e293612eb9; 489 manifest files matched with strict
signature checks passing. Built verification receipt at 2026-10-05T19:40:04Z and
installed verification receipt at 19:40:41Z are retained under
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop175-20261005/. DESKTOP174 remains
as the recovery app. Native app title confirms DESKTOP175; direct connection to
the saved Carvera profile reports Idle with fresh telemetry, while the Ubuntu
camera stays live. Native reference capture retained frame 251 at 1280 x 720 and
observed table Y -195.285 mm. Exposure synchronization remains explicitly
unqualified. Pixel picking, native fitted-file roundtrip and physical calibration
acceptance remain open; no motion or adaptive actuation was invoked.

Camera workbench ergonomics/import responsiveness checkpoint: Source, Reference
and Fit & exchange occupy persistent sections with independent scrolling and
always-visible status. Switching releases hidden field focus and retains the
reference, point edits and intrinsic prior. Command-K can open each camera
section directly without configuring the camera or sending CNC commands.
Portable-job workers now validate fixture CAD, construct tool/stock declarations,
decode bounded rest-stock snapshots and write the installed program before UI
publication. A generation and machine/profile/program ownership guard withholds
late imports after newer requests or changed selections. Importing a job without
retained rest stock clears the previous residual result. Machine-profile
publication/GPU scene construction remain UI work and are not fully responsiveness
qualified. 55 combined camera/import/archive/recording/monitor regressions passed
in 11.26 seconds; six import-publication cases passed in 0.49 seconds after adding
successful publication coverage. Logs:
/private/tmp/carvera-camera-import-checkpoint-20261005.log and
/private/tmp/carvera-job-import-publication-tests-20261005.log. Full Ruff and diff
checks pass. These source changes are newer than installed DESKTOP175; native
section layout and loaded-import latency remain open.

Imported machine-profile preparation follow-up: the import worker now prepares
the retained machine CAD against a captured previous CAD reference. UI publication
accepts the prepared profile without loading its geometry again. A blocked-worker
regression proves Kivy clock callbacks continue while CAD preparation waits and
only the prepared object is passed to publication after release. All 22 async
profile/import regressions passed; log
/private/tmp/carvera-prepared-profile-acceptance-20261005.log. Ruff and diff checks
pass. This follow-up is newer than frozen DESKTOP176 source
05563a4a9c1b2075db00b8706f0cf2b7739aaaad. GPU publication and complete imported
scene transactionality remain separate open gates.

DESKTOP176 verification/install receipt: frozen source
05563a4a9c1b2075db00b8706f0cf2b7739aaaad; independent verification at
2026-10-05T19:51:30Z matched 489 manifest files with strict signature exit 0.
Installation readback at 19:51:52Z matched the same manifest/signature, preserving
DESKTOP175 as recovery. Receipts are under
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop176-20261005/. Native app title
confirms DESKTOP176, the three camera sections are visible, camera remains live
and reconnection reports Idle with fresh telemetry. Native reference-page review
found the image height still pushes controls below the fold at the installed
display scale. Source now reserves viewport room for the controls while preserving
contained image aspect; 14 camera regressions pass, including resized-viewport
coverage. Log /private/tmp/carvera-camera-height-tests-20261005.log. This correction
is newer than DESKTOP176 and is not native-qualified yet.

Hosted quality gate at eb85b70d2c8f9986a5b398be8e88ff50d86cba06 failed in run
37365934876: package-baseline mypy has 16 errors across seven files and strict
machine-layer mypy has 1,030 errors across 64 files. Ruff lint/format and
architectural import boundaries passed. Raw failure log is retained at
/private/tmp/carvera-pr27-quality-failure-20261005.log. Type-check completion is
open; local regression passes do not close hosted CI.

Type-repair checkpoint: quantity unit maps and arithmetic, variadic scene-group
relationships, inverse-time XYZ travel, program-comparison bounds, command
callback binding and archive name/calibration narrowing now have explicit types
or unambiguous bindings. Archive names are validated before object construction.
Release-note paging, generic navigation history, camera receipt-reader protocols,
program comparison and quantities pass strict checking in a five-module run with
imported-module diagnostics silent (mypy 1.20.2 on Python 3.11). This focused run
does not close full-package or hosted type checking. Local full-package checking
also reports 148 errors in imported addon modules; the earlier hosted baseline
had 16 errors, so environment/scope differences remain to reconcile. Exact logs:
/private/tmp/carvera-mypy-repaired-modules-final-20261005.log and
/private/tmp/carvera-mypy-baseline-after-types-20261005.log. Archive identity/type
regressions pass 22 cases after the final validation change; log
/private/tmp/carvera-job-identity-type-tests-20261005.log.

Orientation HUD regression: scene-edit overlays draw in canvas.after, so raising
the cube above only main-canvas geometry was insufficient. The cube now draws
last in canvas.after and is re-raised after the scene overlay is attached; removal
checks both layers to prevent duplicates. The strengthened program-rebuild
assertions check foreground ordering and a single HUD instance. All 179 combined
type-repair, command/navigation, program picker, scene-interaction and ATC overlay
regressions passed in 52.09 seconds (existing SSL warning); log
/private/tmp/carvera-type-and-hud-repair-tests-20261005.log. Earlier failed
orientation-layer receipts remain retained. Ruff, touched-file formatting and
diff checks pass. Installed DESKTOP176 predates these HUD/type repairs and the
viewport-aware camera-height correction. Native acceptance remains open.

Strict contract checkpoint: UI timing exports now use typed records, observations
and snapshots, preserving callback/flip/presentation distinctions. Window sizing
uses narrow configuration/window protocols. Scene selection/placement math now
uses mesh protocols, XYZ surface-hit contracts and typed rendered-tool snapshots;
2D and homogeneous helper vectors retain their arbitrary-dimensional semantics.
These three modules pass focused strict checking with imported diagnostics silent
(mypy 1.20.2/Python 3.11). Timing/window/monitor regressions pass 23 cases in 12.90
seconds; scene selection/placement/ATC-overlay regressions pass 47 in 30.99 seconds.
Logs: /private/tmp/carvera-timing-type-regressions-20261005.log and
/private/tmp/carvera-scene-type-regressions-20261005.log. Full local strict checking
still reports 1,491 errors across 76 files, including imported addons; exact log
/private/tmp/carvera-mypy-strict-scene-timing-checkpoint-20261005.log. Full type CI
remains open. These contracts are newer than frozen DESKTOP177 source a925005.


DESKTOP177 installed/native checkpoint: frozen source
`a92500599fed600b553b4ebcc038e22cb561c67b`. Independent built verification at
2026-10-05T20:06:18Z and installed readback at 20:08:05Z each matched 489 manifest
files with strict signature exit 0. DESKTOP176 is retained as recovery. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop177-20261005/built-verification.json
and artifact-verification.json. Native title confirms DESKTOP177; direct saved
profile reconnection reports Idle with fresh telemetry and live Ubuntu camera.
At 2340 x 1608, Reference image, capture, known XYZ and pixel-pick controls fit
without scrolling. Capture freezes frame 79 at 1280 x 720; Reference survives
Fit & exchange navigation, the main camera continues live, and a pixel click
with blank XYZ is rejected visibly. No measured correspondence or fitted physical
calibration is claimed. Package includes portable calibration, worker-prepared
imports and the foreground HUD correction; complete native loaded-job/HUD
interaction remains open. Timing/window/scene contracts at d420459 and subsequent
source repairs are newer than this installed artifact.

Native diagnostic export at 2026-10-05T20:09:50Z was independently read back from
/private/tmp/carvera-desktop170-20261005/native-desktop177-acceptance.json, SHA256
b3a2166d55b11c1405ce3ecb99fbcb9154851aef19b9c88bab9869f2a04bc763.
Export reports 324 written telemetry records, no rejects/failures, and an irregular
arrival window with one 0.994-second receive gap. Ordinary Job-to-Machine and
Machine-to-Camera callbacks were 1.90/1.11 ms and window-flip notifications
40.47/17.82 ms. Startup had a 3.376-second flip notification delay. These are
local notification observations, not input-to-presentation or machine latency
qualification. All 18 tracked operator-store hashes match the saved baseline.
No motion, upload, tool change, offset change or adaptive actuation was invoked.


Camera/joint/bounds type checkpoint: camera-fitting residual callbacks and Huber
loss now have explicit numerical contracts. Inverse-time joint demand returns,
limit flags and cancellation callbacks are typed. Indexed geometry bounds and
immutable snapshot fields use exact XYZ pairs, and scene inspection accepts the
shared indexed-mesh protocol. Existing arithmetic/validation behavior is retained.
Three machine modules pass focused strict checking with imported diagnostics
silent; 50 camera, inverse-time, scene-bounds and native-inspector regressions pass
in 16.01 seconds (existing SSL warning). Logs:
/private/tmp/carvera-camera-joint-bounds-types-final-20261005.log and
/private/tmp/carvera-camera-joint-bounds-regressions-final-20261005.log. The first
attempt used an incorrect protocol import name; the collection/type failures are
retained in the corresponding non-final logs. Full Ruff and touched-file format
checks pass. Full-package/hosted type checking and physical qualification remain
open. This source checkpoint is newer than installed DESKTOP177.


Hosted d420459 checkpoint: run 37367558768 completed at
2026-10-05T20:11:53Z. Package-baseline mypy, Ruff lint/format and import-linter
passed; strict machine-layer mypy remains failing with 905 errors across 56 files
(84 checked source files). Full quality and downstream test steps remain open.
Raw receipt: /private/tmp/carvera-pr27-quality-d420459-failure-20261005.log.
This closes the hosted baseline type repair only for d420459, not strict typing
or the newer camera/joint/bounds source checkpoint.


Profile/custody/capability checkpoint: library snapshots now distinguish their
schema and profile collections, local persistence/change tokens are typed, and
tool-definition conversion supplies named dimensional arguments. Tool history
uses typed store/event containers and a raw-calibration receipt protocol; exact
number validation retains original int/float values and stale-review rejection.
Observed XYZ poses and UI stall snapshots now have exact coordinate/record types.
Five modules pass focused strict checks with imported diagnostics silent; full
local strict checking still reports 1,304 errors in 68 files (84 checked files,
including imported addon diagnostics), down from the prior local 1,491/76 scope.
Baseline local checking remains at the previously observed 148 imported-addon
errors. Logs: /private/tmp/carvera-profile-custody-types-20261005.log,
/private/tmp/carvera-pose-stall-capability-types-final-20261005.log,
/private/tmp/carvera-profile-custody-full-strict-20261005.log and
/private/tmp/carvera-profile-custody-baseline-20261005.log. This does not close CI.

Capability exchange now rejects coercive execution flags such as string "false",
noninteger revisions/slots, malformed arrays, nonfinite/boolean numeric evidence
and invalid axis limits. Exact false remains offline even with a declared supported
feature; exchange never invokes transport. Focused profile/custody/bench/import
regressions passed 93 cases; capability/pose/stall regressions passed 54. The broad
unit suite plus profile/bench/async-profile/capability integrations passed 1,646
cases in 58.90 seconds. Logs are under /private/tmp/carvera-profile-custody-regressions-
20261005.log, carvera-capability-exchange-regressions-20261005.log and
carvera-profile-capability-broad-regressions-20261005.log.

Workbench header now keeps setup evidence in Program, Scene, Setup and Setup
Evidence. Camera/Machine/Spindle/Console/Position regain that space while preserving
connection/hold/stop and Live/Preview context. Navigation releases focus from the
removed strip and restores one instance above the inspector content. All 56
workspace/camera-reference integrations pass in 34.84 seconds, covering restored
ordering, increased inspector height, retained views and zero command sends. The
run has the existing SSL warning and retained Kivy destructor diagnostics during
teardown. Log: /private/tmp/carvera-contextual-header-regressions-20261005.log.
Full Ruff and touched-file format/diff checks pass. These changes are newer than
installed DESKTOP177; native contextual-header acceptance remains open.


DESKTOP178 package/native checkpoint (2026-10-05T20:31Z): frozen source
`e979cfaabf8babf793cac44c17875a5fa2e1dabc` built and installed as
2.1.0-DESKTOP178. Independent built verification at 20:27:18Z and installed
verification at 20:27:40Z each matched all 489 manifest files with zero mismatches
and passed signature verification. DESKTOP177 remains available as recovery.
Receipts: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop178-20261005/
{built-verification,artifact-verification,native-acceptance}.json.
Native CUA review at 2340x1608 reconnected the saved profile: configuration
loading completed, Idle and fresh telemetry were observed, with live camera
frames and no remote file selected. Setup restores its evidence strip once;
Machine and Camera omit it, reclaiming 88 screen pixels. Reference capture, XYZ
and pick controls fit without scrolling. All 18 tracked operator-store hashes
remain unchanged. No motion, upload, tool change, offset change or adaptive
actuation was invoked. This closes this package/install and contextual-header
review scope; measured registration, full responsiveness and the original 25
end-to-end requirements remain open. Source CI run 37369178168 was queued at
readback; full strict CI is not closed.


Camera exchange/review source checkpoint: calibration/reference payloads, exact
XYZ poses and decoded results are typed. Imported timestamps and table positions
require finite exact numeric values; boolean/string/overflow values are rejected
before destination creation. A present malformed image record no longer silently
becomes absent. Nullable unqualified capture/pose evidence and schema-1 legacy
exchange remain supported. Fit & exchange now shows bound frame, correspondence
count and current/refit-needed state; Save is unavailable during work or with
stale/missing registration. Failed import preserves the prior reviewed image,
registration and points. Focused camera/file/job/overlay/recorded-setup checks:
93 passed in 13.62s with the existing SSL warning. Full Ruff lint/format pass;
calibration exchange passes focused strict typing with imported diagnostics
silent. Native review of this newer UI remains open; DESKTOP178 is installed.
Logs: /private/tmp/carvera-calibration-review-final-20261005.log.
Hosted b95d2f8 run 37370204211 completed: baseline mypy, Ruff lint/format and
import-linter pass; strict machine mypy fails with 724 errors in 48 files (84
checked), down from the earlier 905/56 checkpoint. CI is still open; downstream
tests did not run. Raw receipt: /private/tmp/carvera-pr27-quality-b95d2f8-failure-
20261005.log.


DESKTOP179 package/native checkpoint: built and installed from application source
`89f57433d1277786b3aef866447eee3808e0c29f`. Both independent manifest/signature
checks matched 489 files with zero mismatches; installed verification timestamp
2026-10-05T20:41:55Z. DESKTOP178 is retained as recovery. Native review at
2340x1608 reconnected the saved profile and observed Idle, fresh telemetry and
live camera with no remote file selected. Fit review transitioned from no image
to scratch frame 97 (1280x720, zero correspondences); Save stayed unavailable
until fitting. Loading the boolean-timestamp test file displayed a controlled
validation error, and the frozen reference image/frame/pose remained intact.
All 18 tracked operator-store hashes match baseline. No machine motion, upload,
tool change, offset change or adaptive actuation was invoked. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop179-20261005/
{built-verification,artifact-verification,native-acceptance,build-runtime}.json.
This closes the bounded native summary/rejected-import scope; valid fitted-file
roundtrip and physical image/datum qualification remain open. Broad unit plus
camera-reference regressions passed 1,688 tests in 37.17s. Full local strict
typing reports 1,288 errors in 67 files, including imported-addon diagnostics;
it is still failing and not equivalent to hosted scope. Log:
/private/tmp/carvera-calibration-full-strict-20261005.log.
The first packaging attempt selected an interpreter without PyInstaller and
terminated before packaging; its log is retained. Corrected packaging uses
/usr/bin/python3 with /private/tmp/carvera-receipt-ui-deps-20261005. Build tooling
now checks PyInstaller/Kivy/PIL availability and identifies the interpreter
before staging files. All seven build-preflight tests pass. This tooling change
follows the frozen application source and does not change installed app code.


Job telemetry source checkpoint: work position, reported tool/length offset and
spindle/feed now use separate two-line fields in an adaptive grid. The prior
shortened multi-line label collapsed all three records into one crowded line.
Narrow panes stack the fields, wider panes retain two or three columns, and
disconnected state replaces old numeric values with unavailable/preview text.
Reflow/texture-height checks cover 360/650/1000dp widths without command sends.
Workspace and assembly-preview checks passed 50 cases in 43.18s with the existing
SSL warning; capability inspector/map checks passed 10 cases in 2.75s. Assembly
resolution and current-session capability observation/row records have typed
contracts; both modules pass focused strict checks with imported diagnostics
silent. Full Ruff lint/format pass. Native status-layout acceptance remains open
until a package includes these changes. Logs: /private/tmp/carvera-job-telemetry-
assembly-corrected-20261005.log and carvera-capability-row-types-20261005.log.
Hosted d361e18 run 37371584115 passed baseline mypy, Ruff and import-linter;
strict machine mypy failed with 708 errors in 47 files (84 checked). Full CI and
downstream hosted tests remain open. Raw log: /private/tmp/carvera-pr27-quality-
d361e18-failure-20261005.log.


DESKTOP180 package/native checkpoint: application source
`5191373b269f018cb669476fc946fa3a3b9d5264`; independently built and installed
manifest/signature checks matched 489 files with zero mismatches. Installed
verification timestamp: 2026-10-05T20:59:37Z. DESKTOP179 remains as recovery.
Native CUA review at 2340x1608 observed automatic saved-profile reconnect, Idle,
Live/fresh reported pose, 0 RPM/feed and the Ubuntu camera. Position and reported
tool/TLO appear in separate two-line fields; spindle/feed wraps to the next grid
row without clipping. No program or remote file was selected. All 18 tracked
operator-store hashes match baseline; no actuation was invoked. This closes the
bounded native telemetry-layout review only. Loaded-job responsiveness, full
workflow and physical qualification remain open. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop180-20261005/
{built-verification,artifact-verification,native-acceptance,build-request}.json.
The first build preflight refused the system temporary volume's 0.64 GiB free
space against its 1 GiB reserve. The corrected build used a temporary directory
on the build volume and passed; no reserve was weakened or files deleted.
Both attempt logs are retained in /private/tmp/carvera-desktop180-build-
{20261005,external-temp-20261005}.log.
Broad current-source unit plus workspace/assembly/capability integration checks
passed 1,726 tests in 83.02s. Full local strict typing still fails with 1,277
errors in 65 files, including imported-addon diagnostics (84 files checked),
and is not equivalent to the hosted scope. Logs:
/private/tmp/carvera-job-telemetry-broad-20261005.log and
/private/tmp/carvera-job-telemetry-full-strict-20261005.log.


Loaded-job context refresh now uses a preparation-time resolved-motion tool/line
index rather than scanning all segments on every UI refresh. Exact inclusive
operation queries, unknown tools, replacement and tool/setup invalidation have
source and rendered regressions. The affected 47-test suite and broad 1,684-test
unit/geometry-change/tab suite pass. A 300,000-segment source context/digest
benchmark retained identical results while median work fell from 11.483 to
0.094 ms; this does not prove native latency. ProgramOperations now passes
focused strict typing; full local/hosted strict remain failing. Package/native
loaded-job acceptance remains open. Details: docs/ui-responsiveness.md.


DESKTOP181 packaged, independently verified and installed from application
source 8033087bbd75c428a34a0aad8b81ffdafc65c55d. Native local 6,000-move
preview loading, operation selection, missing-tool readiness and five workspace
screens passed bounded review without CNC transport/actuation. The 18 operator
stores matched; normal relaunch is Live/Idle with fresh camera/telemetry and no
program selected. DESKTOP180 recovery remains local; DESKTOP179 recovery and
the failed no-space staging attempt are verified/preserved on the build volume.
Details and unresolved responsiveness/installer gates: docs/ui-responsiveness.md.


Five-axis source checkpoint: the Machine workbench now has bounded JSON geometry
import, unit-aware targets, one-to-eight seeded branch comparisons, cooperative
cancellation and highlighted result selection. Joint limits, equivalent rotary
endpoints and a tangent-projected local rank diagnostic are explicit. Input edits
and panel closure discard pending results; imported-file and canonical profile
fingerprints remain separate. Broad unit/tab/capability/branch regressions passed
1,709 tests; the new machine review module passes focused strict typing and full
Ruff checks pass. Installed DESKTOP181 predates this increment; native panel and
advanced backend/physical qualification remain open. Schema and limits:
`docs/kinematic-profile-schema.md`. The preceding documentation-head hosted run
37375157315 is terminal failure at strict machine typing (684 errors, 44 files);
baseline/lint/architecture passed and hosted tests did not run.

Final declared-branch/narrow-layout/hole regression suite: 73 passed in 21.48s
(existing LibreSSL/urllib3 warning). A rendered root-window test exposed a
self-parent traversal hang; planning/hole disclosures and shared scroll reveal
now guard ancestor cycles. Full local strict typing remains failing at 1,262
errors in 64 files, including imported-addon diagnostics (85 files checked);
configuration has not been weakened. Failed/interrupted layout attempts and
corrected checks are retained under /private/tmp/carvera-kinematic-review-*.log.

Final branch/shared-reveal/program-task regressions passed 18 tests in 21.10s,
including a self-parent window regression. The installed version file was
independently read back as 2.1.0-DESKTOP181; the new source is not yet installed.


DESKTOP182 package/native checkpoint: built and installed from
`8a1759c26ef913c278c08e64d8c3ab9afa3b299c`; independent hashes/signature
verification matched 491 source files, zero mismatches. Installed timestamp:
2026-10-05T21:44:32.909200Z. DESKTOP181 is retained as recovery. The new
installer checks source/version/identity/signature, free copied-file capacity plus
1 GiB reserve before copying, staging and installed hashes/signatures, and
controlled-failure restoration while retaining failed artifacts. Its 12 focused
regressions pass; power loss and a second rollback filesystem failure are not
guaranteed. Procedure: `docs/verified-macos-updates.md`.
Native CUA review at 2340x1608 and 1864x1306 observed panel expansion,
0.5 in -> 12.7 mm, two local seed solves, selected result details, a valid
declared head/table import with fingerprints, and rejection of a TCP-support
assertion preserving that profile. All 18 operator stores matched before/after;
no restoration or CNC actuation was invoked. Normal relaunch is Live/Idle with
fresh reported pose/camera, 0 RPM/feed and no program/remote file selected.
Receipt root: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop182-20261005/
{built-verification,artifact-verification,native-acceptance,build-request}.json.
Native review exposed chain glyphs, an initial empty-results gap, coinciding
seed solutions and a narrow navigation row with a lone Profiles button.
Source fixes for the first three pass 74 focused tests: ASCII chain separators,
zero initial results height, seed labels/coincidence warning, paired rotary
seeds and a trunnion-style B-then-C table example with five independent local
task directions when tilted. These follow-up fixes are not yet packaged; narrow
navigation density and instrumented native latency remain open. Full advanced
workflow and physical/backend qualification remain open. Hosted run 37376791085
on 8a1759c is terminal failure at strict machine typing (684 errors, 44 files);
baseline/lint/architecture pass and downstream hosted tests did not run.


Camera capture/recording contract checkpoint (2026-10-05): accepted-frame,
worker status, retained header/frame, replay association and bundle receipt
contracts are explicit. Snapshot HTTP response/opening and camera observer
contracts remain independent of CNC and Kivy. Replay validates identities and
field types before accepting typed retained data; malformed session identities
now produce a controlled ValueError rather than incidental UUID attribute errors.
Twelve valid-digest-chain malformed-field cases supplement the existing custody,
queue-loss, source-gap, bundle and workbench tests. The combined batch passed
85 tests; focused strict checks pass for camera_run and webcam. Full local
strict scope still fails with 1,181 errors in 62 files (85 source files checked),
down from the prior 1,262/64 local checkpoint. Full local baseline still reports
148 errors in 19 files including imported addons; hosted scope is separate.
No ignore/configuration changes were introduced. These source checks do not
close native recording or physical camera registration acceptance.


DESKTOP183 is installed from d9c1b414792c63f376133ea3b18d8649b94fb239;
manifest/signature and bounded native navigation/local-seed review receipts are
recorded in docs/ui-responsiveness.md. The hosted d9c1b41 quality run
37379584024 is terminal with 603 strict errors in 42 files, down from 684/44;
downstream hosted tests did not run. Full local and hosted scopes remain
separate. The native short-window Program finding has a source overflow followup
that is not yet installed; the overall 25-requirement scope remains open.


Status recording/replay contract and keyboard checkpoint (2026-10-05):
run_recording now declares program/setup/configuration bindings, retained packet,
gap/connection-boundary events, summaries and replay associations. Archive data
is typed only after existing runtime validation. Invalid non-mapping packets and
non-byte archive input produce controlled failures without changing retained
observations. The camera navigation protocol consumes the actual validated
recording payload and accepts CameraRunReplay through a positional receipt-clock
contract; a focused caller check verifies the concrete pair.

The Run record timeline is keyboard focusable with an accent focus outline:
Left/Right step, Home/End select first/last, and Space toggles receipt playback.
Seeking pauses playback. Shared focus handling disables keyboard jogging, reveals
the focused control and releases hidden focus. Modal dialogs block timeline keys;
key releases are consumed for activated controls. These are local archive controls.
The combined status/camera/archive/workbench batch passed 74 tests in 20.49s
(existing LibreSSL warning), including keyboard/modal/task-switch isolation and
malformed-input preservation. Both changed machine modules and their concrete
camera/status caller pass focused strict typing. Full Ruff/format/diff checks
pass. Full local strict typing remains open: 1,134 errors in 61 files (85 checked),
down from 1,181/62. No checks were weakened. The preceding hosted run 37380792179
at aceceb67 failed strict machine typing with 603 errors in 42 files; downstream
tests did not run. This checkpoint and the Program overflow fix are source-only;
installed DESKTOP183 remains at d9c1b41. Native keyboard/replay acceptance and the
full 25-requirement/advanced-backend/physical qualification gates remain open.


Declared joint-transition checkpoint (2026-10-05): two to eight ordered joint
waypoints are sampled with explicit linear/rotary spacing and a 2001-sample
budget. Full turns remain as entered. Local rank diagnostics identify dependent
interior postures even when endpoints have full rank. The workbench adds a
collapsible transition section, unit-aware sample-step editors, selectable rank
trace, keyboard-operable sample actions, per-joint travel/margins and tip/axis
readback. Locally solved endpoints can be explicitly copied into waypoint rows.
Dense diagnostic ticks use one mesh, not one drawing instruction per sample.
The final branch/path/workbench batch passed 45 tests in 15.05s; focused strict
typing and both architecture contracts pass. Full Ruff/format/diff pass. Full
local strict scope still reports 1,134 errors in 61 files (86 source files
checked); the new module adds no diagnostics. Hosted d217532 run 37381472794
failed with 556 strict errors in 41 files (85 checked); baseline/lint/architecture
passed, downstream tests did not run. No check configuration was weakened.
See joint-transition-review.md. Between-sample behavior, physical clearance,
controller interpolation/rates/TCP/backend execution remain unqualified.
DESKTOP184 packaging/native review is a separate gate; the full scope stays open.


DESKTOP184 native checkpoint (2026-10-05): installed source 0b9b921 independently
matched 492 manifest files with zero mismatches and a valid strict signature.
Native CUA review at 2340x1608 and 1864x1306 verified Program scroll reachability
without overlap; freezing 168 received status events, Home/End selection and
Space playback/pause; and the 91-sample head/head joint route, selecting full-rank
endpoints and rank-4/5 interior sample 46. Live camera and reported Idle telemetry
continued. All 18 tracked operator stores matched the preupdate backup. Final
normal Program/Operations view reported T1/TLO50.480, zero spindle/feed and no
selected program/remote file. No motion, upload, toolchange, offset or adaptive
actuation was invoked. Receipts are under
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop184-20261005/`.

A native observation prompted a source followup: returning to the live recording
buffer disables archive step actions and resets its disabled cursor rather than
retaining a misleading partial archive position. This followup postdates the
installed DESKTOP184 source. Camera archive native roundtrip, loaded-job latency,
complete branch/path workflows and physical qualification remain open.


Indexed setup checkpoint (2026-10-05): fixed rotary angles and declared tool/work
geometry map up to eight work points to exactly three independent linear axes.
Head/head, head/table and table/table topologies, shifted pivots/bases, work-chain
linear axes and non-orthogonal bases participate in the affine solve. Any invalid
point rejects the whole result; dependent bases, stale results and cancellation
do not publish. Workbench controls copy a selected branch orientation explicitly,
inspect individual mapped points and hand off joint waypoints to separate route
review. Narrow forms reserve the actual multiline-field height and fit compact
point-choice captions. See indexed-setup-review.md. Backend/postprocessor,
indexing approach, physical travel/clearance and complete native acceptance remain
open; local mapping does not certify a cutting workflow.


DESKTOP185 bounded native checkpoint (2026-10-05): frozen source 9543153
independently matched 493 manifest files with zero mismatches and a valid strict
signature. Native CUA review mapped the two default head/head work points at
fixed C0/B30 with 5 mm tip offset, selected point 2 (X22.5/Y15/Z29.33), copied
the explicit joint route and reviewed six samples with 2 mm tip step, zero axis
change and zero chord deviation. Last-sample details remained reachable at
1864x1306 and selected state survived widening to 2340x1608. Freezing 583 status
receipts and returning to the live buffer disabled archive stepping and reset
the cursor. Live camera/telemetry continued; final Program/Operations view
reported Idle C1, T1/TLO50.480, spindle/feed zero and no selected program/remote
file. All 18 tracked operator stores matched the backup. No motion, upload,
toolchange, offset application or adaptive actuation was invoked.
Receipts: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop185-20261005/`.
Native selected-branch/custom-profile indexed workflows, camera archive
roundtrip, loaded-job latency, physical indexing/clearance and backend execution
remain open. The packaging-tool preflight source followup postdates this frozen
controller build. The full original and supplemental requirement sets remain
open; this receipt closes only the stated bounded native cases.

Camera viewing recovery checkpoint (2026-10-05): the existing Ubuntu camera
service was active; the missing Mac loopback forward was restored as a supervised
user LaunchAgent. Current host identity was verified over authenticated Tailscale
SSH and separately pinned with strict checking. Native DESKTOP186 again displayed
a live camera frame with 0.1-second age. Controlled forward termination recovered
automatically under a new PID; independent JPEG readback measured 0.064-second age.
Direct Mac-to-CNC control remained unchanged. See camera-forward-recovery.md.
Physical registration/synchronization and complete camera workflows remain open.

Spindle validation checkpoint (2026-10-05): malformed signals and invalid monitor
clocks latch faults without replacing valid sample history. Explicit baseline
recapture now starts a fresh five-second signal sequence while retaining earlier
arrival gaps. The signal panel reports elapsed capture time/sample count and
paused/captured states with wrapping text. All 101 focused monitor/feed/quality/
persistence/recovery/UI regressions pass, both changed machine modules pass strict
typing, and lint/format/architecture checks pass. Full local strict typing remains
open at 1,016 errors in 56 files (88 checked); this scope differs from hosted CI.
See spindle-monitor-validation.md. Changes postdate installed DESKTOP186; native
acceptance and qualified adaptive actuation remain open. Shadow sends no commands.

Tool-bank evidence checkpoint (2026-10-05 UTC): bank cards filter missing evidence
or selected assemblies and open an inline full assessment/raw-receipt review.
Logical and mapped controller receipts stay distinct; every raw sample is reachable
through bounded 80-sample pages. New pages start at the top, stale contexts clear
prior evidence, and compact action captions fit 360/760 dp layouts. Canonical
record validation rejects duplicate logical-tool bindings, malformed fields and
unbounded reads. All 69 bank/custody/mapped-program regressions pass; the changed
engine passes focused strict typing; lint/format/architecture pass. Full local strict
typing remains open at 980 errors in 55 files (88 checked). See
tool-bank-evidence-review.md. Installed and physical reload/re-entry acceptance
remain open; the original and supplemental full requirement sets are unchanged.

Repeat-plan persistence/review checkpoint (2026-10-06 UTC): explicit plan/stock/frame
contracts reject malformed and overflowing coordinates; canonical digest comparison
and a cooperating-writer lock protect per-machine saves. Background plan I/O keeps
navigation available, retains an authorized original-owner save snapshot and rejects
stale restore callbacks. Frame details show declared datum/bounds/stock separation;
active tabs and full-height quantity rows improve narrow layout. All 80 repeat/
simulation/archive/playback/geometry/UI regressions pass; the changed engine passes
focused strict typing; lint/format/diff/architecture pass. Full local strict remains
open at 906 errors in 54 files (88 checked). See repeat-parts.md. Changes postdate
installed DESKTOP186; measured offset transactions, repeat execution/inspection,
installed acceptance and the full original/supplemental requirements remain open.


Repeat-plan editing checkpoint (2026-10-06 UTC): regular saved arrays synchronize
layout inputs; custom frame tables retain individual geometry and require an explicit
new-array action before grid replacement. A collapsible selected-part editor validates
name/WCS/datum/origin/size before publication, preserves neighbors and clears stale
machine-context fields. Source narrow-layout review and focused strict/lint/format/
architecture checks pass. Full strict/package diagnostics remain open and unchanged.
See repeat-parts.md; installed workflow, measured frames and repeat execution remain
open. No controller offsets or execution commands are dispatched by editing.


Repeat draft ergonomics checkpoint (2026-10-06 UTC): pending per-part text survives
selection, shows status/count, and supports validated atomic Apply all plus explicit
single/all discard. A full-width name row and guarded save/restore/array replacement
prevent editing/navigation from silently losing or omitting pending values. All 87
repeat/simulation/archive/playback/geometry/UI tests pass; lint/format/diff/architecture
pass. Full strict and installed/physical acceptance remain open. See repeat-parts.md.


Repeat-plan persistence ergonomics checkpoint (2026-10-06 UTC): common Save/Restore
controls stay available on all repeat pages, with revision-aware status and disabled
pending-edit actions. All 88 local repeat/simulation/archive/playback/geometry/UI
regressions pass, including concurrent-save preservation and explicit restore of
the newer revision. Lint/format/diff/architecture pass; strict and physical acceptance
remain open. DESKTOP187 independently verifies native draft retention, bulk apply,
discard and clean restart (496 source files, strict signatures, nine operator JSON
files unchanged), with native save/restore still open at that frozen checkpoint.
See repeat-parts.md for evidence and the distinction between current disk state and
last-read/saved revision. The original and supplemental requirements remain intact.


Multi-form threadmill source checkpoint (2026-10-06 UTC): loaded profiles carry explicit complete tooth count and tip datum; hole previews use one-pitch radial passes with stack, floor, bottom and reach checks. Recipe restoration and physical assembly review compare those fields, nominal visualization shows the declared tooth cells, and the workbench summary explains axial coverage/reference with stable narrow-layout wrapping. See multiform-threadmilling.md. Installed DESKTOP188 predates this source; native complete workflow, true thread grooves, manufacturer geometry/reference and physical cutting/inspection remain open. The full original and supplemental scope remains intact.


Physical cutter lifecycle source checkpoint (2026-10-06 UTC): physical assemblies now retain explicit cutting-use intervals, operator inspections with optional measured diameter, and reviewed replacement links. Replacement preserves old calibration/use history and blocks new declarations for the retired identity; chronological, duplicate, stale and cycle checks reject atomically. A dedicated passport section provides complete bounded history pages, concentrated compact actions, synchronized assembly captions and background writes with original-store ownership. See tool-lifecycle.md. Native installed workflow, observed execution attribution, physically qualified wear/replacement and full original/supplemental requirements remain open. No controller commands are dispatched.

Lifecycle source validation: 109 focused lifecycle/custody/passport/process/bank/UI tests pass; changed custody/lifecycle/bank engines pass strict checking; full lint/format/diff and two architectural contracts pass. Full local machine strict typing remains 883 errors in 54 files (89 checked), package baseline 148 errors in 19 files (186 checked). No check configuration was weakened.

Long-form custody ergonomics checkpoint (2026-10-06 UTC): anchored overlapping-page
scroll controls expose final fields without submitting drafts, disable at boundaries
and disappear on fitting forms. Field/scrollbar separation, vertical-only motion and
collapsed empty validation space improve compact layout. Full-app pointer routing,
compact navigation and related focus/custody/process checks pass (8 + 37 tests);
360 dp rendering was inspected. The prior native scrollbar discrepancy and next
installed navigation acceptance remain open. See tool-lifecycle.md; the complete
original and supplemental scope remains intact.

Calibration trend checkpoint (2026-10-06 UTC): DESKTOP195 from exact source
6998e6de92f25f305ca64dbdfb2175b1f825ae3b is installed, independently verified
against 498 packaged files and strict signatures, with DESKTOP194 recovery.
Native pointer review of 70 synthetic receipts verified exact unknown receipt
selection, adjacent navigation, older paging, group/metric controls and three
focused views with retained selection. Original active custody absence/configuration
and all nine operator JSON hashes were restored. Normal readback: Idle C1, T1,
50.480 mm TLO, zero spindle/feed, fresh telemetry/live camera and Live pose.
See calibration-bench.md; registered measurement transport, references and physical
qualification remain open. Exact-head hosted typing remains 353 errors/33 files.

Retained plane fitting source checkpoint (2026-10-06 UTC): Surface inspection now
separates receipt history, measurement entry and cross-feature plane review. Compatible
nominal/setup groups use an explicit latest/earliest retained receipt per feature;
missing/raw/unregistered selections are listed without older fallback. Mixed reference
pairs reject. Centered/scaled least-squares height fitting yields tilt, signed residuals,
RMS/range and source-bound receipt selection; rank/spread guards reject unsupported
fits. Entered residual-range comparisons and reproducible bounded atomic exports retain
exact input snapshots. See inspection-plane-review.md. Installed/native plane review,
minimum-zone form/uncertainty, wider tolerances, actual probe transport and physical
qualification remain open; the original and supplemental scope is unchanged.


Fixed tilted-axis clearance source checkpoint (2026-10-06 UTC): translating axial
cylinder sections now have continuous convex support-plane lower/upper distance
bounds. Broad box corner candidates are rejected only with positive separation;
zero-lower-bound contact/near-contact remains a candidate. A bounded simplex solver
retains unresolved precision explicitly rather than replacing it with an achieved
tolerance claim. Compact review exposes unresolved/near-contact/model counts and
modeled witness fractions. See clearance-traces.md. Changing orientation, complete
registered structures, installed/native acceptance and physical clearance remain open.
The full original/supplemental scope is unchanged.

Typed review-input checkpoint (2026-10-06 UTC): program preview records now retain
concrete motion, frame-preview and tool-bank types; dependency summaries accept
explicit tool collections and stock dimensions. Clearance grouping declares source
operation/segment interfaces and exact candidate/capture/cause identities without
removing any captured interval. Operation highlighting and worker clipboard reads
have concrete input/result contracts. Runtime aliases retain Python 3.9 support.
A missing clipboard output pipe is rejected while the helper is reaped and its slot
released. No suppressions or quality configuration changes were added.

Validation: 24 focused behavior checks passed, followed by four clipboard checks
including the new missing-pipe case. All five changed machine modules pass focused
strict typing. Same-environment full-machine comparison against frozen 60ab454
removes 19 diagnostics (872 to 853) with no new diagnostic instances; local package
baseline remains 148 errors in 19 files. Local environment/import coverage differs
from hosted CI, so these counts do not predict the hosted result. Repository lint,
format and both architecture contracts pass. Installed DESKTOP198 predates this
source checkpoint; CI, native workflow, physical qualification and the complete
original/supplemental requirements remain open.

Typed transformed-motion checkpoint (2026-10-06 UTC): simulation segment inputs
now declare source operations, inclusive selection lines, named offset mappings
and reference coordinates. Read-only frame mappings are copied into validated
immutable vectors before transformation, with missing frames still rejected.
Repeat playback records declare the eight position/move/source/tool/feed columns,
unresolved source lines, offset view rows and cancellation callback. Tool comparison
accepts explicit definition maps, calibration history and optional observed poses;
fresh reported TLO remains separate from historical TLO and nominal tool geometry.
No controller commands or quality-check suppressions were added.

Validation: 31 focused simulation/repeat-playback/repeat-stock/tool-comparison tests
pass, including immutable frame mapping, source/tool retention, caller-input
non-mutation and missing-frame rejection. Repeat playback and tool comparison pass
focused strict typing. Same-environment machine strict diagnostics drop from 853
to 836 (17 removed, no new instances); package baseline remains 148/19. Full
simulation-preview typing still has other open functions. Lint/format and both
architecture contracts pass. Previous exact-head hosted run 37405849012 at d267ab1
completed with 334 strict errors in 28 files (90 checked), hosted tests skipped.
Installed DESKTOP198 predates this source. CI, native workflow, physical acceptance
and the complete original/supplemental requirement ledgers remain open.

Typed section drawing checkpoint (2026-10-06 UTC): section geometry declares
indexed-triangle sources, immutable XYZ contours, projected bounds and worker
callbacks. Captured results reject negative/noninteger triangle counts and
nonpositive/nonfinite/boolean tolerance. The drawing now carries horizontal/right
and vertical/up axis captions plus a millimetre scale bar using the same uniform
transform as its contours. Captions render above the geometry; bounded caption
widths prevent compact overlap. Plain direction words avoid missing glyphs in the
bundled font. These drawings remain nominal open CAD contours, not measured solids.

Validation: 29 focused engine/workbench tests pass after final layout refinement,
including all axes, compact/wide scale equivalence, nonoverlapping captions,
SVG scale, cancellation, stale-result invalidation and dense full-segment rendering.
Both final 270/1000-pixel source renders were visually reviewed. The engine passes
focused strict typing; full local machine diagnostics drop 836 to 822 (14 removed,
no new instances), package baseline remains 148/19. Lint/format/diff and both
architecture contracts pass. Previous exact-head hosted run 37406132226 at bd65dcc
is terminal: 317 strict errors in 26 files (90 checked), hosted tests skipped.
Installed DESKTOP198 predates this source. Native installed acceptance, CI, physical
qualification and the full original/supplemental requirement ledgers remain open.

Filesystem worker contract checkpoint (2026-10-06 UTC): file-picker requests and
results carry concrete typed request/entry/listing fields. Parent and child validate
operation-specific requests before filesystem work. Parent validates response
envelopes, directory/filename/path binding, suffixes, unique entries, exact boolean
flags, nonnegative integral sizes and finite timestamps before publication. Empty,
truncated or malformed JSON produces a recoverable picker error rather than an
uncaught field/type exception. Cancellation arriving with a completed reply still
rejects publication. Metadata validation performs no parent-side filesystem I/O.
Existing bounded child deadlines, retirement slots and bootstrap isolation remain.

Validation: 41 focused worker/picker checks pass, including malformed real helpers,
reaping and subsequent capacity recovery, invalid-create non-mutation, late
cancellation, case-insensitive suffixes, valid negative timestamps and a real picker
error-to-successful-retry flow. Prior transport tests now provide valid protocol
requests while retaining their original kernel-block/timeout/capacity assertions.
The module passes focused strict typing; full local diagnostics drop 822 to 813
(9 removed, no new instances), package baseline remains 148/19. Repository
lint/format/diff and both architecture contracts pass. Previous exact-head hosted
run 37406582018 at 2cc046b is terminal: 303 strict errors in 25 files (90 checked),
hosted tests skipped. Installed DESKTOP198 predates this source. CI, native installed
workflow, physical qualification and the full original/supplemental scope remain open.

Typed profile browsing checkpoint (2026-10-06 UTC): cutter filtering and saved
record browsing accept concrete read-only mapping/collection contracts and retain
original record identities. Nonfinite, boolean, nonnumeric or nonpositive dimension
metadata cannot satisfy a range/shank filter and sorts after known dimensions.
Direct filter construction validates the same finite positive dimensions, ordered
range and asset category as text entry. A wrapped active-filter summary beside the
list names shape/vendor, normalized millimetre constraints and reference category;
compact header growth preserves result scrolling and editor space. Inactive and
non-cutter summaries collapse while the declared filter remains separate from data.

Validation: 24 focused engine/library UI checks pass, including imperial conversion,
all active summary fields, NaN/malformed dimension exclusion, unknown-last sorting,
identity/non-mutation, 95-record paging, editor draft retention and compact layout.
The compact source render was visually reviewed and retained at
/private/tmp/carvera-library-filter-summary-20261006.png. Focused engine strict
checking passes; full local diagnostics drop 813 to 803 (10 removed, no new
instances), package baseline remains 148/19. Lint/format/diff and both architecture
contracts pass. Previous exact-head hosted run 37407115509 at 4b65f43 is terminal:
294 strict errors in 24 files (90 checked), hosted tests skipped. Installed
DESKTOP198 predates this source. Hosted CI, native installed acceptance, physical
qualification and the complete original/supplemental scope remain open.

Receipt timeline position checkpoint: recorded playback now displays elapsed/total
receipt seconds, selected event position and the next gap/connection boundary.
The readout follows elapsed time between packets, wraps in narrow panels and stays
in the final rebuilt layout. These are receipt times, not interpolated machine
motion or exposure times. Boundary stops and withholding recorded pose/camera
remain unchanged. The pure playback engine has concrete input/output contracts,
finite numeric normalization and recoverable rejection of unrepresentable clocks
or speeds. Position queries use captured scalar metadata and indexed boundaries,
without scanning packet bodies. Source engine/UI regressions include boundary
navigation, between-packet elapsed time, visible parent/layout retention at
320/1200 pixels, reset-to-live and no command dispatch. The initial omitted-widget
renders were retained; corrected renders were visually reviewed. Installed/native
acceptance and the full recorded-run/physical qualification requirements remain
open; DESKTOP199 predates this checkpoint.

Setup evidence overview checkpoint: the inspector distinguishes current operator
receipts, declarations without receipts, stale receipts needing recheck and
missing configuration. Card headings wrap to their measured text height in narrow
panes, and action labels wrap inside taller controls rather than spilling across
card borders. Expired validity and future-dated measurements have distinct corrective
messages; changed geometry and explicit physical invalidation remain separate.
The pure store declares receipt/state/snapshot contracts and normalizes valid UTC
timestamps without mutating input receipts. Oversized, boolean, nonnumeric or
nonfinite imported dates and evaluation clocks reject as recoverable ValueErrors;
invalid records do not change persisted bytes. Schema 1 and prior receipts remain
preserved. Source regressions cover mixed evidence states, dependent geometry
changes, forms, readonly snapshot maps, timestamps and 280-pixel card layout with
no machine command dispatch. Rendered source review does not qualify an installed
workflow, independent physical measurements, or authorization to run. DESKTOP199
predates this checkpoint; complete requirement acceptance remains open.

Recorded-run bundle contract checkpoint: full-run import/export reports retained
setup assets, optional camera inclusion and the retained event count. Import no
longer incorrectly declares historical tools/calibration unavailable when a bound
setup archive is present; assets are available for review, without implying they
are loaded or physically qualified. Exact program/status/session/member checks
remain. Loaded bundle paths, optional camera/setup records, stream digests and
export receipts have concrete contracts. Program-context absence rejects before
installation, including a rehashed outer archive with valid unbound status bytes.
Setup program/stock binding is typed, and the portable job loader declares its
existing binary-stream input in addition to file paths. Source checks cover stream
custody, matching setup/no-setup notice content, exact bytes, foreign camera
rejection and zero command dispatch. Installed/native full-run acceptance, complete
historical restoration, execution attribution and physical qualification remain
open; DESKTOP199 predates this checkpoint.

Evidence navigation checkpoint: setup evidence and measurement forms use the
shared desktop scrollbar with a visible nine-dp drag target. A persistent
Stock/Mounting/Tools/Offset navigation row reveals the requested evidence card
after layout settles, with identity and active-page guards to prevent pending
navigation from scrolling a hidden or replaced page. It writes no receipts and
dispatches no controller commands. Local replay transport precedes receipt
navigation, timeline and keyboard help so play/pause is nearer the top of the
workbench. Compact and desktop source checks verify card visibility, hidden-page
non-mutation and transport ordering. Native installed acceptance remains open;
DESKTOP200 predates these changes. Prior native diagnostics identify automated
wheel event-coordinate discrepancies, so source scrolling checks do not prove
physical mouse/trackpad delivery or continuous camera health.

Program-shortcut contract checkpoint: recent/favorite references have concrete
path/list/read/write contracts and bounded byte reads, including a store that grows
after its earlier inspection. Unsupported paths, invalid UTF-8/schema and growing
stores reject without rewriting existing bytes. Atomic replace/readback and
external-change reconciliation remain. Picker collection buttons show counts only
after an accepted current worker snapshot; loading/error states retain uncounted
labels, and stale revisions cannot publish new counts. A missing saved-profile
identity no longer crashes repeat-frame refresh and cannot authorize a saved plan.
Source checks cover counts, stale snapshots, bounded reads and input non-mutation.
DESKTOP201 predates this source checkpoint; its installed evidence shortcuts and
visible replay transport are independently exercised, while native shortcut-store
acceptance and complete recorded-run workflows remain open.

Simulation-bookmark checkpoint: saved-point names are separate from wrapped line,
tool and program-match metadata, including narrow workbench widths. Preview
restoration still verifies machine, program, setup geometry, source and tool.
Concrete bookmark/view contracts accept read-only mappings; numeric bounds reject
unrepresentable integers without overflowing. Library reads are bounded at the
actual stream, and atomic saves must pass independent byte readback before
publishing success. Failed reads/saves preserve loaded state and require reopening
when replacement occurred. Twenty-five focused checks cover persistence, external
writers, revision refusal, compact/wide rows and input/store non-mutation. Focused
strict typing passes; same-environment machine diagnostics drop 736 to 722 with no
new instances, while package baseline remains 148 errors in 19 files. Installed
DESKTOP201 predates this checkpoint; native bookmark acceptance, hosted CI and
complete simulation qualification remain open. No machine actuation is added.

Recorded-scene inventory and reversible edge-state checkpoint: the Run record
workbench shows loaded machine/fixture/workholding models, stock dimensions and
work offset, and archived cutter/holder CAD reference counts. Schematic geometry
and unmeasured alignment remain explicit. Stock-only application replaces the
complete inventory notice; restoring the previous scene clears archived status.
Repeat-part edge geometry is included in publication rollback snapshots; normal
restoration verifies regenerated edge vertices/indices rather than object identity.
Archived dimensions reject oversized integers without overflow, and multi-form
thread tools require an integer complete tooth count, pitch, datum and a tooth stack
within flute length. Concrete historical scene/tool contracts retain exact-byte
program/setup/asset checks. Thirty-five focused restoration/navigation/run-package
checks pass (one existing SSL warning); narrow/wide rendered inventory was reviewed.
Strict machine diagnostics fall 722 to 712 with ten removed and no new instances;
package baseline remains 148 errors in 19 files. Initial identity-assumption test
failures and typing attempts remain in temporary logs. Installed DESKTOP203 predates
this source checkpoint; native full restoration, continuous camera health and all
complete original/supplemental requirements remain open. No actuation is added.

### Recording scope and disclosure ergonomics, 2026-10-06

Run record exposes both scopes beside replay controls: Record program status and
Record program + scene. The latter retains declared setup assets; it no longer
hides under file custody controls. Opening secondary disclosures reveals their
heading after layout settles. A closed or hidden disclosure cancels its pending
reveal, avoiding stale scroll jumps. Twelve focused recording/historical-workbench
checks pass, with two affected checks rerun after final assertions; existing SSL
warning remains. Lint/format/diff and both architecture contracts pass.

Native DESKTOP203 (source 9b702864e41354818390d6af3a39fbdd5f85f166) exercised
recent-program local preview, setup-bound recording, freeze, full run export,
recorded scene loading, prior scene restoration and return to live. Independent
readback verifies session 93ff9041-0810-4a2a-b83c-2e01be638ff5, 126 events, exact
113-byte program and matching setup archive. Bundle SHA-256 is
 e0c297ce2659b0a1d5bc8e9a6cd9fecc39143e1a7dd1e7f8bc3afe509be0ffa4.
The native profile has no toolset, so archived cutter selection remains open.
No camera archive is included. All nine pre-existing operator JSON stores are
unchanged. Final native state is Live, Workshop Carvera, Idle, T1/TLO 50.480 mm,
spindle/feed zero, camera age 0.4 s. Physical registration remains unmeasured.
Receipts: /private/tmp/carvera-native-record-workflow-20261006/.

Hosted run 37411186365 for 897313d7c2129da42fd9ea8762672bc1f46fef37 failed the
strict quality hook with 193 errors in 18 files; tests were not cleared by CI.
The next native update has not started: low local capacity and a stalled verified
artifact relocation to the established external CarveraBuilds folder leave
packaging/install open. Originals remain intact until full copy verification.
All original/supplemental requirements remain open. No actuation is introduced.

### Tool profile loading responsiveness, 2026-10-06

The profile library and startup toolset restoration prepare tool geometry in a
worker, retaining current preview geometry until preparation succeeds. Pure
validation, CAD digests and mesh construction are separated from renderer
publication. One active worker and one latest queued request bound concurrent
loads; overwritten requests never publish. Program/CAM units, existing tooling,
assembly binding and scene identity are rechecked before publication. Missing
assets, changed scene/program and a closed workspace preserve the prior preview.
The editor shows Preparing until publication completes, then Loaded or the error.
This changes local preview only; it does not update physical tooling or offsets.

Focused validation: 27 geometry/assembly/profile/worker tests pass, plus three
worker/editor tests after the final closed-workspace check and 66 adjacent
library/cutter/workspace/machine-profile checks. Existing SSL warning
remains. Package typing stays at 148 errors in 19 files with zero added/removed
diagnostic instances; both architecture contracts pass. Native acceptance and
packaging of this checkpoint remain open until independently verified. Scene
assembly preview/selection still has synchronous preparation paths and remains
part of the responsiveness backlog.

DESKTOP203 artifact relocation completed with 7,851 files/links independently
matched, strict signature verified and the original path retained as a symlink.
Receipt: /Volumes/Wes Storage/CarveraBuilds/carvera-desktop203-20261006/relocation-receipt.json.
Hosted run 37412190228 for e1de2c9b14677e1a7dd458c2a6c3fc94488e1c8b failed the
strict quality hook (193 errors in 18 files). Neither that CI nor the package
baseline is green. All broader original/supplemental/physical gates remain open.

### Individual cutter custody after asynchronous loading

Individually loaded cutter profiles retain a detached source record beside their preview slot. Recording snapshots include that record only while its full converted definition still matches the active preview (excluding freshly calculated asset digests). This closes the missing inventory-metadata path when no ATC toolset is loaded; tool CAD and drawing bytes were already retained in the authoritative scene definitions. Changing or removing the active definition withholds stale metadata. Replacing the complete toolset clears individual provenance. The recorded geometry remains nominal and does not prove physical tooling or measured stickout.

Thirty-three focused recording/setup/historical-scene, asynchronous cutter-loading and profile-editor checks pass. Native DESKTOP204 loaded the existing Helical 03182 CAD, recorded/exported it with the selected program, restored the archived scene with one cutter CAD reference, then restored the previous preview. The individual inventory metadata correction follows DESKTOP204 and requires a later installed build for native qualification. Full hosted CI remains a separate open gate.


### Assembly and Scene cutter preparation, 2026-10-06

The native assembly passport Preview/Clear actions and Scene cutter dropdown now use the bounded background tool loader. Existing geometry stays visible while CAD, digests and meshes prepare. Rapid changes keep one active and one latest queued request; only the latest result publishes. Scene choices persist after successful publication, and failures restore the prior accepted choice. Follow program restores the prior definitions and releases the manual cutter override. Assembly revision and linked cutter fingerprint are rechecked before publication; a saved Scene cutter changed during preparation is rejected. Manual preview-tool changes also invalidate a pending result. Startup scene restoration defers the request until numeric setup fields settle. The legacy synchronous helper APIs remain available to internal callers/tests; native controls use the asynchronous request APIs.

Validation: 53 assembly/worker/workspace checks pass, followed by five final worker tests including rapid Scene selection, stale saved-cutter rollback, revision rejection, restoration and no controller-command dispatch. Full lint/format and both architecture contracts pass. Package diagnostics match the preceding baseline exactly: 148 errors in 19 files, zero added/removed instances. Installed acceptance of this source checkpoint remains open until a new build is independently verified.

DESKTOP205 independently qualified the earlier f5fc2a9 individual-cutter recording change: exact source and all 503 packaged files matched; strict signatures passed; native existing Helical cutter preview, program-plus-scene recording/export, archived scene restoration, prior-scene restoration and return to Live were exercised. Archive session a34ceef2-d374-4b48-8f1e-5713d25aa7fa retains one individual inventory tool plus its nominal geometry and drawing assets. Ten pre-existing operator JSON stores matched their prior hashes. This proves local preview and archive custody, not physical tooling or machining. Hosted f5fc2a9 run 37413301913 failed strict quality typing with 193 errors in 18 files; hosted tests were skipped. The full original/supplemental/backend capability scope remains open. No actuation is introduced.


### Typed ATC receipt contract, 2026-10-06

The bounded M889 inventory now declares its receipt, pending-clock/generation/source state and logical row schema. A read-only cutter-description protocol keeps the machine layer independent of rendering/UI types; reported coordinates and declared names remain separate, and physical contents are explicitly Unknown. A pending query without a start time expires safely rather than performing arithmetic on absent state. Existing header/completion/ambiguity/timeout/reconnect and validated exchange behavior remains covered by 27 passing tests. Focused strict checking passes the inventory module. Same-environment full machine strict comparison against frozen 09aaa72 removes exactly 18 inventory diagnostics with zero added instances (712 to 694; these local counts include imported modules and differ from hosted CI). Package baseline remains 148 errors in 19 files. Both architecture contracts pass. The full typing/CI and physical inventory reconciliation gates remain open. This source checkpoint postdates frozen DESKTOP206; no controller commands are introduced.


### Static Live cutter placement, 2026-10-06

Installed DESKTOP206 independently matches frozen 09aaa729fb88873bbbf9e221d00b886084a98063 in all 503 packaged files and passes strict signature verification; DESKTOP205 recovery remains intact. Native Scene loading of the existing Helical CAD and nominal ball-nose profile, navigation to Position/Setup, Follow program restoration and return to Live/Program were exercised. Ten pre-existing operator JSON stores are byte-hash unchanged. Live readback reports Idle C1, T1/TLO50.480, zero spindle/feed and a live camera. No motion, upload, offset, toolchange or run command was invoked. Receipts are in /Volumes/Wes Storage/CarveraBuilds/carvera-desktop206-20261006/.

Native review found the no-toolpath static cutter at the program origin while the spindle followed a reported Live pose. The preserved before-fix regression fails all three rendered offset coordinates. Source now uses the same observed machine-to-program point for static Live geometry, retains the local cursor in Compare and hides unavailable Live geometry. Hiding the machine removes bed-motion displacement from the standalone cutter frame. Thirteen pose/worker/assembly tests and two final shown/hidden model cases pass; lint/format pass and package diagnostics remain exactly the preceding 148-error baseline. Installed acceptance of this correction remains open; DESKTOP206 predates it. The last loaded Preview T caption also remains in the header after Follow program restoration and needs a source/UI correction. Physical geometry registration, full Live/Compare/rotary workflows and all broader requirements remain open.

Hosted cf27c7a run 37415436484 removes exactly 18 ATC inventory diagnostics with none added: 193 errors in 18 files become 175 in 17 (90 checked). Hosted tests remain skipped. Prior DESKTOP205/202/201 artifact relocations independently match all files and directory/link members, pass strict signatures and retain their original paths as symlinks to verified external copies. All relocation/build/install handles have terminal successful receipts.

### Follow-program profile summary, 2026-10-06

Clearing a manual cutter/assembly override now restores the selected machine and loaded toolset summary in the workbench header. The previous cutter-preview caption cannot linger after Follow program. A restored manual override still retains its preview context. Seven asynchronous cutter/assembly checks pass, including machine/no-toolset restoration and an actual loaded bank name; no controller commands are dispatched. This follows installed DESKTOP206 and still requires installed native readback. Exact 7525924 hosted CI remains failed with 175 errors in 17 files (90 checked), with hosted tests skipped.

### Typed portable ATC configuration receipts, 2026-10-06

ATC exchange now declares validated payload, envelope, coordinate rows and export receipts. JSON remains an untrusted boundary: exact fields/semantics, UTC completion time, source restrictions, response and envelope hashes, and coordinates reconstructed from the normalized response are checked before returning a typed result. Optional UTC offset is guarded explicitly. Import remains historical evidence and does not replace current connection freshness or infer pocket contents. Twenty-seven inventory/exchange tests and four native-panel integration tests pass; focused strict checking, lint and formatting pass. DESKTOP207 packaging is a separate frozen 3079b2c checkpoint; this source follows it and requires later package/native qualification. Full CI and physical ATC reconciliation remain open.

### Typed geometry-change dependencies, 2026-10-06

Simulation/setup context capture now declares the read-only viewer/setup/profile interfaces, asset identities, assembly identity and context schema. CAD byte loading has concrete bounded path/byte contracts. Existing context field names, asset digests, units and metadata exclusions remain intact. Change-to-operation dependency review materializes one-shot change iterators once so the tool-specific dependency is retained across its two passes. Twenty-seven geometry/preview/impact unit and integration checks pass, including same-path changed CAD bytes, stale/unversioned assets, assembly/holder consequences and the iterator regression. Focused strict checks pass both contract files. Python 3.9 runtime validation caught and corrected a union expression evaluated inside cast; the initial failing log is retained. Lint/format and architecture checks pass. This source follows frozen DESKTOP207; full CI, installed workflow and physical geometry qualification remain separate open gates.


### Installed connection and no-CAM Live cutter, 2026-10-06

DESKTOP207 independently matches frozen 3079b2c78076280e0e39cda46786b011343b7146 in all 503 packaged files and passes strict signature verification. DESKTOP206 recovery is retained. Native direct connection initially failed with Errno 65 while the same host/port was reachable from the terminal. Refreshing the existing app Local Network permission on/off/on restored connection without new access scope. Controller readback identifies C1 firmware 2.1.0c; downloaded configuration matches advertised MD5 1ab5731998af7c59b9762b573e78655e, 8192 bytes. Fresh telemetry reports Idle, and the Ubuntu camera updates independently. Native T3 preview and Follow program header restoration were exercised; ten pre-existing operator JSON stores remain byte-identical. Intermittent stale camera frames and complete geometric registration remain open. No motion, offsets, toolchange, upload/run or adaptive actuation was issued.

Native inspection exposed a further gap: Follow program without a CAM path cleared the cutter mesh even with a known reported tool. New source builds the static Live mesh from the reported number only when geometry exists, removes unknown-tool geometry instead of displaying a fallback, and hides it when pose is unavailable. Known-tool recovery rebuilds the mesh without requiring a manual preview override. Eight pose/context integration tests and 48 profile/scene regression tests pass; lint, formatting, diff and both architecture contracts pass. This correction postdates installed DESKTOP207 and still requires packaged native readback. Exact facb692 hosted run 37419326095 fails with 131 typing errors in 15 files (90 checked), removing 24 geometry contract diagnostics and adding none against b530610; hosted tests are skipped. Full CI and all physical acceptance gates remain open.


### Connection attempt feedback and recovery, 2026-10-06

The workbench now keeps a session-only immutable transport attempt record with its exact endpoint, elapsed time and terminal result. Failed attempts retain recovery guidance instead of silently returning to generic Disconnected. Network route/access, refusal and timeout guidance stays conditional; an errno does not assert an independently verified root cause. USB failures guide cable/device/serial ownership review. Pending attempts disable the profile connect action, while navigation remains available; a failure exposes an explicit retry rather than automatic reconnect. Success records transport opening only and cannot substitute for live status. The failure note grows with wrapped text and the header distinguishes failed from pending state. Records are not persisted to operator machine profiles. No permission change, automatic retry or new controller command is introduced.

Fifty-nine connection/workbench/unit checks pass, including blocked worker responsiveness, no duplicate transport attempt, event-loop-only completion, failed target non-persistence, retained guidance and separate live-state acceptance. The connection navigation test now locates the action by identity so it remains valid for Connect/Connecting/Retry captions. Focused strict checking passes the new machine contract; lint/format, diff and both architecture contracts pass. Final failure rendering was inspected with its endpoint, retry action and untruncated guidance visible. Connection and health now precede advanced capability/kinematic cards; UI timing details are disclosed on demand while measurements continue. Fourteen final navigation/selection checks pass, including disclosure, incomplete-profile guards and agreement between the slowest-session metric and its retained record. The initial missing-host guard failure and outdated caption assertion logs are retained; the guard was corrected and the timing assertion now verifies its actual retained duration. Installed qualification remains open. This source follows installed DESKTOP207 and the no-CAM static cutter correction. Exact 09ea156 hosted run 37420487723 remains failed with 131 typing errors in 15 files (90 checked); hosted tests are skipped. Full CI and all retained original/supplemental requirements remain open.


### Typed component and telemetry worker boundaries — 2026-10-06

Fixture/workholding preparation now declares independent generation, active and pending lane state and its UI-dispatch completion contract. Telemetry persistence declares immutable handoff input, sequence/loss metadata and complete queue/error/drain snapshots. The asynchronous architecture and failure behavior remain unchanged: superseded component work cannot publish, queues remain bounded, and flushed-to-OS records do not assert durability or complete capture. Thirty-six component, scene-loading, receive-heartbeat, telemetry-diagnostic and recovery tests pass on the prepared Python 3.9 runtime. Both modules pass focused strict typing; lint, format, diff and both architecture contracts pass. Full CI remains open. This checkpoint follows frozen DESKTOP208 at 83c7486 and is not included in that package. Native and physical qualification remain separate.


### Recovery and bank-draft contracts — 2026-10-06

Telemetry recovery now declares its pending/resumed/failed receipt, retained history, owner publication callback and explicit boundary/hash fields. Completion updates the operation record captured when its worker starts. Twenty-three recovery/receive/diagnostic tests pass after this change, including failed-byte retention, exclusive segment creation, distinct retries, readback mismatch, owner changes and no controller commands. The two-bank compiler now declares inherited state, inspectable export and body contracts; 25 remapping/export tests pass. Both modules pass focused strict checking, full lint/format/diff and both architecture contracts. These source changes postdate frozen DESKTOP208 and require later package qualification; they do not authorize bank execution or recover missing telemetry.

Hosted worker-contract run 37422367954 at 261446e removes 27 strict machine diagnostics with none added (131 to 104). Recovery/bank run 37422602918 at d45dcdb removes another 15 with none added (104 to 89 errors in 11 files, 91 checked). Its package baseline and architecture checks pass, but strict machine typing and downstream hosted tests remain open. The locked Ruff 0.16.0 formatter also exposed an existing readiness predicate layout that the global Ruff 0.12.7 did not detect. Formatting that expression with the locked tool passes all 520 file format checks and full lint; no predicate behavior changes. Ten operator stores still match their pre-build SHA256 hashes. DESKTOP156 relocation matches all 3,396 members and fresh strict signatures, retains its original path as a symlink and frees installation capacity; DESKTOP208 remains the same frozen 83c7486 build, now signing.


### Installed DESKTOP208 and no-CAM cutter readback — 2026-10-06

DESKTOP208 independently matches frozen 83c7486141d178f8fb52dd1850601db1b76e0e8b in all 504 packaged files, with no mismatches and strict signature verification passing. Archive SHA256 is 390bf04f7c416b1fe018c9db3984b14fb2a3dcaace3ef4a58d890089b79c3a48. Installation completed at 2026-10-06T06:21:10.097118Z after capacity/reserve verification; DESKTOP207, DESKTOP206 and DESKTOP205 recoveries remain available. The installed version was read back natively. Saved-profile direct connection to 192.168.0.79:2222 succeeds without further permission changes. Controller identifies C1 firmware 2.1.0c, with advertised/downloaded configuration MD5 1ab5731998af7c59b9762b573e78655e matching across 8192 bytes. Fresh Idle telemetry and camera updates were observed.

With no CAM program, native Scene selection loaded known T1 nominal geometry; returning to Follow program retained its cutter mesh and restored the machine/no-toolset header. Final native readback showed machine position (-232, -195.285, -3) mm and G54 work position (-232, -195.285, -53.480) mm, with 0.02-second telemetry and 0.2-second camera age. All ten pre-existing operator JSON files remained byte-identical. No motion, spindle command, offsets, toolchange, upload/run or adaptive actuation was issued. Native failure recovery was not deliberately exercised; intermittent camera staleness, physical cutter identity/dimensions and complete fixture/vise/stock registration remain open. Built, installed and scoped native receipts are retained under /Volumes/Wes Storage/CarveraBuilds/carvera-desktop208-20261006/.

Exact hosted run 37422948404 at 887f1c73d3805cbcb1986c4df3d060f18773efe3 is terminal: locked formatting, package baseline and architecture pass; strict machine typing still fails with 89 errors in 11 files (91 checked), and hosted tests remain skipped. Later worker/recovery/bank contracts and the inline profile-library work postdate frozen DESKTOP208 and require subsequent package qualification.


### Inline profile library and explicit save/load actions — 2026-10-06

Machine, cutter and ATC toolset profiles now open as a lazy, cached right-workbench section rather than a modal that obscures the machine and camera. Close returns to the originating section; normal history/compact navigation includes Profiles. Reopening unchanged store generation preserves the current editor without rebuilding it. Existing draft retention is maintained. The library toolbar uses balanced compact rows and the record list budgets its height so a 360-dp workbench retains at least 80 dp of scrolling editor space; actions remain pinned. Rendered 360/600-dp layouts were inspected.

Loading an unchanged saved profile no longer calls save or rewrites the profile JSON. A changed/new record clearly offers Save & use profile or Save & load preview; unchanged records offer their corresponding load action. Before loading, the saved row is checked against its edit baseline; a concurrently changed or removed row is rejected for reload instead of overwriting it. Twenty-eight profile/asynchronous-load checks pass, with byte/generation and no-command assertions. The workbench regression module passes 48 tests; 11 isolated navigation tests and 12 isolated draft/comparison tests pass. Final compact-height/editor-draft checks pass nine tests after the layout adjustment. Full locked lint/format/diff and both architecture contracts pass.

An earlier combined UI process failed focus/navigation assertions with retained modal state; another combined process passed 59 checks but failed a compact drawing-focus assertion that passes in the isolated draft run. Those logs are retained; combined-suite focus isolation remains open and these results are not a full-suite claim. Initial new-test setup errors (missing tool diameters and absent profile JSON before any save) were corrected without changing product validation. This checkpoint postdates installed DESKTOP208 and requires later package/native qualification. It sends no CNC actuation.


### Cutter-table and setup-comparison contracts — 2026-10-06

Cutter TSV exchange now declares record, changed-field and stable selection identities; complete-paste validation and ID-bound bulk updates retain their existing semantics. Reconciliation materializes one-shot available-ID iterators once so intersection cannot consume the input before current/anchor membership checks. A regression exercises range extension after iterator-based reconciliation. Setup-remedy comparison declares captured segments, tool/scene/stock inputs, cancellation and concrete contact tuples; independent stock clone returns are explicit. Required replacement/shift guards preserve the existing exactly-one-remedy rule. Twenty-nine table/remedy checks and focused strict typing pass; locked lint/format/diff and both architecture contracts pass. This source postdates frozen DESKTOP209 and requires subsequent package qualification.

Exact e4414f2 hosted run 37424689445 is terminal with unchanged strict-machine count (89 errors in 11 files, 91 checked); formatting, package baseline and architecture pass, hosted tests skipped. A trial test-only modal teardown improved the combined UI batch to 70 passes but did not resolve compact drawing input; the remaining failure included delayed ScrollView touch recursion. The speculative fixture change was removed and its failed log retained. Combined native drawing-click/focus qualification remains open; no test gate was suppressed.


### Installed inline profiles and compact browser disclosure — 2026-10-06

DESKTOP209 independently matches frozen e4414f2367ca4426557880f7a2a886aee1e0d256 in all 504 packaged files with zero mismatches and strict signature verification passing. Archive SHA256 is 6c6a1716d7349e675a2231894a7ddf3c08fa6749fdb1649f385441d020c22189. Installation completed at 2026-10-06T06:42:55.430722Z with DESKTOP208 recovery retained. Native title/version, automatic direct C1 Idle readback, camera updates, inline machine/cutter categories, unchanged saved T2 preview loading, Close returning to Program and cutter-editor retention on reopening were exercised. All ten pre-existing operator JSON hashes remain unchanged; no actuation was issued. Scoped native/build/install receipts are retained in /Volumes/Wes Storage/CarveraBuilds/carvera-desktop209-20261006/. Native draft/compact drawing-click, camera consistency and physical tool/workholding registration gates remain open.

Native review showed the embedded saved-record browser still crowded the editor. New source makes that browser a counted Browse/Hide disclosure in narrow workbench layouts, initially collapsed, while standalone/wide libraries retain their browser. Expanded search, filters and records remain accessible; collapsing does not rebuild or discard the editor draft. A 360/600-dp regression verifies browser open/close, accurate captions, retained draft, at least 160 dp of collapsed editor space, unchanged store bytes and no commands. Nine profile/compact checks pass, plus the final caption check; rendered layouts were inspected. This browser disclosure and the later contracts are not included in installed DESKTOP209 and need subsequent package/native readback.

Exact 627fee5 hosted run 37425323069 passes locked lint/format, package baseline and architecture; strict typing fails with 75 errors in nine files (91 checked), hosted tests skipped. Independent message/path diagnostic comparison against e4414f2 removes 14 errors and adds none. Full CI and all retained requirements remain open.
