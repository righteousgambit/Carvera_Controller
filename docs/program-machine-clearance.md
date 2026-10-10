# Program machine-clearance reviews

## Before / after material sections

Ordered stock-history rows include **Before / after material**. Select a
retained stock move, choose its stock-local XY, XZ or YZ plane and a zero-based
cell layer (blank selects the middle layer), then **Reconstruct section**.
Previous/next stock-move actions follow the same stock instance through the
resolved program, including moves made while another named datum is active.

The worker replays the complete preceding material history and the selected
move under one shared cell-work budget. It checks the reconstructed steps
against the retained report; the final move also checks complete final cells.
The detached before/after state is cached for one reviewed move, including all
stock instances. **Previous layer** and **Next layer**, or changes of plane,
reuse it without replaying preceding cuts; **View section** replaces the
reconstruction action when that state is available. Changing to another move
or review releases it. The side-by-side views use the same scale and full grid bounds. Green cells
remain, amber cells were removed by this move, and dark areas were empty. A
cavity or an earlier cut is never labelled as new removal. Exact cell-run
merging preserves holes; a section exceeding 8,192 rectangles is refused
instead of being truncated. Cancellation or a failed replacement preserves
the last complete section for unchanged options. Changed selections/options
clear the old section, and stale worker delivery is withheld.

These are sections through the declared stock's own grid, before its rotation,
tilt and WCS placement. They show center-classified simulation cells, not a
measured physical boundary or clearance proof. Opening a portable surface
review supports the same reconstruction while preserving current setup,
program, tool profiles and controller state.

## Compare a finishing continuation

Under **Before / after material**, expand **Compare finishing continuation**.
Choose a tool retained in this review and an ending source line (blank uses the
review end), then **Compare following moves**. The comparison starts immediately
after the selected resolved move; further chords on the same source line are
included. It reuses the captured after-stock, or reconstructs it in the worker.

Both variants follow the same intended tip path and fixed axes. One keeps each
planned tool assignment, while the other substitutes the selected reviewed tool
for all following resolved moves in the range. The result gives estimated removed
and remaining volumes, plus complete-grid differences: extra removal and extra
stock relative to the planned continuation. The planned result is a baseline,
not a nominal finished-part target or a gouge/allowance certificate.

Rapid cutter and non-cutting shank/holder contacts are checked against the material
present before each move. All contact estimates are retained, paged 64 at a time,
and linked to source lines with the original parser-input hash guard. Uncertified
curve chords retain material. Both variants share a 50-million cell-work budget
and a 100,000-contact limit; cancellation or refusal publishes no partial result.
The previous complete comparison survives failed replacements with unchanged
options. Changing review, stock move, tool or range clears it and withholds stale
worker delivery. Source, setup, tools and controller state are preserved.

These are center-classified stock estimates. Changed tool-length joint poses,
machine/fixture collisions, cutting forces, ATC travel and physical execution are
not recomputed by this comparison. Use the separate CAD/body clearance workflow
for its own declared coverage. **Comparison scope & limits** explains these
bounds without occupying the main result area.

## Compare an explicit part target

Expand **Compare actual part target** under the retained stock sections. Use
**Choose part STL…**, explicitly select **mm** or **inch**, and enter translation
X, Y, Z in millimetres. The STL coordinates plus this translation must be in the
selected stock's grid frame, before its rotation/tilt and WCS placement. There is
no automatic centering, clipping, inferred unit or alignment. The complete target
bounds must fit the declared grid. STL topology, proper intersections, closed
shells and cavity winding are validated before accepting material occupancy.

**Load & compare target** classifies the complete target on exactly the retained
stock grid: bounds, cell sizes, pivot and orientation remain identical. The result
compares the initially declared stock and stock after the selected move. If a
finishing comparison is retained, it also compares planned and substituted-tool
continuations. Each state reports excess material outside the target, missing
material inside the target, and newly missing volume relative to initially
insufficient stock. Missing target centers indicate potential overcut or
insufficient stock; they do not establish a measured gouge. A sampled target
volume can differ from the exact declared solid volume at the chosen resolution.

Select **Display stock state**, choose section plane/layer above, and **View target
section**. Green marks target cells, amber shows excess stock and red shows
missing target cells. Complete equal-run rectangles preserve cavities and
separate islands; exhausted section bounds withhold the entire new image. Plane,
layer or displayed-state changes clear the image without clearing numeric fits.

