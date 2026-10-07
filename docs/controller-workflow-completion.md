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

## Close local preview source checkpoint — 2026-10-07

Program actions and shared workspace search now offer Close local preview for an
idle local-only selection. The action rechecks current job and loading state at
invocation. Running, paused, remote and in-flight loading contexts refuse it.
Closing removes the filename, operation analysis, path geometry, program timing,
repeat playback and resume-line inputs while retaining machine setup, component
profiles, visibility choices and workholding geometry. It returns to Live view,
whose position still requires connected, fresh reported telemetry.

This addresses an installed DESKTOP278 observation: removing a temporary local
preview previously required restarting the controller. The new action is source
work; its package and installed interaction remain open until verified. It sends
no stop, upload, offset, motion or other controller command and does not establish
physical setup qualification or completion of the broader overhaul.

## Shared artifact picker keyboard checkpoint — 2026-10-07

The shared browser for CAD, profiles and machining artifacts now supports
Up/Down, Home/End and page selection with a visible selected row and automatic
viewport reveal. Enter opens the selected folder or checks the selected file
through the existing asynchronous acceptance route. Cmd/Ctrl+F focuses search;
Cmd/Ctrl+L focuses the location editor. Text editors retain their normal keys,
and selection alone never imports, saves or runs a program.

Filtering clears a hidden row's keyboard identity while retaining the filename
draft. Pending directory/file checks reject selection, and background dialogs do
not intercept the frontmost modal's keys. Escape and external modal dismissal
remove the window listener and invalidate pending delivery. Fifteen artifact
picker integration tests pass, including actual window dispatch, selected recycled
row reveal, folder opening, text focus, stale-selection rejection, asynchronous
checks, preserved existing files and dismissal cleanup. Installed keyboard
interaction and large-directory latency remain open.

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

## Profile field density source checkpoint

Plain identity and asset fields now use 58-dp profile rows. A group containing a
quantity field retains 78-dp rows so its canonical unit interpretation remains
visible. This reduces empty space in embedded machine and cutter editors without
changing stored profiles, applying settings, or dropping quantity feedback.

Thirteen profile chrome, draft and embedded-browser integration tests passed,
including 360- and 600-dp libraries and preserved drafts. Locked package typing
passed all 230 source files; focused lint/format passed. This is a source
checkpoint after the frozen DESKTOP274 candidate: publication, package and native
verification of this additional change remain open. It advances requirements 4
and 8 without closing the complete desktop-grid or layout requirements.

## Inspection desktop scrolling source checkpoint

Installed DESKTOP273 exercised exact receipt search and displayed the selected
measurement identity, coordinates, source, registration/calibration references
and explicit accuracy limitation. Its review and receipt-list scrolling areas
still used Kivy's content-only scroll view: the thin visible scrollbar was not
an operable desktop drag target, and reaching the remaining metadata was awkward.

Both areas now use the existing DesktopScrollView, with a 9-dp drag target,
content and scrollbar scrolling, bounded wheel movement and nested viewport
routing. Nine inspection integration tests passed, including an actual scrollbar
drag in a short popup, retained provenance, original file bytes and no controller
commands. Locked package typing passed 230 files; focused lint/format passed.
Package and installed interaction verification of this additional fix remain
open. The complete overhaul and physical measurement qualification remain open.

## Compact layout dialog and native reading-position checkpoint

Installed DESKTOP276 at db89be4 restored a saved Run record task at scroll fraction
0.6263821772542701 after resetting the task to its top, expanding Program context
and changing to Position. The restored playback and timeline-key landmarks match
their original positions; the collapsed Program context and visible camera were
also restored. The temporary layout file was preserved outside the data path,
and all ten tracked operator JSON paths retain their original bytes. This closes
one stable-content native reading-position check, not the entire layout requirement.

The layout dialog now has one heading, a visible Close action, a width capped at
760 dp and a height fitted to its content within 85% of the window. Short windows
use the shared 9 dp draggable scrollbar while retaining the header and Close
control. Sizing waits for the next UI frame after native resize events; dismissal
cancels the pending resize and removes listeners. The embedded layout panel keeps
its heading. Thirty-six layout tests pass, including full/short viewport resizing,
visible Close, context preservation and detached resize listeners. Package typing
passes 230 files with locked mypy 1.19.1 using isolated imports; focused lint and
format checks pass. Hosted CI, new package and installed interaction of this dialog
remain separate open gates. Changed-content reading anchors and the broader
25-requirement controller overhaul remain open.

