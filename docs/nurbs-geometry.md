# Preserved rational curves and local conversion

`NurbsCurve` retains original controls in mm, positive weights, the knot vector
and degree. `tessellate_nurbs` converts clamped continuous curves of degree 1–16,
up to 4096 controls, without changing the retained source representation. General
nonclamped and discontinuous curves are explicitly refused rather than silently
reinterpreted. A dialect adapter must provide its real knot convention and modal
coordinates; this geometry module does not interpret or emit machine commands.

Interior knots are inserted to degree multiplicity in homogeneous coordinates.
The resulting rational Bezier spans are subdivided in homogeneous coordinates.
For each candidate chord L and rational span N/W, the converter bounds the norm of
N−WL through its Bernstein coefficient hull and divides by the smallest positive
weight. This gives an analytic parameter-matched position bound, including
collinear curves whose weights change parameter speed. A floating-point allowance
increases with coordinate magnitude, weight ratio, knot spacing and parameter
conditioning. This is a numerical allowance, not a formal interval-arithmetic
proof or a certificate of executed-machine accuracy.

Each output interval retains its original parameter endpoints. The returned bound
covers position conversion only; length, tangents, dynamics and backend execution
remain separate. Original positive-weight control-hull bounds enclose the curve.
The converter refuses insufficient segment budgets, extreme weight/knot
conditioning, indistinguishable output parameters and depth exhaustion. It checks
cooperative cancellation during knot insertion and subdivision; no incomplete
polyline is returned.

Validation includes an exact rational circular arc, degrees 1/2/3/5/8/16,
nonuniform and repeated interior knots, an independent original-knot de Boor
evaluator, 100 seeded weighted curves, weight-scale and parameter-domain
invariance, and invalid inputs/budget/cancellation/precision refusal. Together
with existing polynomial spline regressions, 71 tests pass. Strict isolated
module typing and focused lint/format checks pass.

LinuxCNC describes G5.2/G5.3 as an experimental NURBS data block. Its source
semantics, program analyzer integration, linked UI inspection, actual backend
exercise and installed qualification remain OPEN. The converter alone does not
close requirement 20 or the broader controller goal.

Primary dialect reference:
https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g5.2-g5.3
