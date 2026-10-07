# Declared feed and chip-load review

Setup > Tools > Feed & chip load opens a local milling-parameter bench. An
eligible inspected source line also offers Review feed & chip load, opening the
bench with a detached program-hash/line/modal-state snapshot. The bench copies
G94 feed per minute or converts G95 feed per revolution using explicit spindle
RPM. It rejects G93 inverse time, unknown/stopped spindle, rapid/unknown motion,
unknown units/tool, tool mismatch, unresolved modal errors and unbounded values.
Unsupported constant-surface-speed commands retain interpreter errors and are
not treated as RPM.

Diameter is an editable declared library value if a nominal tool is selected.
Effective cutting diameter and active flute count are explicit assumptions.
RPM/feed fields accept shared imperial/metric quantities. Optional ceilings for
RPM, feed and nominal chip load are compared independently; omitted ceilings
remain unassessed. Editing a field clears the old result. Failed source import
retains existing fields and clears the result. Nothing saves a tool profile,
rewrites a program or sends a controller command.

The model calculates nominal chip load F/(N*z), feed per revolution F/N and
cutting speed pi*D*N. These are kinematics, not actual chip thickness or machining
feasibility. Engagement, axial/radial depth, material/cutter capability, runout,
power, torque, stability, effective tool diameter and physical machine limits
remain unqualified. No cutting permission or machine limit is inferred.

Source validation: 34 affected/neighboring checks passed before the final small
chip-ceiling and step refinement. The final 27-check model/bench suite passes. Changed-module
typing, Ruff and both architecture contracts are checked separately. The
360-dp one-column bench was visually reviewed. Initial test failures from an
incorrect parser factory name were retained and corrected to from_text.
Packaging, installed workflow acceptance and physical qualification are separate
OPEN gates until their receipts are available.

This advances part/process requirement 15; full feasibility including engagement
and qualified machine/tool constraints remains OPEN.
