# Program machine-clearance reviews

Open **Machine → Kinematics & machine clearance → Continuous machine-body clearance → Program machine clearance** in the workbench. Load a C1 CAD scene, stock and explicit tool profiles, assign the scene datum to its named work coordinate system, then review the loaded program or the selected operation. Repeat-part setups use their named datums.

The review checks every resolved XYZ segment and retained curve enclosure in the selected source range with the corresponding tool's declared body geometry. Contacts have source-line and path-fraction references, with detached equal-scale XY/XZ projections. Contact choices are paged in groups of 64. Missing curve certificates, unresolved commands and automatic tool-change travel keep separate coverage gaps; contact with initial stock may be intended cutting.

## Save and reopen

**Save body review…** creates a `.cvprogramclearance` file containing:

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

The compact result lists bounded curves separately from uncovered curves and keeps backend/physical qualification status visible. Expand **Coverage & limits** for full curve position bounds, computational counts, gap lines and qualification details. The body-envelope review does not claim exact surface contact, dynamic execution, or curve-length/tangent accuracy.

A successful reopen proves consistency of the retained parser input, declared body geometry and current computation. It does not authenticate manufacturer CAD, establish measured registration, model removed stock, cover uncertified curves or unresolved/backend/ATC motion, or qualify installed execution or physical clearance.

## Continuous CAD surface refinement

Expand **CAD surfaces & solids** to review the entire loaded program or only its selected operation against every triangle of the captured C1 machine, ATC, fixture, workholding and initial stock geometry. Selected component overrides, movable-jaw placement and stock tilt/rotation share the viewer registration. Imported repeat stocks retain their actual surfaces and source identities. Hidden CAD remains included. Cutter, shank and holder pairs retain their conservative rotating envelopes; a static flute mesh does not prove spinning-tool clearance.

The worker first performs the existing curve-aware body review, then refines each candidate pair over the **complete original chord**, including time beyond the first conservative box interval. A triangle BVH removes provably disjoint pairs; exact rational separating-axis projection intervals cover continuous translation, including coplanar and between-endpoint contacts. There is no time sampling or face decimation. Curve error enters as a conservative relative position allowance; a 0.000001 mm outward numerical allowance covers floating-point placement before the rational tests. Triangle contacts widened by these allowances are possible contacts, with no exact curve-surface witness.

Results retain original component triangle IDs and source-parameter intervals. Select a contact for equal-scale XY/XZ projections of the two triangles at the nominal chord pose at the interval midpoint. Select a remaining gap to see why that body pair remains unresolved. Source inspection requires a matching active parser-input hash. Results are paged in groups of 64; changes to source, parsing, range, datums, tools or scene withhold stale worker completion. Cancellation and budget exhaustion publish no partial result and restore the shared controls.

After continuous possible surface contacts are retained, the worker classifies the intervals between them for **closed-solid containment or separation**. Geometric admission requires a complete manifold mesh, nondegenerate faces, no proper self-intersections, positive enclosed material volume and consistent alternating cavity winding. Either global winding direction is accepted; disconnected solids and true cavities are supported. There is no automatic vertex welding, face repair, Boolean union or invented file provenance. An unavailable solid retains an explicit pair gap.

Boundary shells are checked against the other admitted solid in both directions at an exact rational interior parameter until containment is found; separation requires checking every shell. With no boundary crossing anywhere in that interval, occupancy cannot change. This uses the complete continuous surface-contact partition, rather than sampled times. Contact boundaries remain closed possible contacts; neighboring occupancy endpoints remain open. Conservative curve and numerical allowances remain included in the surface contacts. A body inside a declared cavity can be separated even when its bounding box overlaps the enclosing object's box.

Select a solid interval to inspect its original source-parameter range and classification. Containment includes the original shell face and its nominal chord witness in world coordinates; this is not a measured physical contact point. Separation applies only to the admitted pair and interval. Source inspection, paging, stale-result rejection and cancellation work the same way as the surface contacts. Rotating tool assembly envelopes, original unresolved-command/curve/ATC gaps, removed-stock state, measured registration, backend execution and physical clearance remain separate open gates. **Save surface review… and Open surface review… retain prepared triangles, exact rational contacts, solid intervals/witnesses and gaps in a `.cvsurfacereview` file. Opening reparses the exact program text and recomputes the body, surface and solid results. Save body review… and Open review… continue to exchange the separate envelope report.**

Preparation is bounded to 250,000 complete unique triangles across the required tool scenes (200,000 per individual mesh). Validated common machine/workholding/stock meshes are shared between tools; each tool keeps its own spindle registration and rotating envelopes. Narrow-phase queries share limits of two million BVH node pairs and 100,000 triangle pairs across the complete selected range. Individual-contact mode additionally retains its original 10,000 triangle-contact limit; grouped mode uses the separate representation bounds below. Exceeding a limit refuses the whole report. CAD and imported repeat-stock source bytes are checked before preparation and after computation.

Solid admission builds a cancellable surface-area partition of complete face bounds. Floating-point costs choose only the tree layout; every original face remains in exactly one leaf. Exact integer plane, noncoplanar plane-cut interval and coplanar-edge certificates reject only pairs proved separated or confined to their original shared boundary. Plane-cut endpoints retain numerator/positive-denominator pairs; cross multiplication proves strict interval separation without division, normalization or tolerance. Exact endpoint contacts and overlapping cuts retain the original full predicate. Binary64 positions embed into a common integer grid without rounding. Inconclusive pairs retain the original full rational intersection test. Solid-review leaves hold at most 16 faces, trading bounded cheap box comparisons for fewer tree visits. Every overlapping face candidate is still charged. The existing stock-voxel admission keeps its eight-face leaves, original traversal and pair accounting.

