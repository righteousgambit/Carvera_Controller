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
