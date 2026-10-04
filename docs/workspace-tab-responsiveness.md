# Workspace tab responsiveness

Tab selection captured navigation context by serializing full loaded CAD meshes
on the UI thread, on departure and arrival. Updating the hidden section chooser
could also re-enter selection and repeat these captures. The C1/Saunders/vise
profile contains 3,707,460 numeric vertex entries. Three initial serializations
took 0.8281, 0.8058 and 0.7938 seconds each on this machine.

Loaded MachineProfile metadata is now recursively immutable, detached from the
input dictionary, and canonically serialized once during profile construction.
Navigation hashes reuse that serialization while freshly capturing setup,
tooling and view state. Mutable adapters continue fresh serialization. The final
canonical bytes are identical to the historical encoding, so bookmark identities
remain compatible. Changing geometry requires loading a replacement profile;
the cached metadata cannot silently diverge through supported public mutation.

The hidden chooser callback ignores a section already being selected. A tab
click therefore has one navigation arrival rather than recursively selecting it.

Under concurrent source tests, legacy serialization took 1.6507 seconds; cached
assembly/hash took 0.0524, 0.0460, 0.0205, 0.0197 and 0.0211 seconds. The old/new
hashes matched exactly. These are context-processing measurements, not end-to-end
native click latency or a guarantee that every source of UI delay is resolved.

Source validation: 56 focused model, profile-loading and Kivy navigation checks
passed in 123.75 seconds (one existing locale deprecation). Tests cover input
alias isolation, immutable cached metadata, canonical legacy bookmark identity,
mutable-adapter edit detection, one navigation arrival per tab click, scene and
program navigation, and rejection of changed setup/tool geometry. Ruff lint and
format, whitespace checks and both architecture contracts passed.

DESKTOP117 installed/native checkpoint: source
`2772bf8a044fc6e54807fbf264419afc10b8fb4e`; 437 packaged files matched, strict
signatures passed for built/installed/recovery116 bundles. All eight workspace
sections and Profiles were exercised with the full loaded machine/plate/vise
geometry. Back restored Machine from Camera. Fresh camera and telemetry remained
visible, with no reconnect overlay during navigation. Native click latency was
not instrumented. No program was loaded and no machining command was issued.
Eight operator stores and Kivy config were restored exactly after clean test exit.
Normal relaunch PID 30500 was left in Live view, reported Idle, T1/TLO 50.480 mm,
0 RPM/feed; camera 0.6 seconds old and telemetry 0.23 seconds old at final capture.
Receipt: `/Users/wes/Downloads/carvera-desktop117-20261004/native-receipt.json`.

## Selection highlight rebuild (DESKTOP124)

A second source of blocking was `GcodeViewer.set_inspected_component`: selecting
Scene, switching its component or clearing inspection rebuilt every CAD group,
recomputed its bounds, transformed all vertices and created fresh GPU meshes.
The geometry and placement had not changed. With the actual
`c1-v9-saunders-vise.json.gz` loaded, changed selections took 0.8556–0.8852 seconds
on the UI thread (source-app diagnostic, October 4).

Inspection now changes one shader uniform per existing render context. Mesh
colors, geometry snapshots and section calculations remain intact. The shader
preserves vertex alpha and the same teal highlight; cutter and pose-marker
contexts explicitly keep highlighting off. Real geometry/setup edits still
rebuild the scene and reapply the selected highlight.

The same source-app diagnostic measured 0.033–0.045 milliseconds for changed
component selections and 34–40 milliseconds for each of the eight workspace-tab
callbacks. These timings measure synchronous callback work, not input-to-display
latency. The integration regression prevents any mesh rebuild or buffer/snapshot
replacement during selection and tab navigation, exercises all eight tabs and
asserts no controller commands are sent. It can be run against a local real CAD
asset using `CARVERA_TIMING_CAD`, and writes measurements when
`CARVERA_TIMING_OUTPUT` is set. Default test runs use the available model.

Diagnostic evidence is retained in
`/Users/wes/Downloads/carvera-desktop124-20261004/highlight-before.json` and
`highlight-after.json`. Installed/native acceptance is recorded separately.

Source validation for DESKTOP124: 15 focused Kivy checks passed in 64.88 seconds,
including real-CAD selection/tab buffer reuse, shared history, section
cancellation/dense rendering and highlight preservation. Ruff lint/format,
whitespace and both architecture contracts passed. The broader run was 49 passed,
2 failed; both failures were independently reproduced using the archived
DESKTOP123 source: profile form viewport height at narrow size, and a wheel test
that assumes the former Preview screen's first child is a ScrollView. Their
logs are retained as `broader-tests.log` and `baseline-failures.log`. The broader
suite is not claimed green.

Installed/native DESKTOP124 checkpoint: source
`795cb953a16ca0f8a80f0c5a6c7fa8ff7cb19f33`; 441 staged, built and installed
application files matched the manifest, 438 repository files matched (generated
version/locale files excluded), and strict signatures passed for the build,
installed app and preserved DESKTOP123 recovery bundle. Native clicks exercised
all eight tabs plus Profiles. The Scene stock highlight displayed correctly;
camera and telemetry remained fresh through navigation. Native click-to-display
latency was not instrumented. After clean test exit, eight operator-store states
and the Kivy configuration were restored exactly. Normal relaunch was left in
Live view, reporting Idle, T1/TLO 50.480 mm, 0 RPM/feed and no program selected.
No machining, tool change, program upload/start or offset write was performed.
Receipt: `/Users/wes/Downloads/carvera-desktop124-20261004/native-receipt.json`.
This closes the bounded selection-rebuild fix; broader UI/workflow ledgers and
the two baseline test failures remain open.
