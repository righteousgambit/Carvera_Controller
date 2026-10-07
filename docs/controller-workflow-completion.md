# Workflow completion and advanced-machine requirements

The latest 25 recommendations extend the existing requirements ledgers. They do
not replace earlier requirements or treat existing partial foundations as complete.
The implementation goal remains active. Each workflow needs source validation,
installed interaction evidence and, where applicable, actual backend and physical
qualification. A machine profile declaration does not establish installed hardware.

| # | Requirement | Required completion evidence |
|---|---|---|
| 1 | Responsive background work | Large CAD/program/config workflows preserve controls and fresh state; bounded progress/cancel and measured native latency |
| 2 | Selection-driven workbench | Vise/cutter/path selection opens linked editing, measurements and operations while preserving the left views |
| 3 | Coordinated timeline | Operation/change/ramp/reload/probe/inspection selection aligns pose, source, telemetry and recorded camera with timing gaps visible |
| 4 | Desktop data grids | Tool/offset/measurement/magazine sorting, resizing, keyboard/bulk/paste/virtualization at small and large scales |
| 5 | Geometry-linked draft editing | Stickout/jaws/WCS inputs highlight precise geometry with previous/proposed states and reviewed application |
| 6 | Shared job search | Entity/operation/frame/measurement/alarm search navigates exact related context |
| 7 | Actionable setup readiness | Specific missing/stale/mismatched inputs open exact editors or evidence without closing unrelated checks |
| 8 | Persistent purposeful layout | Resizable/collapsible/pinned setup/run/inspection arrangements preserve visible proportioned model and camera panes |
| 9 | Visual change review | Old/new setup/tool/offset/program geometry and affected operations/simulation results are linked |
| 10 | Offline reconciliation | Disconnected complete preparation reconciles actual machine/magazine/offsets/capabilities on connection |
| 11 | Executable two-bank workflow | Appropriate stop, reload, physical/logical identity reconciliation, measurement, offset validation and qualified reviewed re-entry |
| 12 | Tool/pocket/spindle identity | Logical tools, physical assemblies, pockets and transfer/spindle positions with actual fixed/random changer semantics |
| 13 | Geometry-driven probing | Selected features produce supported approach/travel/expected-result previews and captured feature/frame-bound actual results |
| 14 | Inspect/correct/finish | Nominal/tolerance/results, explicit radial/diametral bounded correction, supported finish and reinspection |
| 15 | Complete moving-assembly collision | Swept cutter/neck/holder/spindle/machine/workholding/rotary checks identify first pose and contacting surfaces with qualified geometry |
| 16 | Remaining-stock decisions | Residual allowance/reach/candidate tools and finishing comparison at explicit simulation resolution |
| 17 | Explained adaptive decisions | Signal age, engagement inference, proposal, limiting factor and observed response tied to motion context |
| 18 | Machine-side adaptive execution | Qualified local sampling/actuation and desktop targets/bounds/recipes with measured latency and failure semantics |
| 19 | Trajectory quality | Segment/corner/dynamics/blending contributions and dialect-correct accuracy/timing comparisons |
| 20 | Spline/NURBS support | Dialect-specific preserved geometry or explicitly bounded conversion error with supported backend exercise |
| 21 | Five-axis tool/joint comparison | Intended tip and head/table motion, branches/limits/singularity and orientation/unwind review with actual adapter |
| 22 | Coordinate-frame inspector | Machine/fixture/work/local/rotary/tool transform tree explains effective coordinates and offsets |
| 23 | Synchronized machining | Pitch/encoder phase/reversal/retract/interruption semantics and actual threading/tapping qualification |
| 24 | Mill-turn channel/resources | Turret/spindle/live-tool/workpiece ownership, synchronization/shared-axis conflicts and transfer state simulation |
| 25 | Commissioning/fault replay | Real UI exercised with delay/stale/alarm/disconnect/tool mismatch; actual capabilities commissioned with configuration-bound results |

## Shared workspace search source checkpoint

The Cmd/Ctrl+K palette combines workflow actions with individual operations from
the currently analyzed job. Operation names, tool IDs, warning text and start-line
tokens are searchable. `T1`, `tool:T1` and `line:2` use exact token matching, so
they cannot select a `T10` or line 20 result. Opening an operation enters the
Operations task, selects its exact details and seeks its local preview through
the existing inspection route; it sends no machine command.

Each entity retains the analyzed program identity and content hash. Replacement
or clearing of that analysis rejects the stale action at invocation, refreshes
the search results and keeps the palette open. Entity records are reused while
the analysis identity remains unchanged. Rendering is limited to 40 rows with
the full match count and a refine-search prompt; keyboard selection operates on
those visible results.

