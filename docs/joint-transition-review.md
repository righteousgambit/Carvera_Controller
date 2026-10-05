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
The rendered 360 dp transition section was visually reviewed. Installed/native
acceptance is separate and remains open until its explicit receipt.
