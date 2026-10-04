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