## Contextual setup next action

The setup strip's next action now re-evaluates the current dependencies, opens
the evidence inspector and reveals the first stock, mounting, tooling or offset
check that needs attention. Previously it opened the general inspector without
revealing the check named on the button. When all four receipts are current but
telemetry is unavailable or stale, it opens the Connect task and its connection
card rather than whichever Settings task happened to be selected previously.

Fifty-nine focused readiness tests pass. The new interaction cases cover each
check with declared-only, expired and changed-dependency evidence; they verify
the exact visible card, preservation of every unrelated current receipt and
byte-identical evidence storage. Connection navigation also preserves storage
and sends no command. Locked isolated package typing passes 230 files and focused
lint/format checks pass. Hosted CI, packaging and installed verification of this
source increment remain open. This is a partial improvement to requirement 7;
actual setup measurement and the complete workflow remain separately unqualified.

## Recorded evidence checks source checkpoint

Run record now includes a compact review summary and a collapsible evidence-check
panel. At the selected receipt or intermediate playback time it reports receipt
age, missing telemetry, connection generation boundaries, archived alarms and
disconnects, unavailable position, and an optional logical-tool comparison. The
freshness budget and expected tool are local review inputs; they do not change
controller settings or establish physical tool identity or executed program lines.

Duplicate-time boundaries remain independently selectable. Missing tool fields
never borrow an earlier packet's tool. Pausing or opening marker evidence retains
the playback review time, while explicitly selecting First resets it to that
receipt. Invalid input drafts remain visible with the last applied checks retained;
opening another recording clears the expected tool. Review work preserves live
machine state, observed pose, recording buffer and original archive bytes.

Forty-one focused unit and integration tests pass, including real UI actions for
fault review and playback freshness, with no controller commands. Locked isolated
package typing passes 231 files; focused lint and format checks pass. Hosted CI,
packaging and installed interaction verification of this increment remain open.
This advances historical review and fault-evidence coverage without closing the
complete run-alignment, actual fault replay or broader 25-requirement overhaul.

## Responsive cutter-table controls

The saved-cutter comparison dialog now keeps search on a full-width row and wraps
Filters, Reload, Select results and Clear into a separate adaptive action grid.
This removes fixed-width controls that could squeeze search outside a narrow
viewport. Native resize sizing is deferred to the next UI frame; dismissal removes
the resize listener and cancels pending sizing.

Twenty-two cutter-table tests pass, including repeated 360-, 600- and 1200-dp
resizing, reachable action bounds, at least three complete data rows in the narrow
viewport, retained selection and unsaved editor drafts, actual filter/select/clear
actions, original store bytes and no controller commands. Existing virtualized
keyboard/sort/column-resize and reviewed paste/save cases continue to pass. Locked
isolated package typing passes 231 files; focused lint/format checks pass. This is
a source improvement to requirement 4; publication, hosted CI, packaging and
installed interaction of this additional increment remain separate open gates.

## Short-window cutter-table repair

DESKTOP279 native testing at 1340 by 792 pixels exposed overlapping controls
and a vanished row viewport. The table body now scrolls when vertical space is
limited, retains at least three rows, and keeps the footer actions outside the
scrolling body. Header dividers capture their original press during nested scroll
negotiation so immediate column resizing survives this layout change.

Four integration cases pass, including the short high-density viewport, visible
Close, accessible rows, preserved selection and editor draft, actual coalesced
pointer resizing, and reviewed edits. The installed failure remains recorded;
this repair requires a new build and repeated native resize verification. Current
local package typing also reports 148 errors in imported addon files despite the
7700 source passing hosted quality hooks; that discrepancy remains open.

## Operation trajectory facts source checkpoint

Selected operation process details now report nominal programmed feed time,
timed and untimed resolved feed-block counts, the shortest nominal source block,
and the largest sampled direction change between eligible adjacent feed blocks.
Results retain exact source lines. Imperial feed is converted to mm/min for
timing; an inverse-time arc is one source block and each G93 move requires its
own explicit F word. G95 timing remains unavailable without supported spindle
synchronization interpretation. Rapid and unresolved moves are excluded.