A synthetic 10,000-operation study exposed 0.4–1.0-second synchronous index/search
work. Index construction and filtering now run in a single-worker executor,
with cooperative cancellation and at most one pending successor. Local actions
are available immediately. Delivery checks the query generation, popup lifetime
and analyzed-job identity; closing does not wait for the worker. A failed search
reports its failure while retaining local actions. This is source behavior, not
installed latency qualification.

This advances requirement 6 without closing it: exact measurement/alarm/frame
entity navigation, cross-domain relationships, large-job latency and installed
workflow acceptance remain open. A bounded rendered list does not prove a
bounded search or index-construction latency.

## Operation-list responsiveness source checkpoint

A source Kivy study of a 1,001-operation program found 1,001 allocated buttons
and approximately 1.4 seconds of synchronous UI publication. The operation list
now retains lightweight data for the whole program and recycles only viewport
rows. Selecting an operation reveals its row and uses the existing source,
facts, highlight and preview route. Full names and details remain available in
the selected operation card.

Repeating that mocked-hardware source study after recycling rendered three
operation rows and measured approximately 8.3 ms of synchronous publication.
This single source observation is not an installed latency qualification or
an end-to-end job-load benchmark.

Reused rows resolve their current program/operation identity at invocation;
replacing an analysis refuses stale rows and clears departing keyboard focus.
Focus reveal uses operation indices, avoiding Kivy's generic ScrollView
assumption that a recycle layout's trigger is a scheduled Clock event. Shared
history also tolerates that layout method when waiting for rendering.

This advances requirements 1 and 4. It does not qualify installed large-job
latency, virtualize every application grid, or close the overall overhaul.

## Tool-bank preparation source checkpoint

`tool-bank-preparation.md` records partial progress on requirement 11. Preparation
selection/persistence and attributed evidence do not implement stop, physical
reload, controller mapping, offset application or resume execution. Existing
playback does not enforce these local preparation records. Full requirement 11
and the overall implementation goal remain open.

The DESKTOP72 source run found six existing navigation integration fixtures with
identity-only machine contexts. The board's display-name assumption raised
`KeyError: name`; the failed suite and uninstalled artifact are retained. The
follow-up uses the machine identity as the display fallback, preserving the exact
context binding rather than inventing or switching machine identity. Tests cover
that fallback as well as the actual shared-navigation workflows.

## Shared entity search source checkpoint — 2026-10-07

Requirement 6 now includes retained inspection features and exact measurement
receipts, alongside operations and current coordinate-dependency paths. Search
accepts feature names, part names, source/registration/calibration references and
exact `feature:ID` / `receipt:ID` tokens. Receipt navigation opens the owning
feature, expands its history, clears hiding filters and selects the correct page
and provenance. Replaced store snapshots refuse stale navigation. First storage
load runs on the cancellable search worker; closed popups reject delivery.

Coordinate results open the selected dependency in a fresh zero-point review,
with configured preview, reported telemetry and unknown registration visibly
separate. Setup/controller replacement refuses stale search results. Refresh
then preserves a subsequently chosen dependency. These are review actions; no
controller writes or registration claims are introduced.

Measurement results stream through a bounded top-40 search page with a total
match count. Records do not allocate one retained command or result widget per
receipt. A 10,000-result resource test checks bounded live command objects,
deterministic ordering, exact count and cancellation. This is source evidence;
installed large-history latency and complete shared alarm/entity navigation
remain open, as do the rest of the 25-requirement implementation goal.

### Recycled operation-list compatibility follow-up

Hosted run 37612852988 at `47fb5e0` passed quality hooks and 3,194 tests,
but failed two older pose-context assertions (caption capitalization and an
empty widget tree). Empty recycled lists keep their layout manager; the
fixture now checks empty data, zero visible rows and zero viewport height.
Local continuation exposed remaining reveal checks that assumed every Kivy
layout trigger had `is_triggered`; recycle layouts expose a method instead.
Operation, shared scroll and task-deck reveal checks now tolerate that method
while still waiting for scheduled layout/texture events. Row textures reserve
a vertical inset. Selection tests explicitly open the Operations task before
clicking a rendered row, matching the virtualized view lifecycle.

DESKTOP269 built and independently verified 544 controller package files with
zero source mismatches and a strict signature at the older `47fb5e0` source.
It remains uninstalled and preserved; these follow-up fixes and entity search
require a new frozen candidate. Installed DESKTOP268 remains the recovery-safe
runtime checkpoint. Neither package verification nor focused tests closes
latest hosted CI, installed follow-up acceptance or the overall goal.

## Installed DESKTOP270 and continued review ergonomics — 2026-10-07

