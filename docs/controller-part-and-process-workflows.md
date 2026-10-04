# Part and process workflow requirements

These additional 25 requirements retain the complete recommendation scope.
Every full workflow remains OPEN. Source, desktop interaction, installed runtime,
backend execution and physical acceptance are independent gates.

1. Operation tree tied to scene entities, tools, parameters and selected paths.
2. Dimensioned section views through stock, fixtures and machine structures.
3. Semantic program comparison by features, parameters and changed motion.
4. Modal-state inspector covering units, planes, offsets and compensation.
5. Setup dependency map with reviewed downstream consequences.
6. Operation-linked camera framing with explicit digital zoom and context.
7. Visual setup change journal retaining photos and geometry revisions.
8. Grouped, actionable alarms distinguishing machine and observation failures.
9. CAD feature association with operations, nominals, tolerances and results.
10. Remaining-stock evolution across operations and tool changes.
11. Rest-machining analysis identifying inaccessible remaining material.
12. Finish-quality overlays with assumptions and inspected-result comparison.
13. Face/region-specific roughing and finishing stock allowances.
14. Complete facing footprint coverage, margins and measured surface-map use.
15. Feed/speed feasibility against tool, engagement and machine constraints.
16. Tool-deflection estimates with assumptions and dimensional consequences.
17. Backend-aware drilling cycle preparation, visualization and execution.
18. Thread specification, preparation, supported machining and gauge results.
19. Fixture layout alternatives with reach and measured placement evidence.
20. Multi-part nesting, retention and machining-order comparison.
21. Postprocessor reference qualification with intended/interpreted motion.
22. Physical feed-mode interpretation, translation and rotary diagnostics.
23. Rotary setup placement optimization against reach and unwind constraints.
24. Measured volumetric error maps and supported compensation ownership.
25. Turning/mill-turn stock evolution, tools and explicit diameter/radius modes.

## Operation facts source checkpoint

Operation selection now exposes resolved rapid/feed path lengths, resolved and
unresolved motion-line counts, work frames, programmed spindle range, and feed
ranges grouped by feed mode and program units. Arcs use the existing interpreter's
chord-tolerance subdivision; path length is therefore an approximation. Unresolved
approaches and unsupported motions are excluded and their count remains visible.
Feed moves do not establish stock contact; these are program facts rather than
measured machine motion or material-removal results. No commands are issued.

Existing selection still seeks the rendered preview. This does not establish
CAD feature association, full operation editing, stock contact, machine-space
clearance, installed acceptance or physical qualification. Those remain OPEN.

Validation: 31 operation-model checks passed, including mixed program units/feed
modes, operation boundaries, unresolved motion, foreign-operation rejection,
arc approximation and rapid-feed exclusion. Seven Kivy selection/navigation
interaction checks passed (133.63 seconds; one existing locale deprecation),
including actual operation-row dispatch, preview selection, readable flowing
summary and no command send. Ruff lint/format, diff whitespace and both import
architecture contracts passed. This is source and source-runtime evidence;
packaging and installed visual acceptance have not been performed for this change.

## Compact operation inspector

The selected operation now has a responsive summary card for resolved path,
motion-line completeness, work frames and program tools. Detailed process ranges,
bounds and warnings are expandable. Warning count stays visible on the disclosure
action. Tool-specific review buttons route to the existing comparison/calibration
inspector and select the corresponding tool number; these actions neither select
a physical cutter nor send commands. Loading/unloading a program clears the old
card and disclosure state. Operation selection remains tied to preview seeking.

CAD feature identity, editing operation parameters, validated engagement and
physical machining remain OPEN. This UI checkpoint does not close requirement 1.

Validation: the broad pass completed 55 model/navigation checks. The final card
interaction passed after responsive sizing/alignment changes (20.18 seconds;
one existing locale deprecation), exercising wide two-column/narrow one-column
layouts, actual detail disclosure, tool-review routing and program unload. Both
final card PNGs were visually reviewed. Ruff lint/format, diff whitespace and
both architecture contracts passed. Installed acceptance remains OPEN.

Operation-row selection now explicitly reveals the operation card at the top of
the report viewport; source-line inspection retains its individual-move reveal.
A final interaction verifies the selected operation heading lies inside the
actual Program task viewport (17.25 seconds, passed). The DESKTOP118 artifact
started before this correction and is superseded; it will not be installed.


DESKTOP119 installed/native checkpoint (2026-10-04): application source
`c50c97a4115a347f137b54f2a394dbe6cad18439`; 437 staged, built and installed
files matched; strict signatures passed for built, installed and recovery117.
Native local-only preview verified rough/finish operation selection and automatic
summary reveal, process disclosure/collapse, Review T1 routing to Setup,
selection persistence across Program/Setup, and Scene/Camera navigation with
fresh camera and telemetry. Operator stores and Kivy configuration were restored
exactly after clean test exit. Normal relaunch PID 36609 was left in Live view,
Idle, no program selected, reported T1/TLO 50.480 mm, 0 RPM/feed; camera and
telemetry were 0.4 seconds old at final capture. No upload or machining action.
Receipt: `/Users/wes/Downloads/carvera-desktop119-20261004/native-receipt.json`.
This closes this compact-inspector installed acceptance checkpoint only;
requirement 1 and the full workflow ledger remain OPEN. Native tab latency was
not instrumented; the geometry serialization fix is unchanged from DESKTOP117.