Arc subdivision boundaries are not treated as controller corners. Frame changes,
rapid transitions, geometric discontinuities and intervening source lines do not
create an eligible direction-change boundary. Sampled arc endpoint directions
approximate tangents. These facts are integrated into the existing selected
operation details; acceleration, jerk, blending, overrides, actual backend timing
and installed qualification remain open under requirement 19.

The daff484 hosted run passed quality hooks and 3430 tests but failed two older
Program layout tests that assumed two idle buttons regardless of local selection.
Fixtures now explicitly cover empty/local-preview and playing states and assert
the exact control identities, including Close local preview. The failed run is
retained; a new full hosted result remains required.

## Bounded cubic analysis and operation cancellation

Explicit LinuxCNC analysis retains original G5 control geometry and source lines,
converts with a parameter-matched position-error bound, reports tolerance and
segment count in process details, and encloses the curve using the original
control hull. Carvera analysis continues to reject G5. Program-wide segment
limits, finite-coordinate/depth limits and cooperative cancellation refuse
unbounded or interrupted work without publishing a truncated cubic. Program
replacement/clearing now supplies the cancellation signal to the existing
operation-analysis worker; stale result delivery remains guarded.

The converter, documented G5/chaining/unit interpretation, rejection cases,
existing operation/timing behavior and cancellation pass 103 unit cases. A real
selected-operation UI regression and a source UI cancellation case pass with
no controller commands. Full lint/format and architecture/typing verification
remain separately recorded. Operator-facing dialect study selection, installed
spline rendering, quadratic/NURBS, supported-backend exercise and physical
qualification are OPEN; this does not close requirements 1 or 20. Details and
primary source are in `bounded-spline-analysis.md`.

### Compact cutter-table navigation — 2026-10-07

DESKTOP280 native review at 1340×792 pixels retained three rows, selection and an operable Close action, but outer native scrolling did not reliably reach the search/filter controls. This failure remains retained. Short dialogs now expose Search & filters and Cutter rows actions in the fixed footer; they disappear in taller dialogs. Four full integration cases pass, including action-driven reachability, retained selection/editor draft, unchanged profile bytes, reviewed-save conflicts and no controller commands. Installed verification of this additional repair remains OPEN. The complete layout and responsiveness requirement remains OPEN.

### Local dialect and cubic geometry review — 2026-10-07

Operations now exposes collapsible local analysis settings with explicit Carvera
or LinuxCNC G5 interpretation, drafted mm position bound and whole-job segment
budget. Applying valid settings replaces the analysis through its cancellable
worker; invalid drafts preserve the applied settings and current analysis. New
filenames and clearing reset to Carvera. Inspecting a resolved cubic reveals
exact contiguous converted sections, its complete control polygon, all XYZ
control points, conversion evidence, source line and program hash. Equal XY
scale preserves the shape, and section paging never decimates the conversion.
An indexed immutable point snapshot avoids whole-job scans on selection.

These studies retain the existing machine pose and do not seek or highlight a
Carvera preview interpreted independently. Source bytes and machine capability
state remain unchanged; no commands are sent. Final focused verification passed 28
focused cases, including actual setting actions, invalid drafts, exact section
boundaries, cancellation and existing motion-tool indexes. Installed interaction,
backend exercise and the complete requirements 1, 19 and 20 remain OPEN.

### Program-file discoverability — 2026-10-07

The existing guarded Choose program action now remains beside the program status
in an adaptive summary row instead of disappearing into collapsed details. It
wraps on narrow layouts and is retained across heartbeats. Twenty integration
cases pass, including opening and dismissing the actual picker from collapsed
details, exact active-program control membership, draft preservation and no
controller commands. Installed interaction of this increment remains OPEN.

### Installed compact cutter navigation and draft verification — 2026-10-07

DESKTOP281 at source 13329107 passed bounded native interaction at 2340×1606
and 1340×792. Search/filter and row navigation remained reachable in the fixed
compact footer; filtering preserved the selected cutter. Native column-divider
drag resized the Name column. An unsaved 6.4 mm diameter draft survived compact
saved-table browsing and returning to the editor; saved rows remained 6.35 mm.
Restoring the original draft value returned the editor to no pending changes,
without saving or loading a preview. Independent SHA256 comparison found all ten
tracked operator JSON paths unchanged. Live Job workspace and camera were restored.