**Compare target** reuses the detached, hash-identified target. **Reload target
bytes** explicitly rereads and validates the source file. Editing file, units or
placement releases the target; changing stock instance/review releases it too.
Moving within the same stock preserves its target but clears the fit. Changed
finishing inputs/results invalidate associated fits. Worker generations reject
stale deliveries, including a selection changed away and then restored. Cancel
or refusal retains a complete previous result for unchanged inputs.

Target meshes retain the existing 24 MiB/100,000-face limits. Geometric admission
has bounded intersection/traversal work; aligned rasterization allows two million
complete cells, eight million ray tests and sixteen million node visits. A fit
shares eight million cell-work units across all two/four stock states. The target
identity and scope details are collapsible. Normal-distance allowance, cutter
reach, forces, machine/fixture/ATC clearance, measurement and physical registration
remain separate gates; this workflow sends no commands or setup changes.

## Ordered remaining-material review

In **CAD surfaces & solids**, choose **Initial CAD + ordered stock**, set the
stock resolution, and review the program from line 1. This adds a separate,
source-linked material history to the exact initial-CAD result. Every resolved
move is checked against the cells present before that move removes material.
Rapid cutters and non-cutting shank/holder envelopes retain estimated contacts;
ordinary cutting contact is permitted for material subtraction only in this
estimate. Initial CAD contacts remain visible and retain their original meaning.

Each paged history entry gives the source line/tool, stock instance, volume
before the move, estimated removal, remaining volume and contact candidates.
Contact inspection shows an occupied-cell envelope and estimated tool-tip entry
in that stock's work frame. **Inspect source** requires matching parser-input
bytes. All repeat stock instances evolve in order using their own declared
datums, including during moves programmed in another instance's WCS.

Ordered review requires preceding source history: a selected operation starting
after line 1 is refused. Nonzero curve-enclosure error or missing curve bounds
holds material for those chords; unresolved blocks and ATC travel remain visible
coverage gaps. Removal classifies voxel centers; an emptied cell does not prove
that its entire volume or the physical part is clear. Rotated cells use enclosing
axis-aligned contact boxes, and manufactured flute/thread geometry remains
unqualified. CAD clearance, estimated stock and physical clearance are distinct.

New v10/v11 `.cvsurfacereview` methods retain complete initial occupancy, stock
placement, cutting/assembly dimensions, every history step and final compressed
occupancy. Saving and opening reparse the source and recompute both the original
CAD report and all ordered material steps. Rehashed changes to tool/stock
bindings, contacts, volumes or final cells cannot reuse old evidence. Historical
v1–v9 methods retain their original semantics. Opening a file preserves the
active scene, datums, tool library and controller state.

Shared limits are two million stock cells, 50 million conservative cell/section
work units, 100,000 move/instance steps, 100,000 contact estimates, and the existing
64 MiB archive limit. Work accounting charges complete grid sizes even when a
query visits fewer cells. Cancellation or exhausted work refuses the entire new
ordered result; retained input cells are never modified. The existing workbench
worker owns calculation/exchange, disables inputs while running and checks scene
and source identities before accepting a result.

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
one complete face per leaf and a balanced fallback for coincident
centers or deep branches. Tree costs choose grouping only; exact rational box
intervals still prove culling. Every surviving leaf pair consumes the original
shared triangle-pair budget, including pairs rejected by the exact predicate.
All original face IDs, duplicate faces and degenerate triangles are retained.
The exact triangle predicate checks coordinate axes first and lazily constructs
face, edge-cross and coplanar axes until separation is proved. It intersects the
same complete closed-interval family, without rounded coordinates or changed
error allowances.

Portable exchange selects the index through its versioned review method. Current reviews use the directional method below; previously saved v1 reviews rebuild the
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

Grouped portable reviews with the retained two-face index declare
`c1-exact-interval-groups-continuous-surfaces-solids-v3`; current directional
reviews use the v5 method described below. Saving and reopening
reparse the retained source, rebuild every mesh index, recompute all groups,
member IDs, exact intervals, solid results and counters, and compare the complete
evidence. Rehashing edited membership cannot bypass this check. Existing v1/v2
individual-contact reviews retain their original methods and accounting when
opened and resaved. Detached opening preserves the active program, geometry,
toolset, datums and controller state. The existing 64 MiB complete exchange
limit remains unchanged.


