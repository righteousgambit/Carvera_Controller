# Facing preview setup binding

Generating a facing preview captures the current numerical inputs, loaded cutter
definition and declared scene setup. The background calculation can open its
result only if those dependencies still match at completion. Switching machine
profiles or changing stock, workholding, component choices or preview work offsets
requires generating again. This also detects different imported stock shapes
with identical outer dimensions, using source content, units and local bounds.
If the operating system cannot start the calculation worker, the panel reports
the error and releases its busy state so the operator can retry.
Unexpected calculation exceptions also produce a failure completion and a
diagnostic traceback. Empty-message exceptions receive a nonempty class-based
error label, preserving retry without staging an incomplete result.
Pass calculation and G-code serialization both run in the background worker.
The UI completion rechecks the captured context and stages the finished text;
it does not serialize the toolpath. Encoding failures use the same recovery path.
The captured program selection, preview request/load generation, analysis
generation and loaded-program hash must also match. A later local/remote choice,
reload or clear supersedes the pending result, even when setup stays unchanged.

Camera/model visibility and framing are presentation choices and do not invalidate
the calculation. Relocating identical imported-stock bytes preserves their source
identity. The check uses local metadata without reading source files, querying the
controller or changing machine state.

This prevents a late calculation from replacing the program preview under a new
setup. It does not certify fixture clearance, source geometry, physical mounting,
measured offsets or the cut. The generated program remains a local preview for
review through the existing workflow.

Regression checks defer the calculation, change stock/vise/machine context, then
complete the old work. Those completions must produce no generated job file, no
preview load and no controller commands. Separate checks retain identity across
view-only changes and relocated identical sources while rejecting changed shapes.