At `fc76d84`, hosted run 37616023276 passed 3,201 tests with 17 skipped.
DESKTOP270 was independently checked against its frozen source archive: 544
package files, zero source mismatches and a strict signature. Recovery installation
retained DESKTOP268. Native synthetic checks exercised exact/source measurement
search, receipt page selection, fixture coordinate review and operation 1,001
selection/details/highlight. Temporary records and recent-file changes were
restored under exact-byte guards; all ten checked operator paths matched their
original identities. The clean runtime was relaunched in live view with no
program, fresh telemetry/camera, Idle and zero spindle/feed. These receipts close
those bounded workflows, not the full implementation goal.

A paired local preview check observed a 3.39-second heartbeat gap while DESKTOP268
created operation rows. DESKTOP270 observed no gap over one second during that
preview load. Startup still produced layout/render stalls. A single session under
changing host load is not general input-to-display latency qualification.

The next source increment retains a compact selected operation list above its
detail heading instead of aligning the detail card and clipping the selected row.
Its list height follows the workbench viewport. Inspection review puts selected
receipt provenance before an optional deviation-chart disclosure, opens receipt
history by default, and collapses the feature-wide nominal/summary. Outside wheel
events no longer dismiss that review; normal Close/Escape and outside clicks are
preserved. Compact geometry, receipt reachability, unchanged data and no-command
checks cover these source behaviors. Installed acceptance of this increment
remains open.

Requirement 6 now also searches explicit alarm-state observations in the loaded
recording. Results carry session, sequence, connection generation and receive
time; exact `session:ID`, `sequence:N`, and `connection:N` tokens avoid prefix
matches. Navigation pauses local replay, selects the exact event and opens its
observation. Replaced recordings or mutated event contents reject stale results.
These are retained observations, not a live alarm claim or machine acknowledge,
reset, recovery or actuation. Searching a recording does not invent alarm codes,
interpolate missing evidence, or change the live machine pose.

The full 25-requirement goal remains open, including startup/latency qualification,
large-history installed search latency, measured registration and synchronized
capture, qualified collision/remaining-stock simulation and actual advanced-machine
execution/commissioning. Current source, CI, packaged/installed acceptance and
physical qualification retain separate gates.


### Scene snapshot consistency repair — October 7

Hosted verification of the review/alarm increment found ten failing interaction
cases. Scene snapshots previously copied heartbeat-driven checkbox values, which
could lag direct viewer visibility changes and contradict the actual outer-machine
framing. Snapshots now read cutter and component visibility from the viewer itself.
The controls remain presentation readbacks; taking a snapshot does not render,
rebuild, persist, or send machine commands. A regression test captures the state
before the heartbeat and verifies it remains identical after control readback.

The coordinate-search stale-context test also scopes its deliberately invalid
setup sentinel so the real setup is restored before scheduled UI heartbeats.
This retains rejection of stale actions without leaking a fake object into the
shared runtime. Packaged DESKTOP271 is retained and will not be installed against
its failed source CI. Installed DESKTOP270 remains the verified recovery checkpoint.
The correction's hosted, installed, and physical gates remain separate and open.

The correction's first hosted run stopped at three typing errors in indexed
geometry code before executing tests. The follow-up preserves the exact immutable
snapshot guard while making its protocol narrowing explicit, and gives slab
rejection and the indexed dot product concrete bool/float returns. Forty-five
focused geometry tests passed. Local verification now additionally uses the locked
mypy 1.19.1 rather than relying only on the newer local checker. DESKTOP272's frozen
archive is retained without starting its build because that source failed typing.


## Recording task concentration and bound exports — October 7

The Program workbench retains its selected filename above a collapsible
“Program details & controls” card. Machine-state telemetry and existing guarded
choose/review/pause/abort controls remain available in the card; the connection,
profile, Feed hold and STOP remain outside it. Entering a running-program context
expands the card once. Subsequent packets retain the operator's explicit choice.
Collapsing a planning card releases hidden keyboard focus without losing drafts.
The task viewport gains the space released by the card instead of leaving a gap.

Named layouts now save this disclosure in schema 5, including strict boolean
validation and readback. Versions 1–4 remain readable with a collapsed default.
Restoring the disclosure skips scroll-to-heading, preserving the selected task's
reading-position restoration. This advances requirement 8; complete workspace
arrangements, installed responsiveness and the full overhaul remain open.

Workspace search now exposes Run record import/export and matching camera-bundle
export. Search captures the exact panel, replay, live buffer and camera part. Busy,
replaced or mismatched selections refuse stale invocation; refreshing search
binds replacement commands to current selections. Exports recheck selection when
the save dialog returns and retain the accepted source in their worker closure.
Changing selection cannot silently export a different archive. Commands reveal
the owning recording task and camera section, never send a machine command, and
retain the existing exclusive-write and exported-file readback checks. This
advances requirements 3 and 6; exposure timing, measured registration and complete
cross-domain timeline qualification remain open.
