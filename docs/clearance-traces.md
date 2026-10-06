# Continuous clearance traces

The Program workbench's material-removal section now captures its resolved
motion, immutable tool envelopes and obstacle bounds for a separate clearance
calculation. Review clearance plot runs in a worker, supports cancellation and
refuses results or source navigation after the program/setup/CAD context changes.
Stock grid and numerical clearance error are separate labeled inputs; the latter
accepts explicit length units such as `0.002in`.

For constant vertical tools the trace computes each motion/component's minimum
distance across all modeled obstacles and axial sections. Distance between a
translated cylinder and a box is convex in motion time. Golden-section search
retains an interval containing a minimizer; translation length times interval
width bounds the unsampled distance error. Reported lower/upper values bracket
the modeled minimum with a gap no larger than the requested tolerance. Existing
continuous contact checks establish a zero envelope gap without claiming a
localized contact time. Stationary distances are evaluated directly. Fixed tilted axes now use continuous convex support-plane distance bounds for the
entire translating cylinder. The cylinder-plus-segment support function includes
all intervening positions; it does not sample time. Feasible simplex combinations
provide distance witnesses and supporting planes provide lower bounds. Arithmetic
is shifted/scaled, near-dependent faces are skipped, and an outward numerical
margin widens the interval. At most 128 support evaluations are allowed per pair.
Intervals that exceed the requested precision are retained and explicitly counted;
no budget/stagnation fallback claims that precision was achieved. The public domain
is bounded to 1e9 mm coordinates/dimensions. Fixed-axis collision candidates use
these bounds after the broad box check, retaining every zero-lower-bound candidate.
Contact/near-contact is not a penetration depth or a measured contact time.

The chart shows interval minima, not instantaneous distance or penetration
depth. Component filters and near/automatic scales retain the complete report.
Render-only display bins keep the smallest lower bound; high values may be
visually clipped, while selection retains the actual numerical interval. Source
selection identifies the obstacle, assembly section, dimensions and CAD source.
Subdivided arcs carry source-line start/end ratios so navigation can seek into
the appropriate resolved portion. This ratio is preview interpolation, not
observed servo execution.

The calculation stops explicitly on cancellation or evaluation/record budget
exhaustion. An incompletely examined motion is never counted as completed.
Absent holder geometry, incomplete machine geometry, unconfirmed registration,
unsupported orientation and missing obstacle pairs remain unknown. The workbench captures its starting stock, including a matching imported
rest-stock snapshot, before subtraction. Clearance review replays completed
motions on an independent clone. Non-cutting bodies and rapid cutters are
checked against occupied cell boxes before each motion cuts. Cutting cutter
sections omit stock clearance. Only prior completed motions contribute removal;
same-motion cutting can still cause conservative body contacts. Contiguous X
runs compress occupied cells without replacing holes with a stock bounding box.
Numerical minimization error does not bound stock-grid error: removal classifies
cell centers, so empty cells are not proof of completely removed physical material.
The standalone API retains initial bounds when no stock state is supplied, and
labels that basis explicitly. Fixture/vise boxes, cutting cylinders and rotating CAD bands remain
conservative. Complete mesh/machine clearance, changing tool orientation,
exact physical residual-stock boundaries, physical registration and hardware qualification are
still open. This is partial progress on requirement 10 in
`controller-decision-and-advanced-machining.md`, not completion of that scope.

## Compact review workflow

Simulation uses one responsive scope/action toolbar: Whole program or Selected
operation, Simulate, Clearance plot and More actions. Stock save/load, reset and
change-impact review stay available in the menu. Calculation disables conflicting
actions and exposes Cancel in the section header. Expanding the section reveals
its header after layout, rather than leaving the inputs above the viewport.

Selecting a plotted interval updates source inspection without moving the
preview. Show motion in preview seeks the captured source ratio; Source details
reveals the operation explanation without seeking. A source selection on another
line clears the previous plot marker and geometry selection. Stale contexts refuse
both actions. Coverage, numerical tolerance, stock-grid basis and unknown counts
remain visible; Model details expands the full assumptions and missing geometry.
These are local preview interactions, not observed machine execution.

Captured clearance has its own input context, independent of any retained
residual-stock baseline. A program, assembly, stock, frame or workholding change
marks that capture historical during the normal metadata refresh, clears its
selection and disables plot/source/preview actions. This refresh does not read
CAD files. Explicit actions still verify exact asset bytes and can invalidate a
capture whose files changed at the same path. Invalidation remains in effect
until a new material-removal calculation captures the current inputs.