These close the named bounded interactions, not full grid behavior, native bulk
editing, large-scale latency or the complete requirements 1 and 4.

### Quadratic spline source checkpoint — 2026-10-07

Explicit LinuxCNC analysis now retains G5.1 and its original three controls,
using degree elevation through the bounded cubic converter. Forty-two focused cases
pass, including original-polynomial error checks, units and modal interpretation,
invalid-block refusal, mixed-degree budget and interruption of cubic continuity.
The local review labels G5.1 and shows the original quadratic polygon. General
rational/NURBS implementation, installed interaction and supported-backend
execution remain open; requirement 20 and the complete goal remain open.

### Installed local analysis and cutter focus checkpoint — 2026-10-07

DESKTOP282 at b53138b8 passed independent verification of 547 packaged files,
strict signature and recovery-preserving installation. Native interaction confirmed
Choose program remains visible with details collapsed, local preview selection,
explicit LinuxCNC analysis at a 0.001 mm bound and 1000 whole-job segments, rejection
of a nonfinite draft, and source-line cubic geometry with its source hash, four
controls, 92 segments and a reported bound of 0.000963659 mm. Close local preview
cleared the study; exact own-recency-delta restoration and independent hashes of ten
operator paths returned the app to clean Live monitoring with no program selected.
Camera stale/timeout labels and recovery were observed; camera reliability remains
unqualified. Receipt: native-analysis-verification.json under the DESKTOP282 artifact
root. Quadratic 20487ba is published but is not in DESKTOP282.

A separate DESKTOP281 native Down-key check failed to advance a clicked cutter row.
A regression now reproduces this through real touch release and Window keyboard
routing rather than calling the grid handler directly. Consuming a row click now
protects the same release from clearing the grid focus, using FocusBehavior's
existing ignored-touch mechanism. Thirty-seven cutter-table and shared-focus cases
pass, including Down, Shift+Down, search focus transfer, unchanged saved bytes and
no controller commands. Installed qualification of this focus repair remains OPEN;
the native failure receipt is retained. Requirements 1, 4, 20 and the full overhaul
remain OPEN.

### Preserved NURBS geometry source checkpoint — 2026-10-07

The rational geometry kernel now retains controls, weights, knots and degree and
converts continuous clamped positive-weight curves through homogeneous knot
insertion and rational Bezier subdivision. Output retains original parameter
intervals, a position bound and control-hull bounds. Budget, cancellation,
conditioning and depth limits refuse incomplete conversion. An independent
original-knot de Boor evaluator checks nonuniform/repeated spans and 100 seeded
weighted curves; polynomial and rational regression coverage totals 71 passing
tests. Strict isolated module typing and focused lint/format checks pass.
`docs/nurbs-geometry.md` describes the analytic bound and numerical allowance.
Dialect parsing, linked program/UI integration, packaging/native and supported
backend execution remain OPEN; requirement 20 is not complete.

The LinuxCNC rational-geometry adapter additionally maps default order 3 and
the official uniform clamped knot convention, checked against source
46a388fd15a477b4bf2ce090919b0273074e7fc1. Seventy-eight spline/NURBS cases pass.
Complete G5.2/G5.3 program parsing and linked workbench review remain OPEN.

The complete version-bound NURBS data-block parser now preserves source/control
line identity, pre-block incremental interpretation, three-plane geometry,
explicit positive control weights and actual effective-order behavior. Combined
block/rational/polynomial validation passes102 tests; strict isolated typing
passes both modules. Program analyzer and linked workbench integration remain OPEN.


### Whole-program NURBS and linked geometry review checkpoint — 2026-10-07

Complete pinned G5.2/G5.3 data blocks now enter the explicit LinuxCNC study
analyzer without treating control rows as linear moves. Closure publishes bounded
motion; checkpoints preserve pre-block position and per-row feed. Any source row
in the span opens the same review, including active-plane projection and paged
controls, weights and knots. Polynomial/rational conversion shares one budget;
invalid/incomplete blocks and unsupported feed modes stay unresolved. Recovery
inside a block is refused. Move explanations retain source-span warnings.