## Exact directional surface index

Current preparation uses `surface-directions-v3`: the bounded surface-area
partition retains every original triangle in a single-face leaf. Each node
also retains exact lower/upper projections of all of its points along eighteen
fixed integer directions: X±Y, X±Z, Y±Z and both 2:1 variants in each
coordinate plane. Leaf projections use exact dyadic
input coordinates; parent bounds are exact unions of their complete children.
There is no rounded normal, approximate hull, face omission or error reduction.

Queries intersect the original three coordinate-axis slab intervals with those
eighteen directional intervals over the complete motion chord. Each direction's
exact L1 norm of two or three scales the same original position allowance. An
empty interval proves all
original face pairs inside those nodes separated. A surviving interval is only
a candidate; every leaf pair is still charged to the unchanged triangle-pair
work budget before the original full triangle predicate runs. Each node pair
remains charged to the unchanged whole-review node budget. Projection
preparation and traversal retain cancellation and complete-report refusal.

The original coordinate slabs use direct exact endpoint arithmetic instead of
general dot products. Independent tests compare those intervals with the
original generic rational implementation. Work counting and endpoint closure
remain identical for retained legacy indices.

Individual directional reviews declare
`c1-direction-bounds-continuous-surfaces-solids-v4`; grouped directional reviews
declare `c1-direction-bound-groups-continuous-surfaces-solids-v5`. Opening a
v1, v2 or v3 file reconstructs its original median/two-face index and accounting;
resaving preserves its method. Production-writer v2/v3 fixtures retain their
original contacts/groups, solid evidence and counters and resave byte-for-byte.
Mixed index methods refuse ambiguous exchange. The workbench coverage card
shows the retained index method. All geometry, solver, representation and
portable-size limits remain unchanged.


Static triangle pairs use the original complete coordinate, face-normal,
edge-cross and coplanar-axis family on one exact integer grid. All validated
binary64 positions, shifts and padding embed without rounding. Each axis's
polynomial scale multiplies both sides of its inequality by the same positive
factor, retaining the original L1 error allowance and closed contact. Moving
triangles retain the rational interval predicate. Original per-pair/node work
counting and legacy evidence remain unchanged. Tighter node bounds may reject
proved-empty space inside former conservative boxes, including degenerate
line/point boxes; source faces remain complete and unavailable solids keep gaps.

## Declared rotating cutter, shank and holder sections

Current scene reviews also retain the cutter, shank and holder axial sections
derived from the loaded millimeter tool definition. Each section is a filled
rotating +Z cylinder. The cutting section retains the outside-diameter envelope;
ball, bull, taper, drill and thread details are not treated as exact manufactured
surfaces. Existing registered CAD bands retain their source-byte identities and
declared heights/radii. Missing holder declarations remain unknown. The C1 tool
base translation is included in cylinder/mesh registration; tilted or rotated
tool bases refuse this method rather than receiving a false +Z result.

For a complete obstacle triangle, the unknowns are its two barycentric
coordinates and move parameter. Seven exact linear inequalities define the
closed barycentric/time/axial-overlap prism. Intersections of its constraint
planes give all feasible vertices. Projecting those vertices into the relative
XY plane and finding the convex hull's nearest point gives the global minimum
squared radial distance. Its comparison with the declared squared radius is
exact. This covers the complete chord, including interior crossings and
tangencies, without time or spindle-angle sampling, polygonal circles or
approximate optimization. Continuous cylinder/node-box tests reject complete
empty bounds before leaf queries. Parallel cylinder pairs restrict time by
axial overlap, then minimize exact squared center distance over that interval.

The existing outward position/curve allowance expands the declared cylinder
axially by the allowance and radially by twice it. The latter contains both an
XY error cube and an error ball. These are nominal input/curve enclosures;
they do not establish physical registration or bound all CAD model errors.

Each section reports possible contact with an exact rational existence witness,
contained material, separated material, or unavailable solid geometry. A witness
can lie inside the filled rotational envelope; it is not a tool-boundary point,
first-contact time, entry/exit interval or exhaustive obstacle-face list. A
positive witness closes that section's existence query. A no-contact query
visits every relevant retained face, then admits the complete closed obstacle
solid before classifying the center witness. With no boundary entering the
connected cylinder anywhere on the move, its material occupancy cannot change.
Open/nonmanifold solids keep an unavailable result. No cutting or mounting
contact is automatically permitted or excluded.

