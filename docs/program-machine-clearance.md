# Program machine-clearance reviews

Open **Machine → Kinematics & machine clearance → Continuous machine-body clearance → Program machine clearance** in the workbench. Load a C1 CAD scene, stock and explicit tool profiles, assign the scene datum to its named work coordinate system, then review the loaded program or the selected operation. Repeat-part setups use their named datums.

The review checks every resolved XYZ segment and retained curve enclosure in the selected source range with the corresponding tool's declared body geometry. Contacts have source-line and path-fraction references, with detached equal-scale XY/XZ projections. Contact choices are paged in groups of 64. Missing curve certificates, unresolved commands and automatic tool-change travel keep separate coverage gaps; contact with initial stock may be intended cutting.

## Save and reopen

**Save review…** creates a `.cvprogramclearance` file containing:

- The exact UTF-8 text passed to the operation parser and its SHA256. This identifies parser input; it does not attest to an original file's encoding or line-ending transformations before parsing.
- Parser dialect, curve tolerances and budgets, timing inputs, and the offsets used to interpret WCS transitions.
- The inclusive source range, review datums, per-tool articulated body declarations, and their original scene references.
- Contact intervals, source fractions, coverage gaps, qualification text and computational counts. Separate digests bind the resolved motion and the complete body declarations.

Saving reparses the source and recomputes the report before atomically publishing the file. A forged result, missing exact parser input, mismatched geometry, changed source settings, cancellation, or exceeded limits prevents publication. A successful save returns the SHA256 of the bytes read back from the destination.

**Open review…** verifies the format and transport digest, reparses the retained source with the retained settings, recomputes the declared-body review, and compares the complete result. Rehashing an edited result cannot bypass recomputation. Invalid or cancelled opening retains the previous result.

Reopening displays a detached review. It does not load a job, replace the active scene or tool library, set machine offsets, or send controller commands. Referenced CAD files need not be present: the recomputation uses retained conservative body declarations, not reopened CAD surfaces. **Inspect source** requires the active program's parser-input hash to match the retained source.

A selected-operation file retains the complete source text so its modal history can be reproduced. Only tools required in that selected range are retained. The displayed range defines coverage; retaining full source text does not qualify execution outside it.

## Bounds and qualification

The format accepts at most 32 MiB, including at most 16 MiB of UTF-8 parser input and 100,000 source lines. An individual source line is limited to 65,536 characters. Archive parsing caps complete-program motion at one million segments, without publishing a partial parse. The selected review remains bounded to 100,000 segments, two million shared clearance intervals, 10,000 possible contact intervals, 32 tool declarations, and 32 bodies per tool. Budget exhaustion refuses the report rather than decimating it. JSON fields are unique; nonfinite values and oversized integer tokens are refused.

The current method is `c1-program-curves-common-link-enclosure-v2`. Older `c1-program-polylines-common-link-enclosure-v1` files still reopen by recomputing their original chord-only method and retain their curve-interior gaps; opening them does not silently upgrade coverage. It uses the nominal C1 X/Z spindle and negative-Y table mapping. Bodies on the same rigid attachment cancel their common motion exactly while their pair remains checked. Each resolved G2/G3 arc/helix, LinuxCNC G5/G5.1 spline, and positive-weight G5.2/G5.3 NURBS closure retains its complete tessellation and original normalized parameter partition. The arc bound uses the second-derivative linear-interpolation bound plus accepted endpoint radius mismatch and floating-point allowance. Spline bounds come from their parameter-matched control-polynomial or rational conversion certificates. The machine review validates the complete certificate against parser-owned motion before applying it. Missing certificates retain gaps; malformed or duplicate certificates refuse the report.

For the nominal C1 linear axes, a tool-tip position error bounds every attached body's translation error. Bodies on different attachments use the sum of their displacement bounds in the separating-axis enclosure; bodies on the same rigid attachment cancel common motion. Interval subdivision terminates on the joint interpolation bound while retaining the curve error as a separate conservative allowance. A contact widened by an enclosure has no exact curve-overlap witness. Same-attachment box overlap remains exact because the shared uncertain motion cancels. Its source fraction is the original normalized curve parameter, not chord-length fraction; the detached projection shows the nominal chord pose. All endpoints expanded by the curve error must remain within every nominal C1 joint limit, or the review is refused. This can conservatively reject a curve near a travel boundary.

The compact result lists bounded curves separately from uncovered curves and keeps backend/physical qualification status visible. Expand **Coverage & limits** for full curve position bounds, computational counts, gap lines and qualification details. The current UI does not claim exact surface contact, dynamic execution, or curve-length/tangent accuracy.

A successful reopen proves consistency of the retained parser input, declared body geometry and current computation. It does not authenticate manufacturer CAD, establish measured registration, model removed stock, cover uncertified curves or unresolved/backend/ATC motion, or qualify installed execution or physical clearance.
