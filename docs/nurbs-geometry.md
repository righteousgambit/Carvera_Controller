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
with existing polynomial spline regressions, 78 tests pass. Strict isolated
module typing and focused lint/format checks pass.

LinuxCNC describes G5.2/G5.3 as an experimental NURBS data block. Its source
semantics, program analyzer integration, linked UI inspection, actual backend
exercise and installed qualification remain OPEN. The converter alone does not
close requirement 20 or the broader controller goal.

Primary dialect reference:
https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g5.2-g5.3

The `linuxcnc_g52_curve` adapter maps order (default 3) to degree and generates
the official uniform clamped knot convention. Its caller must supply the
pre-block current position as the first control and resolve modal coordinates.
Order 1 introduces discontinuities and is explicitly refused by this continuous
converter. This does not yet parse a complete G5.2/G5.3 data block.

The knot convention was checked against LinuxCNC source revision
`46a388fd15a477b4bf2ce090919b0273074e7fc1`, function
`nurbs_G5_knot_vector_creator`:
https://github.com/LinuxCNC/linuxcnc/blob/46a388fd15a477b4bf2ce090919b0273074e7fc1/src/emc/rs274ngc/nurbs_additional_functions.cc

A subsequent read of the same pinned `interp_convert.cc` exposed a version
distinction: default order is3, but a source L word changes the effective order
only when it exceeds3. `linuxcnc_g52_effective_order` models that interpreter
behavior separately from the mathematical knot generator. The generator takes
an already resolved effective order; calling it directly with an uninterpreted
L word is incorrect. The interpreter also handles XY, YZ and XZ planes and
updates the current position at block closure, so incremental control coordinates
require the pre-block position rather than a fictitious sequence of tool moves.
Complete program integration must retain this version binding; the general
documentation alone is insufficient to qualify backend semantics.

## Complete version-bound data block

`parse_linuxcnc_nurbs_block` accepts a complete G5.2/G5.3 data block plus an
explicit pre-block position, plane, unit scale and distance mode. It preserves
original source SHA256, start/end lines and each control's source line; the
implicit current-position control has no invented source line. All three
principal planes are supported. G91 controls use the pre-block position as
observed in the pinned interpreter, rather than accumulating previous controls.
Opening axes assign P to the new control and leave the implicit first weight1;
opening without axes assigns P to the implicit control.

This version's interpreter initializes P to−1 and requires positive P for later
controls. The parser therefore refuses omitted P on added controls despite the
general manual's stated default. It models effective L order separately, permits
explicit repeated G5.2 and retains unit-normalized final G94 feed context. It
refuses incomplete blocks, expression/control-flow syntax, duplicate words,
unrelated motion/modal/axis/side-effect words, fractional N and feed overflow.

Two boundary failures (fractional N and feed-unit overflow) were reproduced and
corrected with retained test logs. The complete block, rational and polynomial
regression set now passes102 tests; strict isolated typing passes both modules.
The enclosing analyzer and linked review are now implemented as described below.
Supported backend exercise remains OPEN; this parser does not claim an executable program.

Interpreter, defaults and generic word checks were inspected at the same exact
revision in `interp_convert.cc`, `interp_internal.cc`, `interp_read.cc` and
`interp_check.cc`; downloaded sources and Git blob identities are retained in the
local NURBS artifact evidence directory.

## Whole-program and linked review

The explicitly selected LinuxCNC study dialect collects a complete data block
before publishing any geometry. Control rows retain the pre-block position and
each row's modal feed. Converted cutting motion is attributed to G5.3 closure,
which sets the final position and clears the motion mode as the pinned interpreter
does. A following move needs its own motion command. Original program bytes and
hash remain unchanged; the block additionally retains its exact captured-text
hash, source span, control-source lines and interpreter revision.

Every source row in a resolved span opens the same immutable curve review.
Rational and polynomial curves share one whole-program segment budget. The
frame bounds use the positive-weight control hull; declared work offsets affect
operation bounds but do not alter the stored work-frame controls. Estimated time
is nominal converted-path length at the final G94 feed, without a length-error
certificate or acceleration model. Missing or overflowing timing remains unknown.
G93/G95 data blocks are explicitly unresolved pending their dialect qualification.
Incomplete, invalid, default-Carvera or unresolved-context blocks publish no
control-row motion and remain unresolved; cancellation propagates without a
partial analysis. Recovery inside a data block is refused even when external
position and clearance evidence is supplied.

The linked review projects the active XY, XZ or YZ plane with equal axis scale.
Exact converted segments are paged in contiguous 256-segment sections; the
coarse whole-curve context has no separate display-error bound. Controls, weights
and knots are paged in 16-entry sections while the complete control polygon stays
visible. The implicit pre-block control is labeled explicitly. The source span,
closure line, complete program/block hashes and pinned interpreter identity are
shown. Source-span warnings now survive move-inspector lookup on both control
rows and closure. This review does not seek the legacy machine/toolpath viewer or
send controller commands.

Installed/native qualification of this new whole-program UI, supported backend
execution, missing feed modes and full advanced simulation remain OPEN. The
current installed DESKTOP283 contains the preceding keyboard/polynomial work,
not this new rational program integration. Requirement20 remains OPEN.