Triangle and rotating queries share the original 2M node, 100K primitive-pair
and 10K individual-contact limits, and the original solid-admission budget.
Every section is reviewed; any exhausted bound refuses the whole operation.
The retained `triangle_pairs` counter key now counts both primitive kinds for
rotating methods. The workbench labels it as primitive pair checks. Triangle
contact groups retain their separate complete interval/membership accounting.

Raw rotating reviews declare
`c1-continuous-declared-rotating-surfaces-solids-v6`; grouped rotating reviews
declare `c1-declared-rotating-exact-groups-surfaces-solids-v7`. Prepared triangle
geometry and complete tool/body/section declarations share one geometry digest.
Readers validate every section against its retained body/frame, reparse source,
rebuild surfaces and recompute every rotating result. Rehashed declarations or
witnesses cannot reuse old evidence. v1 through v5 retain their original methods
without retroactively adding rotating queries.

The workbench lists section states beside triangle contacts, solid intervals
and gaps. It shows source-bound axial dimensions, the original obstacle face,
nominal world witness and its source parameter. XY/XZ views mark that witness;
source navigation and detached save/reopen preserve the current machine,
profiles and datums. Current initial-stock geometry is retained throughout the
move: dynamic removed-stock coupling, exact manufactured flutes, missing
assemblies, advanced-machine axes, measured registration, installed/backend
execution and physical qualification remain independent open requirements.

## Shaped rotating cutter profiles

Detailed surface review now uses the loaded ball, drill, chamfer, engraving and
supported tapered tool's nominal axial cutting profile. Ball tips and rounded
supported tapered tips use spherical caps; increasing tapered portions use cones,
and the upper cutting body retains its cylinder. The complete original C1
registration, source chord and position/curve allowance apply to every piece.

Each spherical/conical query minimizes its exact rational quadratic over the
complete closed axial/barycentric/time polytope. Every independent active face,
edge and vertex is considered; singular stationary faces have a flat direction
reaching a lower face. This includes contacts in triangle interiors and between
clear motion endpoints. It does not use temporal steps, circle tessellation or a
floating-point optimizer. Sphere allowances enclose the position-error cube;
cone allowances extend the axial/radial profile with a capped upper piece.
Whole-node rejection remains the containing cylinder certificate. Original node,
primitive-pair, contact, section and solid-admission limits remain shared.

The workbench identifies the primitive beside its section outcome and shows
sphere center/radius or cone endpoint radii. A witness establishes possible
intersection with the declared padded profile, not first contact or a
manufactured flute boundary. Assembly-to-assembly queries still use enclosing
cylinders and state that limitation on shaped results. Bull corners and thread
teeth retain the outside-radius envelope; arbitrary CAD cutting flutes remain
unresolved. Current stock is initial material, not a record of prior removal.

Shaped raw/grouped reviews use separate v8/v9 methods and retain all primitive
parameters in their complete geometry digest. Opening recomputes the same
profile-aware report. Older v1–v7 reviews retain their original method, work
accounting and qualification; published v6/v7 production-writer fixtures replay
and resave byte-for-byte. Rehashing a primitive, parameter, method, source or
witness does not bypass recomputation. These are nominal declared profiles;
manufacturer identity, measured registration, changing-stock coupling and
installed/backend/physical qualification remain separate gates.

The separate evolving-stock simulation uses the same finite ball cutting reach:
its lower hemisphere and upper cutting cylinder share the motion parameter.
This prevents subtracting cells above flute length at a different time in a
diagonal move. That simulation updates occupied cells between segments. Detailed
C1 surface review still checks retained initial stock surfaces; coupling its
report to that evolving occupancy remains open.

## Selected-cell surface allowance and local approach

The part-target section can pick a complete stock-grid cell in XY, XZ or YZ.
The workbench also accepts explicit zero-based X/Y/Z indices and an optional
reviewed tool. The detached target retains its validated source triangles and
hash; editing the source file does not change the retained result until reload.