## Structured modal-state inspector

Source-line details now contain a before/after inspector for fifteen program
state fields. Changes-only is the default; Show all includes inherited values
and explicit unknowns. Before/after values stack at narrow widths. Feed meaning
changes are highlighted even when an F value is unchanged across a units change.
Pending tool, program tool, H selection, cutter compensation, spindle mode and
spindle speed remain distinct. The parser records G40 and requested G41/G42/D
compensation; offset paths remain unsupported and unresolved, including later
moves after cancellation when interpretation is already uncertain. The inspector
never supplies initial controller defaults or numeric H/D/offset values.

Source validation: 45 model checks and 57 dependent bank/preflight checks passed.
Nine actual Kivy navigation interactions passed in 74.14 seconds, including
wide/narrow modal panels, actual filter/disclosure actions, inherited states,
program unload and no command sends. Wide and narrow panels were visually
reviewed; a missing-font arrow glyph found in that review was replaced with
plain text. Installed acceptance remains OPEN for this change. Requirement 4
remains OPEN for numeric transform/offset ownership and backend qualification.


DESKTOP120 native acceptance found a filter expansion scroll jump: increasing
the inspector height preserved a normalized outer scroll position and hid the
filter header. That installed checkpoint remains OPEN; its screenshot and
receipt are preserved in the DESKTOP120 archive. The follow-up queues an
explicit header reveal after either filter action. The actual Kivy interaction
regression verifies header visibility after both transitions and passed in
19.00 seconds. DESKTOP121 installed acceptance remains pending.


DESKTOP121 installed checkpoint: application source
`2f9f455f4aadc35e21a905da95829304cd0acfad`; 436 repository files and 439
staged/built/installed files matched. Strict signatures passed for the built,
installed and preserved DESKTOP120 recovery bundles. Nine navigation interaction
tests passed in 78.70 seconds. Native line 7 inspection showed the units/feed
transition; Show all and Changes only both kept the header/filter visible.
The native workspace tab sequence reached Camera with fresh camera/telemetry;
click latency was not instrumented. Eight stores and Kivy config were restored
exactly after clean exit. Normal PID 46162 was left in Live view, no program,
reported Idle/T1/TLO 50.480 mm/0 RPM/feed, with camera 0.1 seconds and telemetry
0.12 seconds old at capture. No machining commands were issued.
Receipt: `/Users/wes/Downloads/carvera-desktop121-20261004/native-receipt.json`.
This closes the modal filter installed checkpoint; requirement 4 and the full
workflow ledger remain OPEN.


## Dimensioned CAD sections

Scene component inspection now includes X/Y/Z plane selection, a nominal CAD
coordinate, a midplane shortcut, a proportioned contour plot and in-plane
minimum/maximum/span dimensions. The worker intersects the exact rendered
triangle snapshot, including declared stock and placed workholding. It cancels
coplanar triangulation diagonals, retains open mesh contours, rejects malformed
geometry and refuses sections beyond the display budget. It does not infer
solid area, wall thickness, closed topology, live machine pose or physical
clearance from these line segments. Coordinates precede live joint transforms.

Calculations run off the UI thread with bounded progress and cancellation.
Changing the component or rendered geometry rejects late results; changing the
plane clears the previous result. Controls remain available for navigation while
a calculation runs. The plot uses uniform scale and collapses when no contour
is available. This advances requirement 2; measured frame qualification,
installed acceptance and the full workflow ledger remain OPEN.

Source checks: 47 model/scene/renderer/navigation interactions passed in
85.35 seconds. Two final section-workbench actions passed in 19.03 seconds,
including cancellation with late result rejection and switching to Camera during
a held worker. Both architecture contracts passed. Wide/narrow source rendering
review exposed cached-center alias ordering during resize; the correction and
rendered-vertex containment regression passed: two interaction checks in
16.27 seconds. The corrected narrow plot was visually reviewed.


Real-asset qualification found the initial section display limit unsuitable for
the Saunders plate: its 99,760 triangles produce 43,520 midplane segments.
DESKTOP122 packaging was deliberately stopped (terminal exit 1) and the build
was never installed. Its diagnostic receipt preserves this finding. The
successor allows 200,000 segments and renders batches of at most 64,000 vertices
to respect Kivy's 16-bit mesh index limit. A dense-render test found recursive
height dispatch could duplicate batches; height now settles before instructions
are cleared and rebuilt. Fourteen focused checks passed in 16.84 seconds,
including exact retained segment counts and bounded mesh indices.

Pure-model checks of the current CAD asset (SHA-256
`ff5ae4980b41a8280127922286c0dc452c991214db952bed3e766855382464bb`)
resolved all 43,520 fixture contours in 0.434 seconds, 1,640 vise contours in
0.031 seconds, and fixed-machine/spindle sections. These are worker calculation
measurements, not installed click latency or physical-placement qualification.
DESKTOP123 installed acceptance remains OPEN.