DESKTOP283 is independently verified (547 source files, no mismatches, strict
signature), installed with DESKTOP282 recovery, and its clicked-row Down/Shift+Down
keyboard and search-focus transfer are qualified natively. All ten tracked
operator states remained unchanged. This bounded keyboard checkpoint is CLOSED;
requirement4's broader ergonomics/authoring acceptance remains OPEN. Native new
NURBS UI/package, backend execution, G93/G95 data-block semantics, camera
registration/synchronized capture and full25 requirements remain OPEN.

### Dialect-bound inherited-feed correction — 2026-10-07

A pinned LinuxCNC source read reproduced six failing cases where G20/G21 kept the
old numeric G94 F value, making inherited-feed timing wrong by25.4. The analyzer
now preserves physical feed while changing program units, lets an explicit same-
block F override it, handles round trips and leaves unrepresentable inherited
feeds unknown. Straight/cubic/quadratic/NURBS timing, move explanations and
operation facts share that corrected state. G93 is not scaled as distance/time;
G94 mode transitions still need new feed. Carvera semantics remain separately
unqualified. Focused134 cases pass, and the four-module strict analysis boundary
passes. The failed-before log and exact primary-source blob are retained.

DESKTOP284 was frozen before this correction. Its build is preserved, but the
candidate is superseded and must not be installed. Installed DESKTOP283 remains
unchanged. Replacement package, native curve-review exercise, hosted latest CI,
supported backend exercise and full25 requirements remain OPEN.


## Helper request framing and native Save-dialog investigation — 2026-10-07

DESKTOP283 native diagnostics export times out reading Downloads and the
artifact folder. A subsequent empty local folder request reports helpers still
stopping, rather than completing. A direct invocation of that same
packaged helper reads the artifact folder in about0.19seconds. Native parent
stack samples show the request thread polling; the short-lived child sample
could not finish before its observation deadline. These observations do not
establish the native failure cause.

A separate focused regression reproduced the helper waiting for stdin EOF after
a complete JSON request. Requests now use one bounded JSON line, so the worker
can answer while the input writer remains open. Legacy unframed callers that
close stdin remain accepted. The request size, cancellation, response validation
and child retirement limits remain enforced. The29 helper tests pass, including
the retained-writer regression. This closes the protocol source defect; native
export verification remains OPEN. DESKTOP285 was frozen before this framing
change and is building from the preceding feed-unit correction.


## Packaged filesystem worker behavioral gate — 2026-10-07

`scripts/verify_artifact_worker.py` checks the independently verified bundled
executable with a framed file-check request while deliberately retaining stdin
until the worker answers and exits. It limits time and output, checks the exact
response and confirms no file was created. It rechecks package identity, source
manifest and strict signature before saving an exclusive successful receipt.
This gate detects the EOF-dependent behavior in installed DESKTOP283 within its
four-second deadline. The corrected source worker passes; the60 helper and
package-verification tests pass, including EOF-dependent, malformed, oversized
and unsuccessful worker responses. GUI launch environment, folder browsing and
actual export still require separate installed interaction evidence.


## Installation requires packaged helper proof — 2026-10-07

The recovery-preserving installer now refuses missing or unsuccessful filesystem
worker proof before any copy or application replacement. It checks source
revision, archive digest, version and the current executable digest, plus a
successful retained-stdin response within four seconds without file creation.
The install receipt retains that proof. Tests exercise missing/stale identities,
changed executable, failed/EOF-dependent/file-creating probes, unbounded and
nonfinite durations, and preservation of the existing application.

The first combined regression had69 passing tests and one corrected source
worker timeout. The unchanged recheck passed all70 in3.05seconds. Both logs are
retained; the four-second gate was not relaxed. This proves the rejection logic
and the passing recheck, not consistently bounded native latency. DESKTOP285
remains the sole running build; its pre-framing helper still needs behavioral
verification before any installation decision.


## Spline review paging density — 2026-10-07

Curve-section and control/knot paging rows now appear only when their respective
content spans multiple pages. Small spline reviews retain the plot, complete
control data and source/bound information without two rows of inactive buttons.
Long reviews keep their independent exact-section and control/knot navigation.
Clearing or replacing the selection removes stale controls and restores required
paging when appropriate. Eleven analysis-workbench integration tests pass,
including short/long review visibility, original geometry retention and clearing
then reopening a long control list. Installed layout verification remains OPEN.