A best-first triangle hierarchy computes the exact rational closest point to the
cell center. Each leaf minimizes over the triangle interior and all closed
edges, with deterministic source-face ties. Exact squared distance, barycentric
coordinates and face/edge/vertex identity are retained. Display distance is
signed using the retained target-center classification. Its plus/minus cell half
diagonal gives a signed distance interval, which expresses grid uncertainty; it
is not a measurement, whole-cell removal proof or a global maximum allowance.
Complete nearest queries share bounded node/triangle counters and cancellation.

An optional straight insertion starts above the entire declared stock's program-
space Z bound and ends at the selected cell center, with the tool axis fixed +Z.
Every retained target face uses the declared translation and stock rotation/tilt
before continuous shaped cutter and declared shank/holder contact queries. All
surface contacts are retained, with complete 64-entry workbench pages. Contact
witness time is an existence witness, not first contact. Remaining-stock shank/
holder contact uses that state's complete center-grid mask and conservative cell
boxes; declared cutting engagement with excess stock is allowed there. Target
contacts include cutter engagement, so zero or nonzero totals are not a global
safe/reachable classification. Undeclared holders stay explicitly unresolved.

This is a candidate local approach to a cell, not a generated finishing path or
machine/fixture/ATC/changed-tool-length/force/physical review. The original C1
scene clearance gates remain separate. All work runs through the existing
cancellable worker; altered targets, stock states and changed-away-and-restored
cell choices withhold stale delivery. A cancelled/refused replacement retains a
previous result only when its inputs remain unchanged. No profile, program,
offset, tool table or controller command is changed by inspection.

## Whole retained-grid allowance extrema

The separate whole-stock summary scans the complete excess/missing masks for all
retained states on their original grid. It queries each eligible center once
against all retained source triangles and shares the resulting witness across
states. Exact squared distances determine largest excess and deepest missing
material; display square roots never determine ordering. Equal-distance cells
retain the earliest row-major index, and equal-distance faces retain their
original source index. Counts, extrema, geometry/stock/program identity and cell
half-diagonal signed-distance intervals remain attached to an immutable result.
No category is assigned a peak when it has no centers.

Complete traversal supports2M-cell grids with8M shared state-cell work. Nearest
queries share50M nodes and50M triangle minima across the operation; individual
cell inspection retains its original smaller bounds. There is no partial,
decimated, sampled or display-derived fallback on cancellation or work exhaustion.
This is an exact center-query result on the declared finite coordinates, plus a
cell-size uncertainty interval, not the exact continuous stock surface maximum,
measured allowance, reachable toolpath or physical clearance certificate.

## Full declared machine review of a selected-cell insertion

After inspecting a reviewed cutter at a target-grid cell, **Review machine** runs
one detached straight +Z insertion through the complete retained C1 scene. It
uses that tool's captured spindle placement and stickout, the selected stock's
WCS datum and the C1 negative-Y table mapping. The candidate must respect joint
limits. All retained machine, fixture, vise, ATC and other-stock declarations and
explicit pair exclusions remain; fixed assembly pairs are reviewed too.

Only the selected initial-stock box and mesh are replaced by the cell inspector's
complete transformed target-face contacts and its selected remaining-stock
noncutting center-grid estimate. That replacement is named explicitly in the
result. The CAD review uses the complete chord and original prepared triangles,
closed-solid admission/occupancy and shaped rotating sections. Missing surfaces,
invalid solids and undeclared holders remain explicit coverage gaps. Cancellation
and shared work exhaustion withhold an incomplete result.

The workbench retains every contact group, solid interval, rotating result and
gap, with 64-entry pages and original triangle-pair selection. Equal-scale XY/XZ
witness projections use the existing geometry inspector. The proposal digest
binds the parent program/declaration, target bytes and placement, selected move,
state masks, cell, tool and machine-tip endpoints. Changing those inputs clears
invalid evidence; stale worker delivery is withheld. Unchanged-input refusal or
cancellation preserves the prior completed result.

This reviews the declared candidate insertion only. It does not review motion
from the actual current machine pose to the start, execute a tool exchange,
reconcile measured controller tool offsets, generate executable G-code, prove
continuous physical stock removal, or qualify physical machine clearance.

## Complete retract, traverse and insertion

Choose **Full approach route** to enter a declared machine XYZ start, use the
retained source move end, or explicitly **Capture Idle pose**. The captured
existing status packet must be fresh, connected and Idle, with the selected tool,
reported length offset, unrotated WCS and zero rotary axis. It is retained as
reported-coordinate evidence; no query or motion is sent by capture. Delivery
rechecks the connection generation and current fresh packet's coordinates,
tool/length and frame/state, while accepting newer stationary packets.

