# Declared joint transition review

Machine > Five-axis reachability & branches > Joint transition review examines
ordered joint positions against the imported or illustrative kinematic geometry.
It never uploads a program, applies an offset or sends a motion command.

Enter two to eight rows in the shared joint-state editor, using the displayed
joint order. Compare seed branches treats those rows as independent solver seeds;
Review entered joint route treats them as ordered waypoints. Copy solutions to
waypoints explicitly replaces the rows with locally converged endpoint solutions,
opens the transition section and invalidates the prior branch result. It does not
assert that the connecting route is a constant-tip or constant-axis path.

Set maximum linear and rotary sample steps with unit expressions, then review.
Each segment is interpolated in the entered joint coordinates. Full rotary turns
are retained: C0 to C360 is a complete turn, not a stationary equivalent endpoint.
All endpoint limits and the 2001-sample budget validate before local rank work.
Changing inputs or cancelling discards a pending path rather than publishing a
partial or obsolete result.

The trace plots local tip/axis Jacobian rank against sample order, not time.
Red ticks identify samples with dependent task directions. The first such sample
is selected automatically. Click the trace or use First/Previous/Next/Last to
inspect the sample's joint positions, declared limit margins, cumulative absolute
joint travel, tool tip and axis in work coordinates. Reported tip deviation is
measured against the straight chord between each pair of waypoint tool tips.
It exposes the curvature of joint interpolation; it is not a machining tolerance
or controller TCP compensation error.

The finite-difference rank diagnostic uses the existing normalized-column
residual threshold of 1e-3. A full-rank endpoint does not establish a full-rank
transition, and finite sampling cannot establish behavior between samples.
Clearance, machine structures, cable travel, rates/acceleration, firmware
interpolation, TCP, backend execution and physical registration are separate
requirements. This review does not certify a transition for execution.

Source verification (2026-10-05): 45 branch/path/workbench tests pass, including
valid endpoints crossing a dependent interior posture, explicit full turns,
three head/table topologies, sample spacing, total budget, cancellation, stale
result rejection, unit-aware controls, plot selection and narrow layout. Two
architecture contracts, focused strict typing, Ruff/format and diff checks pass.
The rendered 360 dp transition section was visually reviewed. Installed DESKTOP184 at source 0b9b921 was independently verified against
492 manifest files with zero mismatches and a valid strict signature. Native
CUA review selected the 91-sample head/head route: both endpoints showed rank
5/5, with the interior sample 46 showing rank 4/5. First, Last and trace selection
agreed. Endpoint-copy workflow and full physical acceptance remain open.
Receipts: `/Volumes/Wes Storage/CarveraBuilds/carvera-desktop184-20261005/`.


## Continuous declared-body clearance

The separate Continuous machine-body clearance section uses the same two to
eight entered joint waypoint rows and declared kinematic profile. It tests every
non-excluded body pair on every segment, including full unwrapped rotary turns.
The sampled Jacobian diagnostic above remains separate from this calculation.

At each interval midpoint, oriented bounding boxes are checked on all 15
separating axes. An analytic bound on every body point's displacement over the
entire interval enlarges the separating margin. Linear travel and nested rotary
pivots contribute to that bound; both workpiece and spindle chains may move.
Intervals that cannot be excluded are bisected chronologically. The first
possible interval for each pair/segment is retained once its combined motion
bound is within the chosen tolerance (0.000001–10 mm). This tolerance is an
unresolved motion enclosure, not a measured clearance, machining tolerance or
exact contact time. A midpoint declared-box overlap is identified separately
from a conservative interval without an overlap witness.

Selecting a possible contact shows the segment, fraction range, joint values,
motion bound and equal-scale XY/XZ projections at the selected midpoint. Bodies
in the selected pair are highlighted. A clear report covers only the declared
boxes over the entered piecewise-linear joint route. Missing structures, exact
CAD surfaces, measured registration, cables, cutter/material interaction,
firmware interpolation, TCP and backend/physical execution remain unqualified.

The shared limit is 50,000 interval checks with a maximum subdivision depth of
40. Cancellation, exhaustion, invalid limits or worker failures withhold the
new report. Input changes and closed panels reject stale worker completion;
worker launch failures release the controls. Work remains off the UI thread.
No review or file action sends a controller command.

Save clearance review writes a bounded 2 MiB `.cvclearance` file containing the
profile, body exclusions, route, tolerance, method, report and payload digest.
Load rejects duplicate fields, unsupported schemas/methods and integrity errors,
then recomputes clearance and compares the entire result before replacing the
current local declaration/result. A re-signed but false report is refused.
Rejected loads retain the prior geometry and result. File picker callbacks also
check the input generation so a stale review is not exported after editing.
A file digest establishes byte identity only, not physical machine clearance.