Change-impact review compares an invalidated clearance capture against its own
original context and names that baseline in the dialog. It therefore reports
the actual previous and current dimensions even if residual stock is absent or
has since been loaded from another snapshot. Historical traces remain visible;
they are not silently presented as current-path clearance.

## Candidate browser

Material-removal candidates are no longer truncated to the first twelve entries.
The workbench retains all unique captured line/component/obstacle tuples and
renders twelve rows per page. Search matches case-insensitive words across those
fields, and a component dropdown narrows the results. The count shows matching
and total candidates; changing a filter returns to the first page. Previous and
Next stop at the actual result bounds. With no candidates, the browser is omitted
from the workbench; absence of contacts does not establish clearance where
geometry remains unknown.

Candidate details retain the calculated obstacle bounds and assembly envelopes.
Show motion in preview uses the clearance capture's identity, not the identity
of a subsequently loaded residual-stock snapshot. A historical capture stays
inspectable as evidence, but its navigation action is disabled. Source inspection
and preview motion remain local; opening, filtering and paging send no machine
commands.


## Fixed tilted-axis checkpoint (2026-10-06 UTC)

The compact clearance card now uses a wrapping header, counts intervals above the
requested numerical target separately from missing model/reference evidence, colors
possible near-contact amber and explains witness fractions in the selected details.
It never labels a numerical witness as a measured machine contact. Tests compare
100 seeded vertical cases with the independent piecewise/golden-section calculation
and axis permutations, 60 oblique cases with analytic supporting-plane distances,
stationary/diagonal/mid-motion contact, tangency, reversal, translation, degenerate
precision and bounded-budget behavior. Source renders cover 400/1000 pixels.

DESKTOP196 predates this source checkpoint. Installed/native tilted calculation,
changing-axis sweeps, complete registered geometry and physical qualification remain
open. This is progress on collision checking and advanced clearance review, not
completion of their full requirements.

Validation at this source checkpoint: 88 focused geometry/clearance/residual-stock/
inspector regressions pass (one existing SSL warning), with 10 final clearance UI
checks after the compact-header refinement. The new solver passes strict typing;
repository lint/format and both architecture contracts pass. Earlier failed attempts
are preserved in `/private/tmp/carvera-tilted-clearance-*-20261006.log`.

## Complete interval inspection

The plot's rendering bins do not define the available inspection records. A status
filter exposes all intervals, possible contact/near-contact, unresolved precision or
positive lower bounds, combined with the component filter. Previous/Next visits every
matching captured interval in report order, including intervals with no upper bound
that cannot be drawn as numeric bars. Matching/total and selected-position counts remain
visible. Filter changes clear excluded selections; reports reject detached old point
objects. Source-selection changes and stale-context invalidation reset the navigation
state and cannot re-enable current-path actions. Navigation inspects source locally;
preview movement still requires the separate preview action. Physical machine control
is not invoked.

This source checkpoint postdates installed DESKTOP197. Native complete navigation
acceptance remains open. Tests inspect all 50 retained intervals even when display bins
omit most, exercise unknown upper bounds, combined filters, boundaries, replacement
reports and full-workbench historical-source guards.

Repaint responsiveness checkpoint: report/filter/component/bucket ownership now
keys one retained display-bin preparation. Selecting an interval, translating the
view, changing height or scale repaints the bounded bins without rescanning the
complete report. A 10,000-record instrumented regression proves this and verifies
filter, component, width, replacement-report and empty-report invalidation. It is
an operation-count check, not a measured native frame-rate guarantee. The combined
clearance/navigation/geometry/inspector suite passes 46 checks; lint/format and both
architecture contracts pass. Installed navigation/large-report latency acceptance
remains separate.

## Assembly envelope input contracts

CAD loading exposes the validated mm/+Z/tip-or-collet triangle schema and exact
converted byte identity. The procedural profile API declares its axial/radial
point pairs; assembly clipping retains explicit three-coordinate vertices.
Envelope construction rejects non-finite registration/clipping heights, unknown
components, missing/non-finite/non-positive exposed stickout and cutting lengths
outside that exposed span before constructing sections. Overall catalog length
does not substitute for exposed stickout. Existing clipped-edge, shoulder and
content-bound holder regressions remain in place.

The 158 focused geometry/CAD/profile/assembly checks pass at this source
checkpoint. This strengthens preparation errors and model contracts; registered
physical geometry and complete machine collision qualification remain open.
These changes postdate the frozen DESKTOP211 package.

Simulation tool preparation also rejects missing/non-finite/non-positive cutting
diameters with a T-number and a direct instruction to correct the saved profile.
The issue preflight and full preparation share this check; the former retains
its disk-free asset policy. Combined assembly/CAD/profile/simulation checks pass
174 cases after this addition. Installed/native behavior remains open.