The candidate retracts to the higher of the start height and the existing local
approach plane, traverses to the selected cell XY, then inserts to its center.
Every waypoint must lie within the declared C1 joint limits. A named approach
plane is not certified clear; all three complete chords are checked against
the retained machine, fixture, vise, ATC and other-stock scene. Target faces and
selected-state stock are checked for every leg. Rapid legs include cutter/stock
contact; insertion permits cutter engagement in stock but retains target and
noncutting results. The declared tool is used throughout; automatic tool exchange,
controller compensation ownership and physical tool registration remain separate.

Exact identical zero-relative-motion pairs can share immutable geometry data
within this three-segment operation. Their key binds the ordered pair, tool,
relative translation and numerical allowance. Every segment has complete source
wrappers and rebased parameters, including contact groups, solids, rotating
outcomes and gaps. Relative-moving queries are not shared. The existing work
limits count unique computations and unique stored group members. This can
reduce repeated fixed-assembly work without dropping any leg's results. Legacy
portable archive methods reject reports that reused pairs; a route-specific
context/export/replay contract remains open. Default legacy refinement is unchanged.

The worker constructs complete result pages off the UI thread; retained target
triangles supply program-frame witnesses without rebuilding a stock grid during
selection. Cancellation and input changes withhold incomplete/stale delivery.
This source workflow is not executable G-code, an effective-compensation
reconciliation, an installed/native acceptance result or physical clearance proof.

## Portable complete approach route

Use **Save route** after a complete route review, or **Open route** to inspect
saved detached evidence. `.cvapproachreview` is a separate versioned method from
the legacy program surface archive. It retains exact source/settings and original
body declarations, complete prepared geometry, stock input/history, selected
move/state/cell/tool, continuation settings, clearance, explicit start provenance
and embedded target STL bytes with source units/translation. The original target
path is a historical label; reopening parses the embedded bytes in a private
temporary file using the existing STL validator. No incoming path is executed or
used as a file destination.

Saving and opening both reparse source, replay stock, reconstruct the selected
move/continuation, validate and voxelize the closed target on the same grid,
recompute every target-state mask and cell inspection, then independently review
all three complete machine/material chords. The recomputed exact record must
match every saved claim. Group members are stored once with all per-leg wrappers;
counts distinguish unique computation/storage from logical memberships. Rational
intervals and original triangle indices remain exact. Rehashed changes to saved
context or evidence do not bypass recomputation.

Files are bounded64 MiB, embedded targets24 MiB, and all existing complete mesh,
stock and solver-work limits remain. Unsupported schemas/methods, duplicate JSON
fields, oversized integers, nonfinite numbers, inconsistent histories or complete
work exhaustion refuse the whole file. Save validates before atomic publication
and verifies readback. Cancellation or stale input before publication retains the
old destination. Original source paths and prepared scene identities do not
independently prove original CAD provenance or physical registration.

Actual worker phases, elapsed time and cancellation remain visible. Open preserves
live position, the current loaded program, profiles/datums/tools and current
target/parent evidence. Captured status in a saved file is historical; it is never
promoted to a fresh machine pose. A new live-start review requires explicit fresh
capture. This workflow preserves declared geometry evidence and generates no
executable G-code or controller command.


Final source verification passes **694 unit / 118 rendered cases**,150 strict
machine files,294 package baseline files,7 checked UI bodies,884 formatted
files and both architecture contracts. The completed route summary remains
visible during exchange progress; final360/800 px rendered cards were inspected.
The nominal full hybrid C1 save and independent public reopen recompute identical
complete evidence for17 bodies/15 meshes/123,582 triangles and95 refined pairs.
The archive is 35,387,384 bytes, SHA256
`393c234b978a86768bc81df30ceb58990f0bfb57696788f6091e5332457a184e`. Its8 shared group pools retain77,362 unique
triangle-pair members and24 per-leg wrappers representing
232,086 logical memberships;57 solid intervals and14 rotating
outcomes remain complete, with no geometry gaps. All33 bound algorithm inputs
remain unchanged across that calculation. Producer/consumer completion is
recorded separately; this synthetic declared setup does not prove current
physical registration, machine execution or installed workflow acceptance.
