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


## Declared engagement and cutting demand

The collapsible Engagement & cutting demand section accepts radial width and
axial depth together. Width must be between zero and the effective tool diameter.
Nominal rectangular engagement gives Q = width × depth × feed in mm³/min,
with an in³/min conversion. This is a continuous-contact process assumption;
program import does not infer stock contact or variable engagement.

An optional operator-supplied specific cutting energy in J/mm³ gives estimated
cutting power P = Q × energy / 60 in watts and torque P × 60 / (2π × RPM) in Nm.
No material coefficient is chosen. The report repeats engagement and energy
assumptions. Power and torque ceilings are independent supplied comparison
values, not a measured machine envelope. Without energy, demand stays unknown;
ceilings remain explicitly unassessed. Partial engagement inputs and energy
without engagement are rejected. Zero width/depth/feed yields zero nominal
demand. Collapsing the section retains inputs and the report remains explicit.

This model excludes variable stock contact, cutting-force detail, drive losses,
unloaded spindle demand, efficiency, chip thinning, chatter and measured machine
capacity. The broader feasibility requirement remains OPEN.

## Operation-linked cutting settings

Operation selection now exposes a paged review of distinct declared tool,
units/feed mode, converted feed and RPM settings. Repeated resolved feed lines
are grouped, with their count and first/last source references retained.
Rapid lines are counted separately. Unsupported modal states and unresolved
motion geometry are excluded with reason counts; they are never silently
converted into a valid cutting setting. Selecting a setting opens the existing
bench with the exact program hash and representative source-line snapshot,
without changing preview selection, rewriting the program or commanding a tool.
The captured review refuses routing after program/operation replacement.

The display is bounded to twelve settings per page. This advances operation
context for feed/speed review; engagement, material coefficients, measured
machine capacity and full physical process feasibility remain OPEN.

Source checks: 50 model/integration checks passed, including actual operation
action routing, pagination, stale review rejection and narrow rendering. The
additional tool-boundary/stopped-spindle test passes in a 40-test model run.
Three changed production modules pass typing and both architecture contracts
pass. Installed workflow acceptance is pending for this source checkpoint.
