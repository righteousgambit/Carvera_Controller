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
localized contact time. Stationary distances are evaluated directly. Tilted
tools yield only conservative swept-box lower bounds and are not plotted as
known numeric clearances.

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
unsupported orientation and missing obstacle pairs remain unknown. Initial
stock is omitted for cutting cutter clearance but retained for non-cutting
bodies and rapid cutter motion, so already-cleared pockets can yield false
contacts. Fixture/vise boxes, cutting cylinders and rotating CAD bands remain
conservative. Complete mesh/machine clearance, changing tool orientation,
residual-stock body tests, physical registration and hardware qualification are
still open. This is partial progress on requirement 10 in
`controller-decision-and-advanced-machining.md`, not completion of that scope.
