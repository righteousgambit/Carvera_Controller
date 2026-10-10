# Program machine-clearance reviews

Open **Machine → Kinematics & machine clearance → Continuous machine-body clearance → Program machine clearance** in the workbench. Load a C1 CAD scene, stock and explicit tool profiles, assign the scene datum to its named work coordinate system, then review the loaded program or the selected operation. Repeat-part setups use their named datums.

The review checks every resolved XYZ polyline segment in the selected source range with the corresponding tool's declared body geometry. Contacts have source-line and path-fraction references, with detached equal-scale XY/XZ projections. Contact choices are paged in groups of 64. Curves, unresolved commands and automatic tool-change travel keep separate coverage gaps; contact with initial stock may be intended cutting.

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

The method is `c1-program-polylines-common-link-enclosure-v1`. It uses the nominal C1 X/Z spindle and negative-Y table mapping. Bodies on the same rigid attachment cancel their common motion exactly while their pair remains checked. NURBS closure blocks retain curve-interior coverage gaps even after modal motion resets.

A successful reopen proves consistency of the retained parser input, declared body geometry and current computation. It does not authenticate manufacturer CAD, establish measured registration, model removed stock, cover curve interiors or unresolved/backend/ATC motion, or qualify installed execution or physical clearance.
