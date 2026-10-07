# Bounded LinuxCNC cubic analysis

`ProgramOperations.from_text(..., dialect="linuxcnc")` explicitly enables the
LinuxCNC G5 cubic interpretation described in the
[stable G-code reference](https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g5).
Default Carvera analysis rejects G5 and keeps subsequent motion unresolved after
that unknown modal command. Selecting a declared analysis dialect does not
establish connected-controller support or enable upload, execution or postprocessing.

Each resolved cubic retains its source line, original four control points in mm,
requested tolerance, parameter-matched conversion error bound and segment count.
The endpoint is interpreted under the current absolute/incremental mode; I/J
remain start-relative and P/Q end-relative. A continuous series may derive omitted
I/J from the negative previous P/Q. Interruption clears that dependency. G17,
known XYZ position and valid offsets are required. Conflicting motion codes,
duplicate geometry words, unsupported axes/control words, budget exhaustion and
unknown modal state do not publish a truncated cubic.

Conversion uses dyadic de Casteljau subdivision. Comparing each subcurve with
its degree-elevated endpoint chord gives a conservative bound from the two
internal control differences. Unlike perpendicular flatness, this
parameter-matched criterion retains collinear reversals and closed loops.
A floating-point allowance is included; tolerance below that allowance is refused.
Coordinates are finite and within one million mm, subdivision depth is at most
32, and the configured segment budget applies across the entire program.
Cooperative cancellation is checked during program parsing and spline subdivision.
Original control-hull bounds enclose the curve; they are conservative extents,
not claims about sampled extrema or measured machine clearance.

Operation process details identify the declared dialect and show each cubic's
conversion bound and source line. Feed length uses the polyline approximation.
G93 timing requires explicit per-block F and does not multiply duration by the
number of polyline segments. Error bounds concern geometric parameter-matched
position only; they do not qualify tangents, length accuracy, acceleration,
controller blending or physical machining accuracy.

Requirement 20 remains OPEN: the operator-facing dialect/study selection,
installed spline visualization, quadratic and general rational/NURBS support,
portable conversion review, and actual supported-backend qualification still
need implementation and evidence. Requirement 1 also remains OPEN; cooperative
operation-analysis cancellation is a bounded improvement, not large-job latency
qualification. No controller transport or machine action is introduced.