## Fresh-session native navigation and export — 2026-10-07

Installed DESKTOP283 successfully browsed Downloads and an empty local evidence
folder after an idle application restart, then saved two diagnostics exports.
Independent JSON readback recorded nine post-startup navigation callbacks across
Program, Scene, Position, Setup, Console, Machine, Camera and Spindle: callbacks
were 1.16–2.86 ms, clock-turn notifications 17.38–74.04 ms and window-flip
notifications 12.20–58.87 ms. These notifications do not establish actual screen
presentation or input-dispatch latency. No program was loaded; heavy-program
navigation remains unverified.

The same session retained one startup heartbeat stall of 3.30 seconds, with image
loading visible in two sampled stacks. This is a diagnostic lead rather than a
root-cause finding. No later one-second stall was recorded in this sample; the
largest measured refresh callback was 17.44 ms. All ten tracked operator files
were unchanged. The older session's export failure and retiring-helper evidence
remain preserved. Fresh-session success on the older worker does not prove the
new framing repair fixes that native failure. Exact-source packaged worker proof
and installed spline-review verification remain OPEN.

## Inspect long spline sections at useful scale — 2026-10-07

Spline review now offers whole-spline and current-section framing, plus a control
polygon visibility choice. Section framing enlarges the exact selected page at
equal active-plane scale and clips outside context to the plot viewport. Original
controls, converted points, source identity, error bounds and independent data
pages remain unchanged. The legend distinguishes clipped context and hidden
controls; empty reviews disable these choices. Twelve analysis-workbench tests
pass, including enlarged section containment and source-geometry retention across
page changes. Source rendering was inspected separately; installed acceptance
remains OPEN.

DESKTOP285 completed its build and independently passed frozen-source and strict
signature checks, then failed the four-second retained-stdin worker behavioral
probe. Its uninstalled package and failure log are retained with a superseded
guard. A replacement must contain the framing repair and pass that behavioral
gate before installation; package identity alone is insufficient.

## Shared search keyboard ownership — 2026-10-07

Workspace search now handles navigation, Enter and Escape only while its modal
is frontmost. A covering dialog retains keyboard ownership; background palette
selection and actions remain untouched. After the covering dialog closes,
palette navigation works again. The regression reproduced background Down-key
handling before the guard, then passed with selection/action and listener-cleanup
checks. The combined search/palette suite passes 28 tests. This is source
verification; installed interaction remains OPEN.

## Installed large-operation navigation sample — 2026-10-07

DESKTOP283 loaded a synthetic local-only program with 1,001 named features plus
the setup operation (1,002 operations, 2,004 source lines). Shared search opened
Feature 1001 at source lines 2003–2004, revealed the final recycled row and linked
its preview/details. Seven subsequent workbench tab switches recorded callbacks
of 1.19–2.12 ms and window-flip notifications of 6.53–16.33 ms. No additional
one-second heartbeat stall was recorded beyond the earlier startup episode.

The native Save dialog exported the loaded-workspace diagnostics. Close local
preview then cleared the synthetic program and returned to live monitoring.
The app was closed before removing exactly the added recent-file entry, with its
post-test bytes preserved and all ten tracked operator files verified against
their baseline hashes/absence. After reopening, no program was selected and
fresh reported pose and camera viewing resumed. No upload or machining command
was issued. This closes this specific installed interaction sample, not all
large-program/CAD latency cases or full responsiveness qualification. Notification
timing is not input-dispatch or actual screen-presentation timing.

## Precise shared operation search — 2026-10-07

The installed large-job sample exposed an ambiguity: unquoted `Feature 1001`
also matched 1001 in other operation numbers and source-line fields. Shared
search now accepts quoted, case-insensitive contiguous phrases with word
boundaries, such as `"Feature 1001"`, and an exact `operation:N` selector for
the displayed one-based operation number. Ordinary queries retain their
all-word search behavior. Unfinished quoted phrases remain searchable while
typing, and apostrophes and path backslashes remain literal.