Solid admission and classification share a separate whole-review budget: two million validation steps (tree traversal and exact integer certificates), 250,000 inconclusive pairs requiring full rational intersection, eight million ray/face tests and 100,000 point queries. Mesh admission is cached only within that operation. A cancelled or exhausted operation publishes no partial report; invalid geometry retains a specific gap rather than silently passing.

The standalone C1 CAD converter preserves full binary64 position coordinates. Only display normals are rounded. Zero-area source facets remain explicit, and a missing face triangulation refuses conversion. Conversion records tessellation settings and zero-area counts; neither the metadata nor regenerated geometry establishes measured registration. Existing converted assets require separate regeneration and geometric admission.

Conversion keeps each original STEP solid as a separate component, preserving its assembly and motion group. Source-local native face IDs, solid index/count and complete face-occurrence coverage accompany each mesh. This splits a native multi-solid bed compound without guessing mesh shells or merging touching edges. A source surface without native solids remains labelled as a surface. If solid extraction would omit an orphan source face, conversion refuses the component. These declarations require downstream geometric admission and do not establish measured registration.


Portable surface reviews retain the complete prepared mesh pool with shared
references across tools, source text/parser settings, selected range, work datums,
body declarations and declared scene identities. Every pool entry must be used;
each reference must identify a declared body, and all prepared points must fit
its zero-joint envelope with the existing 0.000001 mm numerical allowance. Mesh
indices are rebuilt from all retained faces. Geometry and result hashes bind the
prepared declarations; they are not signatures or independent proof of original
CAD provenance, measured registration or physical clearance. A review opens
without its original CAD files or current tool library, preserving active setup.
Source navigation requires the matching loaded program.

Exchange is bounded to 64 MiB, 250,000 unique complete triangles across at most
4,096 meshes, 32 program tools and the existing whole-review solver limits. Exact
rational intervals/witnesses use numerator and denominator strings, preserving
endpoint closure and original source parameters without decimal rounding.
Saving also reparses and recomputes before atomic publication and readback.
Malformed, inconsistent, cancelled or exhausted exchange retains the prior file
and review. JSON duplicate fields, nonfinite coordinates, unknown methods,
ambiguous numeric references and unused declarations refuse loading. Restoring a
review never runs a program, changes machine datums or replaces active geometry.


Surface contact indices use a bounded twelve-bin surface-area partition with
at most two complete faces per leaf and a balanced fallback for coincident
centers or deep branches. Tree costs choose grouping only; exact rational box
intervals still prove culling. Every surviving leaf pair consumes the original
shared triangle-pair budget, including pairs rejected by the exact predicate.
All original face IDs, duplicate faces and degenerate triangles are retained.
The exact triangle predicate checks coordinate axes first and lazily constructs
face, edge-cross and coplanar axes until separation is proved. It intersects the
same complete closed-interval family, without rounded coordinates or changed
error allowances.

Portable exchange selects the index through its versioned review method. New
reviews use the surface-area method; previously saved v1 reviews rebuild the
original eight-face median tree and reproduce their original numerical work
counters under the same global limits. Resaving an opened v1 review preserves
that method. Mixed index methods refuse saving rather than claiming ambiguous
accounting. Rehashing a method or numerical counter does not bypass complete
recomputation.


When a surface or solid work budget is exhausted, program review reports the
source line, active tool, body pair and surface/solid work counters. Worker
controls recover and no partial report is published. The identified pair is
nominal declared geometry; the message does not establish a physical collision
or automatically permit mounting contact.


## Exact interval contact groups

The workbench defaults to **Exact interval groups**. Within each original body
pair and program segment, only contacts with identical exact rational lower
and upper parameters share a group. Overlapping, adjacent or merely close
intervals remain separate. Every contributing original triangle-ID pair is
retained in canonical order. This changes the representation, not the complete
triangle traversal or predicates. It neither permits mounting contact nor
excludes fixture/bed pairs.

Grouped mode shares the existing two-million-node and 100,000-triangle-pair
whole-review work bounds. Its separate representation contract is at most
10,000 exact groups and 100,000 total original member pairs across the complete
selected range. **Individual triangle contacts** remains available and retains
the original 10,000 per-contact bound and work accounting. Cancellation or any
work/representation limit refuses the complete report; no partial groups are
published. Continuous solid classification uses the same complete contact
partition and retains original containment/separation witnesses and gaps.

Select a group and expand **Original triangle pairs in this group** to page
through every member in batches of 64. Each member shows its original two
faces in equal-scale XY/XZ projections at the nominal chord midpoint. Source
navigation requires the matching active parser input. Changing representation
invalidates the prior result; busy controls, cancellation and stale-result
checks use the existing review worker.

Grouped portable reviews declare
`c1-exact-interval-groups-continuous-surfaces-solids-v3`. Saving and reopening
reparse the retained source, rebuild every mesh index, recompute all groups,
member IDs, exact intervals, solid results and counters, and compare the complete
evidence. Rehashing edited membership cannot bypass this check. Existing v1/v2
individual-contact reviews retain their original methods and accounting when
opened and resaved. Detached opening preserves the active program, geometry,
toolset, datums and controller state. The existing 64 MiB complete exchange
limit remains unchanged.