Both full and bounded-page search use the same parsing and matching rules.
Operation selection remains bound to the current analyzed program, with stale
selections refused. The asynchronous palette integration test selects the exact
feature through Enter and verifies no machine command is sent. Source tests
pass; this search change is not included in DESKTOP286 and installed acceptance
remains OPEN.

## Installed spline review and worker recovery — 2026-10-07

DESKTOP286, frozen at `2fab5dab7ae64f414a7c1e819a8b66f54be8b3ce`,
passed independent source/signature verification (549 files, zero mismatches),
the retained-stdin packaged worker probe (1.9564 seconds, exit zero, no file
created), and installation verification. DESKTOP283 remains a recovery app.
The native chooser and analysis controls reviewed a synthetic 38-line G5.2/G5.3
program locally: 4,096 bounded segments at 0.0001 mm requested tolerance,
source lines 4–38, with the reported position-error bound at most 0.0000917177 mm.
Curve section 257–512 and control/knot data 17–32 were selected independently;
current-section framing and hidden control polygon remained effective.

The native diagnostics Save dialog successfully exported JSON, independently
read back with SHA256
`2f1f7db04fa2bd1469025a5e8b55ff942f13d5477489aad600505f598690e33f`.
A 3.275303-second startup heartbeat gap remains recorded; sampled resource lookup
and event-loop stacks are leads, not a root-cause finding or latency acceptance.
The synthetic preview was closed, its sole added recent entry was preserved and
removed with the app closed, and all ten operator records matched baseline.
Relaunch showed Idle, no program selected, fresh reported pose and camera.
No physical command was issued. This closes the bounded installed review and
native export sample; backend spline execution and broader responsiveness remain
OPEN. Receipts are retained under
`/Users/wes/.codex/artifacts/carvera-desktop286-20261007/`.

## Direct geometry and source navigation — 2026-10-07

Inspecting a source block in an explicit study dialect now reveals its own
spline geometry directly, without seeking the legacy toolpath. Source navigation
offers a Spline geometry link only when the selected block has resolved geometry;
the plot offers Source & modal state to return to the block explanation. Both
links use the existing settled-layout reveal and task routing, preserving source
identity, selected line and geometry. This removes repeated long-form scrolling
between the explanation and plot. Integration coverage checks actual viewport
visibility at both destinations and verifies no controller command or legacy
seek. This source change follows DESKTOP286; installed acceptance remains OPEN.

## Startup resource lookup investigation — 2026-10-07

An isolated hardware-mocked source startup profile followed the native resource
lookup stack evidence. It recorded 45 failed lookups for `fresk.png`, a nonexistent
default on three legacy icon-button classes. Their intended KV/default icon is
empty or an explicitly assigned asset. Those Python defaults now start empty,
avoiding transient requests for the nonexistent placeholder. The repeated source
probe recorded zero `fresk.png` lookups and its integration test passed.

This is a bounded unnecessary-I/O repair, not a claim that startup latency or the
native 3.275303-second heartbeat gap is fixed. The before/after profiled fixture
times were 15.52/15.89 seconds; they do not demonstrate a startup speedup. The
before probe attributed 0.02178 seconds to the 45 missing-placeholder lookups;
profiler overhead and source/package environments differ. Raw probe scripts,
JSON and logs remain in `/private/tmp/carvera-startup-resource-probe-20261007/`.
The repair follows the DESKTOP287 freeze and is not included in that package.

## Bounded projection work for long declared paths — 2026-10-07

The advanced motion inspector previously rebuilt projected tip coordinates for
the entire declared path whenever its cursor, projection plane or reference frame
changed, despite displaying only a 200-pose page. It now reads/project only that
page and reads the selected pose for its linked detail. The complete immutable
path, global cursor, work/world frame choice, signed joint demand and page bounds
are retained; no trajectory decimation or machine command is introduced.

A 50,000-pose lazy sequence regression failed before the repair when startup
walked beyond its read budget. After the repair, middle/end/start cursor changes
and a world-frame change each read at most 201 poses and retain the expected
page, global selection and projection. Nine declared-path/motion-view integration
tests pass, including compact layouts, picking, paging and scroll-anchor behavior.
This proves bounded source data access and existing interactions, not native
input latency or physical trajectory qualification. The change follows DESKTOP287;
installed large-path acceptance remains OPEN.
