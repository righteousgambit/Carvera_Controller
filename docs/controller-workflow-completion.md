# Workflow completion and advanced-machine requirements

The latest 25 recommendations extend the existing requirements ledgers. They do
not replace earlier requirements or treat existing partial foundations as complete.
The implementation goal remains active. Each workflow needs source validation,
installed interaction evidence and, where applicable, actual backend and physical
qualification. A machine profile declaration does not establish installed hardware.

## Imported stock geometry — validated engine source, 2026-10-09

The stock-input foundation reads bounded ASCII or binary STL into detached,
immutable stock-local millimetre triangles. Source units are mandatory; source
bytes and their SHA-256 remain attached. It does not guess scale, recenter,
silently weld seams or repair winding. Validation rejects incomplete STL grammar,
nonfinite or excessive coordinates, duplicate/degenerate faces, open or
nonmanifold edges, inconsistent edge direction and disconnected vertex links.
Two otherwise closed shells touching at a single vertex are therefore refused.
Reads, parsing and topology preparation support cancellation.
All43 input tests pass, along with strict typing and scoped lint/format checks.
Independent constructed STL fixtures accepted cube, wedge, L-shaped stock,
closed cavity and separated components and refused three malformed surfaces.

`StockSolid.validate` adds exact rational triangle-intersection and shell-containment
checks, rejecting crossing/contact outside shared mesh edges/vertices and ambiguous
nested-shell winding. Separate pieces, concavities, closed cavities and nested
material islands are supported in either overall winding direction. An indexed
triangle tree and explicit work budgets bound candidate/ray processing; exceeding
the budget fails without substituting a bounding box. Validation can be cancelled.

`voxelize` classifies actual grid centers against material intervals and publishes
a new volume only after completion. Source gaps/cavities start empty. Translation
and program-Z pivot rotation preserve the declared frame, with precision checks
for excessively fine distant grids. Identity retains exact source bytes, units,
placement and the explicit unqualified registration state. Independent clones
retain actual occupancy. Schema-3 snapshots preserve initial occupied count, so
source cavities are not reported as machined removal; schema-1/2 remain compatible.

All162 stock-input/solid/machining/exchange-cancellation tests pass. Cases include
analytic membership at boundaries, real cavity versus material cuts, translated
and rotated stock, self-intersection/contact refusal, nested winding, work budgets,
cancellation, cloning and snapshot validation. Independent retained-fixture readback
checked all1848 cell centers against constructive analytic regions in five solids,
and refused three malformed inputs. Three engine files pass strict typing; both
architecture contracts pass. Startup/transfer regression adds72 passing cases.

This closes the bounded solid-validation/initial-occupancy **source engine** scope.
Desktop import, actual mesh preview/placement controls, context and source identity
through residual/portable jobs, and installed interaction remain OPEN. Measured
stock registration and physical clearance/machining remain UNVERIFIED. The existing
desktop rectangular-stock workflow is unchanged. The frozen DESKTOP327 archive
does not include this stock pipeline and its package/native gates stay separate.

## Native filesystem helper and first-launch qualification — 2026-10-09

DESKTOP325 independently matched all570 packaged source files and passed strict
signature verification, but its immutable first filesystem-helper launch timed
out at the unchanged four-second deadline, with no response bytes. A subsequent
0.602-second diagnostic run does not qualify that failed candidate. DESKTOP324
remains installed; the failed attempt, archive and signed candidate are retained.

The replacement macOS helper compiles directly against Foundation and ICU. It
contains no Python, Kivy or controller bootstrap. The portable Python worker
remains the protocol reference and the implementation for other platforms. Native
tests exercise actual compilation/signing, first execution with stdin retained,
directory creation, existing/new-file checks without writes, relative/home paths,
symlinks, Unicode full case folding and code-point sorting, invalid requests,
one-line/legacy EOF framing, the20,000-child bound before filtering and the4MiB
ASCII-escaped response bound. Empty suffix matching explicitly retains Python's
all-files behavior. Response serialization uses a bounded native buffer.

The dedicated-v3 packaging layout binds both native and reference worker source
to the frozen archive and retains the helper executable hash. Missing, altered
or escaping native source blocks verification. The immutable first-attempt record,
four-second deadline, exit requirement, retained-stdin check and no-file-created
check remain installation prerequisites. Source validation, packaged first launch,
installation and native file-picker/receive-diagnostics use remain separate gates.
All208 native/protocol/packaging/installer cases and24 rendered file-picker and
diagnostics cases pass. Package254 typing, both architecture contracts, lint and
678-file formatting pass. These source checks do not qualify a frozen package.
An additional actual-helper parity check then found that pasted file paths ending
in `/` or `/.` were rejected. DESKTOP326 was stopped during dependency analysis
and preserved uninstalled. Native lexical normalization now removes only empty
and dot components, retaining symlink-aware parent traversal, and home expansion
honors the same HOME environment as the parent. These cases have explicit parity
tests before the replacement candidate is frozen.
Directory metadata reads use the already-open directory, avoiding a fresh deep
path traversal per entry. Large-directory tests retain their child counts and
four-second helper deadline. Their outer test budget is180seconds because creating
20,001 local files exceeded the default60-second fixture budget; this does not
extend helper execution. Hard links were slower here and are not used. Earlier
fixture and timing failures are retained separately from actual helper results.
Reference-worker framing now measures its one-second response after an explicitly
bounded four-second import bootstrap; the independent cold probe still requires
import, request, response and exit together within four seconds. Slot-retirement
tests use a lightweight real child, keeping their one-second slot deadline without
conflating it with Python module import time. This is harness separation, not a
claim that the earlier one-second full-startup failures were repaired.
The oversized-response path also stops once valid entry strings alone provably
exceed4MiB, excluding unreadable and filtered children. This conservative lower
bound cannot reject a response that would fit and avoids constructing a payload
already known to exceed the unchanged final serialized-byte limit.
Queue-budget propagation is checked with a deterministic clock and stalled child:
0.2seconds waiting for a slot leaves only0.1seconds of a0.3-second request budget.
This avoids depending on a timer thread being scheduled between two wall-clock
instants and detects an incorrectly reset deadline directly. Actual child timeout,
cancellation, framing and cold-start checks remain separate.

The frozen DESKTOP327 package independently matched all571 source files and
passed deep strict signature verification. Its immutable first native-helper
launch nevertheless failed: request sent, zero response bytes, no observed exit
by4.013seconds. The successful package checks do not supersede this failure.
DESKTOP327 remains uninstalled, and DESKTOP324 remains installed. The attempt,
failure, archive and signed bundle are retained. A separate post-failure diagnostic
cannot qualify this candidate. Removing Python bootstrap has not yet established
the required packaged first-launch performance; the remaining delay is unresolved.

Future first probes now retain child PID and bounded observations of six fixed
native startup tokens: entry into main, request read/parsed/executed, response
encoded/written. Tokens are opt-in through the probe environment. Raw stderr,
request paths, payloads and arbitrary diagnostic strings are never retained; the
side channel has a separate4096-byte bound. The absolute four-second deadline,
retained stdin, exit requirement and immutable first-attempt gate are unchanged.
All35 verifier cases and33 freshly compiled/signed native parity cases pass,
including fixed-token observations and timeout/privacy limits. This does not
identify DESKTOP327's cause or qualify/install it. Its original attempt/failure
records remain intact. A fresh frozen package with stage evidence and installed
picker/receive-diagnostics verification remain OPEN.

## Receive-loop reliability and retained disconnect evidence — 2026-10-09

Native DESKTOP324 still experienced repeated idle connection losses across
generations; successful status reacquisition after configuration download did
not establish sustained connectivity. The new source checkpoint separates
host receive-loop progress, successful status-poll writes, arriving bytes and
valid pose packets. The Spindle workbench shows the current receiver stage and
ages; diagnostic exports retain eight watchdog disconnects with bounded error
class histories, even after reconnect resets current observations. The watchdog
freezes its evidence before closing the link. No diagnostic observation grants
readiness or substitutes for an actual received valid status packet.

Status and diagnose polling now use monotonic time, so wall-clock changes cannot
stall their cadence. Wi-Fi commands use complete TCP writes rather than accepting
a potentially short send silently. A readable closed socket raises a transport
error and receiver exceptions back off instead of spinning at full CPU. Each
controller owns its own stop event, avoiding one controller stopping another's
receiver. These repairs are not yet evidence that the observed native losses
have been resolved; frozen package, installed diagnostic capture and sustained
connection qualification remain separate gates.

## Observable calculation phases and worker recovery — 2026-10-09

Material removal and clearance review now expose their actual worker phase,
segment count where available, source line where available, elapsed time, time
in the current phase and age of the last progress update. A bounded observation
model shares detached snapshots with the workbench at four updates per second;
worker callbacks no longer enqueue competing status messages. Cancel acknowledges
the request immediately while preserving the distinction between requested and
completed cancellation. Completion stops the progress timer.

Unexpected worker exceptions restore controls and retain the previous stock,
clearance review and navigation. The workbench reports the failed phase and
exception class; the local log retains the traceback. Diagnostic exports include
a detached calculation snapshot and the last sixteen phase timings, distinguishing
worker preparation, calculation and waiting for workbench delivery. These are
local observations, not machine execution, result acceptance or an estimated
completion time. CAD identity and stale-input acceptance guards remain in force.

Preview and Compare now explain when the observed live pose is unavailable or
stale. A fresh native retry on installed DESKTOP323 successfully returned from
Preview to Live; the earlier inert click was not reproduced. The guard still
requires a connected, fresh observed pose.

The four earlier five-second simulation deadline failures passed on unchanged
DESKTOP323 source, and a separate unchanged full workspace run passed all49
cases. This establishes intermittent behavior, not a resolved performance cause;
the deadlines remain unchanged. The new phase snapshot then located a candidate
timeout in fixture/workholding bounds preparation. Immutable snapshots now retain
whether validated indices cover every vertex, with cancellation checks while
establishing coverage. For complete coverage, collision preparation translates the
two cached bounds corners; work coordinates are translation only. Mutable geometry
and snapshots with unused vertices retain the previous all-position scan, preserving
its exact envelope and minimum thickness. A metadata-only CAD identity test is
isolated from delayed viewer rendering. DESKTOP324 package/install/scoped native
qualification is CLOSED at frozen `860f897f317f8551dc00462af793c60a9c4b1832`:
569 packaged files matched, strict signature verification passed and the first
filesystem-helper probe exited in3.318seconds within its unchanged four-second
deadline. Native local preview, phase progress, navigation during calculation,
partial cancellation and diagnostics export were exercised. Operator JSON bytes
were independently restored and verified. Receipt:
`/Users/wes/.codex/artifacts/carvera-desktop324-20261009/native-workflow-verification.json`.
Sustained connection and latency qualification remain OPEN.

All228 final model/rendered cases pass, including the unchanged five-second
simulation deadline checks. Package253, strict machine120, checked UI bodies2
and strict snapshot-module typing pass, as do both architecture contracts, lint
and678-file formatting. Earlier failures remain retained. One ordered synthetic
source comparison with two200,000-vertex immutable components produced identical
collision scenes: unchanged per-vertex bounds took6.343seconds and cached corners
0.000058seconds. This timing is not an installed/native latency qualification.

DESKTOP323's bounded camera checkpoint is independently CLOSED at
`d45dc93e01da54b23ff54a3d11986988fa64a57f`:568 exact packaged files, strict
signature, immutable first helper in1.873seconds, recovery322 retained. Native
pause/navigation/resume/reconnect, controlled unavailable source and restoration
passed. Seven operator JSON files remained byte-identical; config changed only
322to323. Fresh complete Idle/RPM-zero telemetry and the installed executable
were independently verified. Receipts:
`/Users/wes/.codex/artifacts/carvera-desktop323-20261009/`.
Sustained camera reliability, same-source native failure retention, measured
camera registration/exposure synchronization, full original25 and supplementary
requirements, hosted CI, integration and physical qualification remain OPEN.

## Camera delivery ownership and visible frozen frames — 2026-10-09

Camera GET ownership now remains serialized across source generations. Reconnect,
pause and shutdown cannot publish an obsolete response or start a concurrent GET
while the preceding generation still owns its request. The workbench reads delivery
metrics, enabled state, image and error together under one lock.

Repeated server capture timestamps retain the original image and receipt time;
they do not upload another texture or duplicate a recording receipt. A backwards
timestamp is rejected with an actionable clock diagnostic. Request failures,
recoveries, repeated captures and time since a new delivery are visible in Source.
These counters describe transport and reported timestamp progress; they do not
qualify exposure synchronization or measured motion association.

Paused, stale, recovering and capture-time-unknown images carry an explanation
inside the image pane. The badge occupies at most 15 percent of its height and is
absent for a fresh live image. Recorded images are explicitly marked as retained.
The last valid image remains available during a request failure.

The legacy profile reflow test now visits every task and checks its mounted fields
against the editor in window coordinates. Inactive task fields intentionally do
not participate in layout. The failed broad run and unchanged-DESKTOP322 baseline
comparison are retained alongside the corrected source checks.

DESKTOP323 package/install/native acceptance remains OPEN pending independent
receipts. The 12-request current camera transport sample returned fresh JPEGs,
but does not establish sustained reliability. Original requirements 1, 3, 8 and 25,
measured camera registration/synchronization, hosted CI, real advanced-machine
adapters and physical qualification remain OPEN.

DESKTOP322's compact editor/review-return checkpoint is independently CLOSED at
`78e6acd2774c389f2d439575cc951a5338285827`: 41 focused rendered tests, 568 exact
packaged source files, strict signature and immutable first helper in 1.825 seconds.
Native Geometry/Identity/drawing and captured-review navigation passed; the owned
test additions were removed, seven operator JSON files remained byte-identical,
and fresh complete telemetry reported Idle/RPM-zero. Recovery321 is preserved.
Receipts: `/Users/wes/.codex/artifacts/carvera-desktop322-20261009/`.

## Cutter editing and retained clearance review — 2026-10-09

Cutter identity now has its own retained task. Geometry starts with editable
dimensions; in compact panes its linked drawing follows those controls rather
than consuming the initial viewport. A field reveal waits for the mounted task,
focus-driven drawing updates and nested layouts, then uses window coordinates
and stops the scroll effect before positioning the whole input in view. Drafts,
record-specific reading context and drawing-to-dimension navigation are retained.

An open clearance inspector adds Return to review beside the Simulation heading.
After inspecting a source motion, an operator can choose Simulation and return
directly to the captured explanation without searching through the long report.
Closing the review removes this contextual control. Source, current-input and
owner guards remain in place; these actions do not send controller commands.
DESKTOP322 package/install/native acceptance remains OPEN until independent
receipts exercise this source.

DESKTOP321's contact-localization checkpoint is independently CLOSED at source
`739437ebf5db5b2b402d51c373cbc83fa78b810b`: 568 exact source files, strict
signature and immutable first helper in 1.310 seconds; recovery320 retained.
Installed first contact selected line 9 at 49.75%, and the displayed pose agreed
with the captured tip and saved work offset. The retained inspector, preview
closure and test-only record cleanup were independently checked. Seven operator
JSON files remained byte-identical; fresh complete telemetry was Idle/RPM-zero.
Receipts: `/Users/wes/.codex/artifacts/carvera-desktop321-20261009/`.
Full-controller, hosted CI, measured camera registration, sustained camera
reliability and physical qualification remain OPEN.

## Continuous milling contact localization — 2026-10-09

Ordinary fixed +Z milling sweeps now retain an analytic entry/exit interval for
contact between a translating cylindrical assembly section and an obstacle box.
Axial overlap restricts time before rectangle-edge crossings split radial distance
into bounded quadratic pieces. This finds contacts between clear endpoint poses,
including tangent/endpoint contact, without temporal sampling. Subtracting the
start position before root arithmetic preserves translated-coordinate behavior;
the same bounded millimetre domain as the convex solver is enforced.

Collision captures retain the earliest assembly band and program tip. Ordered
remaining-stock checks examine every relevant occupied box until a start-contact
witness proves no earlier hit is possible; box iteration order cannot substitute
for earliest contact. Cancellation retains preceding completed stock. Simulation
maps piece fractions back to their source-line ratios, including subdivided arcs.
Clearance traces prefer the earliest contact among equal zero-distance witnesses.

The linked review explains the source ratio, tip and captured section and adds
First contact in preview. It reuses exact-byte CAD/current-input/owner guards before
seeking. Changing definitions or replacing the inspector cannot apply stale
navigation. Source motion inspection remains available when contact time is
unresolved; fixed tilted axes retain their bounded-distance candidate rather than
inventing a first-contact position. Physical exposure timing, measured contact and
CAD surface registration are not supplied by nominal source-line ratios.

All 190 focused continuous-clearance/stock/capture/grouping and rendered inspector,
plot and asynchronous-navigation tests pass. The independent pose oracle covers
150 random trajectories, plus analytic round-corner, axial, tangent, reversed,
translated, multiple-band and unordered stock cases. An existing cancellation
fixture left its injected copy callback installed during final snapshot readback;
the original snapshot/copy methods were independently confirmed unchanged and the
fixture now restores the real copy method before its unchanged equality assertion.
Strict geometry-model checking, package and machine typing, checked bodies in
both touched UI modules, architecture and locked lint/format pass separately.
Explicit cause/point collections and optional scale values now retain their type
contracts; a detached interval cannot be selected after its report is cleared. Package/install/native acceptance for
this new workflow remains OPEN until independent DESKTOP321 receipts exist.
Requirements 15, 16 and the full original/supplementary scope remain OPEN for
changing orientation, narrow-phase fixture surfaces, complete moving machine
structures, qualified geometry and physical execution.

DESKTOP320's coaxial-transfer checkpoint is independently CLOSED at source
`6e914eb1cc4ac299be3dbc0bb18d24a0f2154371`: 567 exact packaged source files,
strict signature, first helper 1.008 seconds, recovery319 retained, native dimension
entry, blocked grip/source ownership, first-contact navigation and retained pose
exercised. The accepted example was restored and its native export matched all
4482 exact bytes. Seven operator JSON records stayed byte-identical and complete
fresh telemetry reported Idle/RPM-zero. Independent receipts are under
`/Users/wes/.codex/artifacts/carvera-desktop320-20261009/`.

## Continuous coaxial stock/chuck transfer geometry — 2026-10-09

Machine → Channels now admits optional geometry bound to individual grip steps.
Each declaration specifies stock axial limits/diameter, a fixed source chuck face,
receiver start/target faces, and opposing annular chuck bodies with blind bores.
Its declared translation axis joins the grip's implicit resource reservations;
concurrent channel use of that axis blocks both reservations.
Explicit positive dimensions and bounded signed Z coordinates are revalidated at
review. Existing schema-1 plans remain loadable; plans without geometry retain
their symbolic status and do not gain a geometric qualification claim.

Analytic axial/radial interval intersections check every pose of the linear
coaxial approach, including contact between clear endpoint poses. They retain
first-contact fraction, nominal time, receiver Z and contacting declared solids.
Nested annuli avoid an invented face collision but still check blind ends.
Source and receiving engagement come from the stock/bore intersections; source
minimum grip and receiver requested grip remain independent. Contact or inadequate
engagement blocks the grip, preserves ownership and blocks dependent actions.
The clearance allowance expands each axial/radial interval independently; it is
a conservative dimensional allowance, not a Euclidean CAD distance calculation.

The linked workbench has a true-proportion cross-section, approach slider, Start
and First contact controls. Dimensions live in a separate collapsed disclosure;
fractional/invalid drafts and pose survive step navigation at the same review.
Adding dimensions creates an explicitly nominal draft. Applying validates the
complete captured plan and reviews it on the existing bounded worker; obsolete
review owners cannot install edits. Source changes hide prior actionable geometry.
Exact-byte plan load/save retains geometry within the same 256-KiB admission limit.

Local source and rendered checks cover contact, engagement, coordinate translation,
stationary poses, schedule propagation, draft retention, dimension edits and
compact visual layouts. Source/package/installed and physical gates remain separate.
All 100 focused geometry/schedule/file-exchange and rendered planner checks pass.
Package typing covers 252 files, strict machine typing 119, checked new UI bodies
two modules, both architecture contracts, and locked lint/674-file formatting.
The new installed transfer workflow remains OPEN pending its own receipts. Coaxial
solids do not supply jaw/encoder phase, noncoaxial CAD/tool clearance, compliance,
actual grip state or an executable multi-channel adapter. Requirements 15, 23, 24
and the full original/supplementary overhaul remain OPEN.

The preceding DESKTOP319 profile-task checkpoint is independently CLOSED at
`80607f818ec281dbee2928510815832069601d34`: 565 exact packaged source files,
deep strict signature, first helper 1.452 seconds, installed draft/task/picker/ATC
selector exercise, reverted temporary drafts, seven byte-identical operator JSON
records, and fresh complete Idle/RPM-zero telemetry. Runtime receipts are under
`/Users/wes/.codex/artifacts/carvera-desktop319-20261009/`.

## Retained machine, cutter and toolset editor tasks — 2026-10-09

The profile library separates machine Identity, Connection, Scene and Workholding,
cutter Geometry, Assets and Catalog, and toolset Slots. Only the active task body
participates in layout and keyboard traversal. Each record retains its task and
reading positions; raw fractional and invalid drafts remain independent of saved
metadata. Save carries the task context to the saved identity, including a newly
created profile. Replacing an editor disposes its old task owner and pending
restoration; workspace disposal releases the retained library owner.

Save/Use remain pinned. Short editors move heading, description, nominal cutter
drawing and draft status into the active scrolling body and condense its border
spacing. Task navigation becomes a dropdown when captions do not fit. Duplicate
fixed summaries are omitted from the library. Cutter asset and catalog tasks hide
the geometry drawing without recreating it. Visible dimension selection focuses
and reveals the associated geometry input; an inactive drawing cannot dispatch
an obsolete dimension selection. Programmatic field reveal mounts the required task before deferring focus, so a
hidden quantity input never becomes the keyboard owner.

All 68 focused profile, task/history, async loading, keyboard focus and shared
scroll regressions pass; a separate new-identity save check carries Catalog to the
saved cutter without loading it. Package typing covers 250 files, strict machine
typing covers 118, and both architecture contracts and locked lint/format pass.
Source regressions, packaged identity, installed task interaction and physical
qualification are separate gates. The DESKTOP319 installed workflow remains OPEN
until its independent native receipts exist. The full controller overhaul remains
active. Native318 wheel traces show different requested screenshot targets arriving
at identical raw and transformed coordinates before pane hit testing; this is not
proof of an application routing defect or physical mouse/trackpad qualification.

The prior Scene checkpoint is CLOSED at source
`992885f76041843552d671d6946e664a6e3a011a`: DESKTOP318 has 565 exact packaged
source files, strict signature, immutable first helper 3.048 seconds, installed
four-task interaction, picked-face/candidate retention and Back/Forward workflow.
Seven operator JSON records remained byte-identical; complete native telemetry
reported Idle and RPM zero. Runtime receipts are under
`/Users/wes/.codex/artifacts/carvera-desktop318-20261009/`.

## Retained Scene tasks and linked picking — 2026-10-09

Scene now has four retained workbench tasks: Components, Placement, Inspect and
View. Only one task body participates in layout. Components holds cutter, fixture,
vise and stock selectors; Placement holds coordinate-chain and setup actions with
gesture snapping; Inspect holds selected geometry, tool drawings, related
components, picked-face measurement and dimensioned sections; View holds framing,
component visibility, isolation and separation. The interaction mode stays
available above the tasks. Navigation changes neither saved scene metadata nor
physical machine state.

A rendered pick routes to Inspect while retaining the exact selected face and
candidate list. Linked component actions create one history arrival. Back/Forward
restores the component, task and its own reading position, validates task/scroll
metadata before changing the page or view, and rejects a superseded restoration.
Pending picks and framing reject a changed task generation; placement gestures
reject changed tasks or workbench pages before opening a draft. Section, snap and
component field drafts retain their widget identities when their task is hidden;
outgoing keyboard owners and their menus release focus.

Rendered qualification covers all four tasks in a compact dropdown layout,
unchanged fractional-unit drafts, one mounted body, linked selection, exact
reading-position restoration and stale-context rejection. The source/package,
installed workflow and physical qualification gates remain separate. Installed
Scene-task qualification remains OPEN until a new package and its own native
receipts exist. Full original and supplementary requirements remain active.

The prior DESKTOP317 dialog checkpoint is independently closed at source
`d25b76b64406986e30bf182757efa011f736d6aa`: 565 exact packaged files, strict
signature, first helper 3.464 seconds, installed stock/surface/batch interactions,
seven byte-identical operator JSON records and fresh complete Idle/RPM-zero
telemetry. Its nominal UI qualification feature was preserved separately, with no
samples retained and the prior absent active store restored. Runtime receipts are
under `/Users/wes/.codex/artifacts/carvera-desktop317-20261009/`; these do not prove
physical inspection or the newer Scene-task workflow.

## Consistent stock and inspection dialog scrolling — 2026-10-09

Stock-profile planning, nominal surface measurement and batch measurement entry
now use the shared desktop scroll surface. These were the remaining explicit raw
Kivy scroll constructors in the modern desktop forms; base-class imports used
only for ancestor discovery remain unchanged. Surface measurement also disables
horizontal scrolling so a narrow form wraps into its available width.

Three pointer regressions reproduced latent scroll-position changes in all three
forms before migration. They now pass, together with 46 surrounding scroll,
keyboard, surface-inspection, receipt-table and facing-planning checks (49 total).
The rendered cases focus a field while the form fits, expand a report beyond the
viewport, narrow the dialog, then reveal the unchanged draft. Batch records remain
byte-identical and no controller commands are sent. This verifies desktop layout
and focus behavior, not nominal CAD measurement accuracy or physical probing.

The source checks are separate from the next package/install/native qualification
gate, which remains OPEN until its receipts exist. DESKTOP316 independently
closed the earlier shared scroll-component regression at source
`a2e35555bbfab233d0febaa6fef6b5ec0958e4ce`: 565 packaged files and strict signature,
first helper 2.820 seconds, actual pointer Load DEMO/edit/apply anchoring and
Scene-to-Machine draft retention. Its scoped runtime receipts live in
`/Users/wes/.codex/artifacts/carvera-desktop316-20261009/`. The full original and
supplementary requirement ledgers remain active.

## Pointer focus and asynchronous report scroll position — 2026-10-09

The installed Channels workflow exposed a shared desktop scrolling defect:
focusing a control in content that fits the viewport changed its latent vertical
position from top to bottom. Expanding an asynchronous review then exposed the
bottom position as a large jump. Direct method calls did not reproduce it; an
actual pointer event on a fitting draft did. The failed rendered regression is
retained in `/private/tmp/carvera-scroll-anchor-fitting-reproduction-20261009.log`.

`DesktopScrollView` now returns zero scroll distance on an axis with no overflow
or with scrolling disabled. Controls already in view retain their position;
overflowing content still uses the actual pixel-to-scroll conversion. The shared
fix applies to workbench tasks and desktop dialogs, without special-casing the
Channels page or retaining an actionable stale review.

All 46 focused scroll, channel-plan, task-navigation, keyboard-focus and motion
study regressions pass. They include real pointer input, the fitting-draft to
scrolling-report transition, applying a step edit while retaining the button's
reading position, nested wheel boundary bubbling, both scrollbar axes, task
position retention and focus/jog exclusion. Source typing/lint/format and exact
package/install/native qualification are separately recorded; the latter gates
remain OPEN until their receipts are obtained. The prior DESKTOP315 file-workflow
checkpoint remains closed. Full controller ergonomics, large-CAD latency and the
broader original 25 requirements remain OPEN.

## Persistent channel-plan exchange — 2026-10-09

Machine → Channels now loads and saves schema-1 plan files through the shared
artifact browser. Files retain the exact admitted UTF-8 bytes within the same
256-KiB budget, with path, byte count, SHA-256 and UTC observation receipts.
Loaded files are validated and reviewed off the UI thread and read twice to detect
byte changes during review, including same-size/same-timestamp replacements. A
rejected, changed, cancelled or closed-owner import retains the current draft,
selection and review; accepted declared conflicts remain visible as review issues.
No imported plan changes the program, scene or connected controller.

Export captures the reviewed draft and writes/flushes/verifies a same-volume
prepared file on its worker. The UI grants publication only if the draft generation,
source text, review and owner are still current. Atomic hard-link creation publishes
a complete new file without overwriting a competing destination. Unsupported
filesystems fail without partial destination bytes; there is no overwrite fallback.
Exact destination readback supplies the export receipt. Cancel remains available
until that final checked decision and is then disabled while publication completes.
Prepared files are cleaned up on success, rejection, cancellation and creation failure.
External changes after byte observations are not excluded by a filesystem lock.

One file worker remains owned until it returns, even if its popup is cancelled
while an OS read is blocked. Replacement clicks cannot accumulate blocked readers.
Source edits invalidate obsolete transactions, worker-start failures are retryable,
and stale delivery does not install captured reviews. The modal grows with its
receipt within the window bounds. Seven retained operator JSON files are outside
this exchange; existing destination files are preserved.

All80 focused exchange/schedule/filesystem tests pass. All34 rendered exchange/browser/task-navigation cases pass, including
real artifact-browser save/load, exact round-trip receipts, changed/cancelled/closed
owners, latest draft preservation, publication-phase dismissal suppression, worker
startup retry, background-frame availability and compact pane reflow. Source typing
covers250 files, strict machine typing118, checked UI-worker bodies, both architecture
contracts and locked Ruff lint/664-file formatting. The new file workflow's package
and installed native gates remain OPEN until separate receipts exist.

The prior independently installed Channels checkpoint is DESKTOP314 at3fd2eea,
with563 exact-source files, strict signature, immutable first helper2.656 seconds,
DEMO/timeline/cutoff transfer details/2→3-second edit/retained navigation exercised,
and unchanged operator JSON hashes. Its consolidated receipt is
`/Users/wes/.codex/artifacts/carvera-desktop314-20261009/checkpoint.json`.
Requirements24, geometric chuck/stock clearance, measured grip/encoder phase,
real advanced-machine execution, camera registration/synchronization and full25
remain OPEN; file interchange does not close those independent requirements.

## Declared channel and transfer planning — 2026-10-09

Machine → Channels adds a local nominal-time timeline, recycled selectable step
list and before/after workpiece ownership, datum, remnant, spindle RPM and
synchronization inspection. Selected-step drafts edit duration, explicit dependencies
and extra resource reservations; full schema-1 JSON accepts all declared actions and
reviewed JSON can be copied. Command search and the capability inspector route here.
The current Carvera adapter explicitly has no multi-channel execution implementation.

Per-channel order and explicit dependencies form a checked graph. Synchronization
barriers require exactly one arrival from every named channel, share the latest
arrival time, and reject cycles or dependencies within their own cohort. Interval
checks include explicit axes/turrets/live-tool resources and implicit spindle,
peer-spindle and workpiece reservations. Conflicts block the affected actions and
propagate through dependencies and whole barrier cohorts; adjacent intervals can
share a resource. The nominal example overlaps tooling preparation with front work,
then transfers with declared overlap/grip, synchronized cutoff, stopped pair, new
back-face datum and live-tool milling in 24.5 seconds.

State checks reject unsupported release, attached-source release, rotating co-grip
without a synchronization declaration, insufficient grip or overlap, cutoff without
both holders and a reserved cutting turret, and work without a valid datum or drive
reservation. Ownership changes invalidate datums. End events preserve concurrent
changes to independent pieces. These are symbolic declarations: no geometric
clearance, measured chuck condition, actual encoder phase, qualified execution or
physical workholding is established. No program, scene, offset or transport changes.

One review worker and one replaceable pending snapshot keep review work bounded.
Draft edits cancel obsolete results, closed owners ignore delivery, and worker launch
failures permit retry. The selected step survives an applied edit; obsolete recycled
rows cannot route into a newer review. Navigation retains local drafts. Requirements
24 in both this ledger and the specialized-machining ledger remain OPEN for geometric
transfer rehearsal, real machine adapters, installed file interchange and physical
qualification. All112 focused schedule/capability/joint/indexed tests and32 rendered channel,
capability, kinematics and navigation cases pass. Package typing covers248 files;
strict machine typing covers117, both architecture contracts pass, and locked
Ruff lint/661-file formatting pass. Initial fixture and tool-path diagnostics
remain retained. Maximum-size admitted declarations export within the same256-KiB load budget,
using compact JSON when indentation would exceed it. The uninstalled DESKTOP312
candidates312 at1043897 and313 at7a1bd04 were superseded after near-limit
and exact-limit studies; logs and scratch remain retained. Copy preserves the
exact admitted source, and structured edits omit redundant defaults and normalize
integer-valued dimensions to stay within the interchange budget. Source checks and installed workflow evidence are separate gates.

## Explained spindle decisions — 2026-10-08

The spindle workbench has a Decision section beside Signal, Diagnostics and
Baseline, also reachable from command search. It shows the current shadow proposal,
the limiting policy factor, raw and filtered baseline-relative RPM droop, drive
effort (including unavailable PWM), reported feed override and remaining policy
dwell. The monitor and inspector share the same experimental thresholds and bounds;
explaining a decision never advances its filter, timer or proposal.

A bounded response comparison finds the latest reported override change within five
seconds of continuous cutting telemetry and shows before/current RPM and feed,
arrival association and elapsed time. It labels collection versus observation and
explicitly does not attribute a response to a shadow proposal. Interrupted motion,
stopped feed, spindle-command changes, discontinuous arrivals and expired windows
exclude earlier comparisons. Off, baseline capture, missing baseline, stale/future
complete arrivals and latched faults suppress current proposals and comparisons.
Disconnected UI keeps measurements labeled as retained. Complete-sample machine
coordinates are available; executed source line/operation and camera exposure
association remain unverified. Firmware sample age and command-response latency
remain unavailable rather than inferred from desktop arrival age.

The structured explanation is included in existing telemetry records and diagnostics
without a transport action. All 92 focused policy/decision/quality/recording tests
and 68 rendered monitor/diagnostics/workspace tests pass. Package typing covers
246 files, strict machine-layer typing covers116, both architecture contracts pass,
and locked Ruff lint/657-file formatting pass. Initial type-tool/fixture failures
remain retained outside source. Requirement17 is advanced but remains OPEN for
executed-motion association and qualified adaptive backend/physical response.

The independently installed Decision checkpoint is DESKTOP311 at0e97c47, with
561 exact-source files, strict signature and an immutable first helper observation
of2.378 seconds. Native Decision/fault suppression, scrolling, diagnostics navigation
and structured recording were exercised; seven operator records retained exact
hashes. The consolidated receipt is
`/Users/wes/.codex/artifacts/carvera-desktop311-20261008/checkpoint.json`.
The newer Channels source is excluded from311. Active-cutting native scenarios,
physical qualification and full25 completion remain OPEN.

## Background clearance navigation — 2026-10-08

Selecting a clearance interval, revealing its source and seeking its preview now
verify exact CAD bytes on a shared background reader. Captured geometry inspection
opens immediately without disk reads; it explains that loaded definitions match
and CAD is checked before current-path navigation. Its Show motion action uses the
same checked worker. A compact status and Cancel check action retain access to the
captured results while the read is in flight.

Only one reader runs at a time, with one replaceable pending request. Repeated
selection cancels the active observation and replaces the pending request rather
than launching a worker for every gesture. Delivery checks the numerical definition
identity, clearance baseline/context, captured simulation and plot report objects,
and exact selected point or inspector ownership. Cancel, closed inspection,
changed setup/baseline/report/selection and queued obsolete delivery do not seek or
retarget the current source. Same-size/same-timestamp replacements and unreadable
CAD invalidate current-path actions while retaining captured reports. Constructor
and start failures restore controls and report a local error; a later explicit
selection can retry. Byte observation is not an external file lock. OS-blocked
reads must return before that one reader can start its pending replacement.

All 192 rendered navigation/plot/inspection/change-review/simulation/launch/stock-
transfer/workspace cases pass, including 42 focused navigation cases. Tests pause
real asset hashing on the worker while UI frames and Cancel remain available,
exercise a 51-request burst with two reader invocations, and check cancellation
or owner/input changes after verification but before queued delivery. Package
typing covers 244 files; checked navigation-worker bodies, lint and 640-file
formatting pass. Initial fixture diagnostics remain retained.

Source and installed qualification remain separate. DESKTOP310 at27a059b has
independent559-file/signature proof and bounded native synthetic clearance selection,
Show motion, source details and geometry inspection. Seven operator JSON files were
restored and independently checked after restart; final Live/Idle camera/telemetry
readback was fresh. Receipts are retained in the DESKTOP310 artifact checkpoint.
Requirement1, large CAD native navigation, measured camera registration/synchronization,
backend/physical qualification and the full25 remain OPEN.

## Cancellable residual-stock exchange — 2026-10-08

Rest-stock import/export now opens an owned transfer dialog while exact CAD
verification, snapshot compression/decompression, integrity validation and
viewport preparation run on background workers. Cancel remains available during
preparation. The worker captures detached program/setup/tool/workholding inputs
and the residual baseline; the UI rejects changed inputs or baseline before
publication. CAD verification reads exact bytes twice and detects same-size,
same-timestamp replacements. No stat-only proxy replaces the byte identity.

Export prepares a bounded snapshot in a same-directory temporary file, flushes
it and checks the destination's observed bytes before the UI grants its final
commit decision. Atomic replacement runs on the worker. Cancellation, changed
inputs, changed destination, launch failure and replacement failure retain the
prior file and residual result; prepared files are cleaned up. The destination
observations are not an external file lock. Cancel is disabled after the checked
commit decision. Import retains prior stock/display on rejection and invalidates
old clearance results when new residual stock is accepted. Malformed stock must
leave Close available rather than strand a running transfer.

The occupancy format remains compatible and compressed bytes match the previous
encoding. Cancellation checks bound copying, compression, decompression and
validation independently of compressed size. Snapshot input remains limited to
16 MiB and occupancy to eight million cells; OS-blocked reads/fsync/replacement,
JSON/base64 work and final GPU publication remain finite limitations.

The earlier final-CAD acceptance change exposed a regression when cancellation
occurred only during stock viewport preparation. Completed calculation results
are retained again; a second Cancel during final acceptance still abandons the
new result. These semantics have separate controlled rendered coverage.

All137 rendered transfer/change-review/simulation/launch/workspace cases pass;
all93 stock/simulation/snapshot model cases pass. Coverage includes worker hashing
with UI frames and Cancel, stale baseline/setup, same-size/timestamp CAD changes,
missing CAD, changed destinations, malformed stock, launch/replacement failures,
and checked queued publication/delivery. Package243 typing, checked transfer-worker
bodies, lint and638-file formatting pass. The isolated scene-switch timeout,
invalid-fixture attempt, killed follow-up process and process sample are retained;
the final full rendered run completed in153seconds.

Source verification and installed native transfer acceptance are separate gates.
DESKTOP308 at3849906 already has bounded native simulation/change-review evidence,
557 independently matched package files, a strict signature and restored operator
records. The new transfer implementation is excluded from that installed package.
Requirement1, other geometry-navigation/file workflows, backend/physical
qualification and the full25 remain OPEN.

## Background exact-byte change review and result acceptance — 2026-10-08

Geometry change review opens immediately with its Close action available while a
worker verifies exact CAD bytes and computes changed definitions and affected
operations. Dismissal cancels bounded reads and prevents late publication. The
review captures detached numerical definitions and its residual/clearance
baseline; changed selection or baseline rejects delivery. Hashing still detects
same-path, same-size replacements with preserved timestamps. Current definitions
are compared on the UI without reading files. Prior results are not overwritten
by a stale, cancelled or failed request. Launch failures retain Close and an owned
diagnostic. All review entries remain available in12-row pages, so a large
operation set does not allocate a widget for every operation at once.

Simulation and clearance results now perform their final exact-byte recheck on
the calculation worker before applying results. The UI checks only the captured
program/setup/tool definition identity. Cancel stays available during acceptance;
changed or unreadable CAD bytes, changed selected definitions and cancelled
acceptance retain the previous report, residual stock, context, display and
snapshot status. The existing explicitly cancelled partial stock result remains
eligible for exact-byte acceptance; a second Cancel during that verification
abandons it. Verification observes bytes at its worker read, not an atomic lock
on externally editable files. No timestamp/stat proxy replaces the byte hash.

Context capture now copies mutable stock, offset and workholding coordinates;
editing a list in place cannot silently modify a worker's captured request or
its previous-result baseline. OS-blocked reads, final comparison/row-model
construction and GPU publication remain finite runtime limitations. Other
snapshot import/export and geometry-navigation workflows still perform UI work.
Requirement1 and the full25 remain OPEN; installed acceptance of this source is
tracked separately from source tests.

All87 rendered review/simulation/clearance/remedy cases and101 context/snapshot/
stock/clearance model cases pass. Cases pause actual CAD hashing off the UI,
process UI frames and Close/Cancel, reject changed baseline/selection and missing
or same-size/timestamp-replaced CAD, retain previous results during acceptance,
exercise partial-result verification and a second Cancel, reject cancellation
before queued delivery and navigate every one of100 affected operations in bounded
pages. Package242 typing, strict context typing, checked review-worker method
bodies and lint/format pass. Retained diagnostics include the previous synchronous
review call, an empty invocation with a wrong test filename, untyped-result
inference errors and a test assertion that conflated review publication with the
independent telemetry input invalidator; corrected tests isolate that ownership.

DESKTOP307 atdb7c96a is independently installed and scoped native-qualified:
556 files match, strict signature passes and the immutable first helper completed
in1.301seconds. Synthetic cutter inspection closed from its last-observed
Preparing view, reopened to render, and responded to orbit/zoom. The exact worker
phase at the native Close gesture is unknown; controlled rendered tests separately
prove interruption during mesh packing. STEP picking reached the corrected
registration form and Cancel retained the prior unsaved draft without conversion.
Seven saved operator JSON files remain byte-identical; config changed only
version306to307. Post-workflow source/signature checks pass. Restart recovered
after an automation observation timeout; final Live/Idle/0RPM/0feed/no-program
readback had camera1.8s and telemetry0.22s. Recovery306 remains preserved. Native
receipt: local carvera-desktop307-20261008/native-workflow-verification.json.
This new change-review source is excluded from that installed package.

## Cancellation reaches cutter CAD packing — 2026-10-08

Close now passes the inspection cancellation event through cutter and holder
asset preparation. Reads and gzip expansion check between64KiB chunks;
coordinate validation checks every128 values, and clipping/normal/vertex packing
checks every128 triangles. Cancellation before the holder stage avoids opening
its file. Cancelled work returns no partial asset or mesh. Completed CAD geometry,
clipping, holder positioning, byte digests, schema and limits remain identical.
The tip minimum is found during validation without another full coordinate slice.
Hashing, JSON decoding, byte joins, blocked OS calls, procedural profile building
and final GPU publication remain finite uninterruptible steps. This closes a
specific preparation gap, not requirement1 or the full25.

All243 tool/CAD/assembly/identity/snapshot/projection model cases and36 rendered
inspector/conversion/default-profile cases pass. A real mesh-packing callback is
paused on the worker; UI frames and popup Close remain available, dismissal sets
cancellation, packing raises InterruptedError and publishes neither vertices nor
a controller command. Controls cover complete compressed/plain/clipped/holder
geometry equivalence, early read/expansion/decode/validation cancellation,
unchanged digest/invalid-coordinate/encoded/expanded-size rejection, and
cancel-before-holder-open. Package241 and strict three-module typing, lint and
format pass. The prior exact-source read helper lacks the cancellation parameter;
its retained failing diagnostic demonstrates the missing contract. One test
invocation named a nonexistent test file and ran no cases; its corrected full
invocation is retained separately. This source follows installed306 and remains
excluded from that package until the next exact-source native qualification.

DESKTOP306 source48eb1d5 is independently verified and installed:556 files match,
strict signature passes and the immutable first helper completed in2.315seconds.
Native synthetic20,000-triangle inspection opened and responded to orbit, zoom,
fit, nominal drawing and Close. The2441ms click/readback includes automation
and does not benchmark event-handler latency or independently count triangles.
The CAD registration dialog keeps filename/title separate and fields/actions
visible; Cancel retained the draft without conversion. Seven operator JSON files
remain byte-identical; config changed only version305to306. Bundle/signature
reverification passes. A camera request timeout recovered without reconfiguration;
restart briefly displayed an autonomous connection retry and then recovered.
Final Live/Idle/0RPM/0feed/no-program/no-remote-file readback had camera age1.0s
and telemetry age0.38s. Recovery305 is retained. Native evidence is local
carvera-desktop306-20261008/native-workflow-verification.json. PR27's independent
head/body readback matches48eb1d5; hosted exact-head CI and integration remain OPEN.

## Responsive full cutter inspection and CAD registration layout — 2026-10-08

Opening cutter inspection now detaches its definition and prepares the complete
cutter/holder mesh and bounds on a worker. Orbit, zoom and viewport projection,
lighting and triangle ordering also prepare off the UI thread. One projection
runs at a time with one replaceable pending view. Obsolete requests interrupt
bounded traversal; delivery checks generation and the current viewport/pose.
Closing cancels pending work and rejects late geometry or projection publication.
The previous rendered view remains visible while its replacement prepares.
Launch failures restore idle state with an owned diagnostic and no automatic
retry. CAD errors remain visible; the nominal drawing stays available separately.
No triangles are removed or sampled for responsiveness.

CAD registration now uses a scrolling form with a persistent Convert/Cancel bar
inside a proportional dialog. The previous fixed-height form overflowed its
content area, overlapping the filename with the title. Narrow and ordinary
viewport checks retain accessible actions without reducing the captured request.

Rendered coverage processes UI frames during paused geometry preparation and
projection, exercises Close, coalesced orbit/resize, late success rejection,
eight construction/start faults, missing CAD and nominal drawing recovery.
A 20,000-triangle synthetic CAD case retains all60,000 vertices and verifies
worker ownership, valid rendering and no machine command. Projection model cases
check complete framing/normals/colors and bounded cancellation. Initial regression
proved mesh preparation ran on the UI thread; a placeholder Mesh without its
required format failed and was repaired. A resize test initially requested child
bounds overridden by parent layout; it now verifies the actual resized viewport.
These failed attempts remain retained. All35 rendered inspector/conversion/default-profile
cases and32 projection/converter/asset model cases pass, as do package241 and
strict worker typing, lint and formatting. Source and installed qualification for
this newer inspector increment are tracked separately; full requirement1 remains
OPEN because mesh-builder/OS reads and GPU publication are finite uninterruptible
steps, and other scene/context acceptance workflows still perform UI work.

DESKTOP305 at99db682 independently passed555-file source/signature validation,
its immutable first helper1.177seconds and recovery-preserving installation.
Native synthetic STEP import and cutter preview succeeded; Cancel stopped the
observed converter child and preserved the earlier unsaved asset. Post-conversion
source/signature verification passed again. Seven tracked operator JSON files
remained byte-identical and normal CAD interpreter preference was restored,
retaining only the expected installed-version update. Final live Idle/0RPM/0feed
and fresh camera/telemetry readback passed with no program or remote file selected.
This closes the previously open installed import and signature gates for305,
not actual Titan geometry, physical simulation, this newer inspector source or
the full25. Receipts are in the local carvera-desktop305-20261008 directory.

## Cancellable tool-CAD conversion — 2026-10-08

Convert & inspect now retains Cancel while the selected CAD Python interpreter
runs. Registration fields stay locked to the captured request. Cancel requests
child termination, escalating to kill after two seconds, with a second bounded
exit wait. Dismissing the dialog also requests cancellation; late successful
completion never applies a tool asset. Completed conversion still validates the
bounded data-only mesh before invoking the existing import callback. Worker
construction/start and preference-write failures restore the controls with owned
diagnostics and no automatic retry or asset publication. Child output is discarded
rather than collecting unbounded interpreter output or exposing it in the UI.
An isolated-interpreter test also exposed missing controller imports in the
standalone converter. Its data validator now resolves the package root beside
the converter script, supporting a selected CAD interpreter without an installed
controller or inherited development PYTHONPATH; CAD-file directories are excluded.

All26 converter/asset model cases and19 rendered conversion/default-profile cases
pass. Real process tests cover OBJ registration, cancellation/reaping, an ignored
termination signal, timeout, invalid geometry and cancellation during validation.
Rendered cases process UI frames while work is paused and cover Cancel, dismissal,
late successful completion, exactly-once acceptance and launch/write failures.
Package240 and the new worker's strict typing pass; lint/format checks pass. The
initial real-conversion fixture omitted required units/axis flags; its failed log
is retained, as is the genuine isolated-interpreter import failure. Successful
OBJ conversion now runs under Python isolated mode. No machine command is sent
by this workflow.

DESKTOP303 source6e7933d was installed after555-file/signature validation and its
first helper check passed in1.20s. Native Cancel terminated the observed child,
restored the controls and left the unsaved cutter asset unchanged. Seven operator
JSON files remained byte-identical; the CAD interpreter preference was restored,
with the expected installed-version update retained. Native STEP import exposed
a separate packaging defect: the frozen module's virtual converter.pyc path was
passed to the external interpreter, although only converter.py is shipped.
The converter script resolver now selects and checks that source file. Regression
cases cover the missing virtual bytecode path and macOS Frameworks/Resources
symlink. This fix is excluded from DESKTOP303; corrected installed import remains
OPEN. Direct conversion of a synthetic STEP cylinder succeeded independently.
DESKTOP304 source5260626 passed555-file source/signature validation and its first
helper check in1.27s, but installation stopped before mutation: the direct303
diagnostic had added three Python3.12 bytecode caches to signed resources. Those
caches were moved to forensic storage and the original303 source/signature was
independently restored without re-signing. The standalone converter now disables
bytecode writing before loading its validator. A regression explicitly enables
writing before execution and confirms that all shipped package bytes remain
unchanged. The failing cache-writing case is retained. DESKTOP304 is superseded
and uninstalled; corrected installed import and post-conversion signature remain
OPEN until the next exact-source package is qualified.
Asset validation and OS-blocked filesystem reads cannot be interrupted
until they return; an OS refusal to reap the killed child is reported rather than
treated as confirmed exit. Requirement1 and the full25 remain OPEN.

## Cancellable workholding snapshot validation — 2026-10-08

Workholding preparation now passes Cancel through the resulting immutable CAD
snapshot. Mutable vertices and indices copy in1280-value chunks; indexed bounds
validate every128 entries, including repeated indices, without an initial full
set conversion. Interrupted snapshots never enter the placement cache. Previously
cached placements remain available, and complete snapshots retain their bounds,
copy/pickle semantics and immutable data. Placement callers keep their existing
cancellation diagnostic. The redundant full index list is no longer allocated
before snapshot construction.

All133 snapshot/profile/render/inspection/simulation model cases and24 rendered
simulation preparation/recovery cases pass. The rendered case pauses actual
snapshot bounds validation on the calculation worker, processes UI frames and
Cancel, and verifies previous report/stock/context/display and export status are
preserved without simulation publication or a machine command. Package240 and
strict114 typing, lint/format checks pass. Initial fixture-format and stale test
context failures are retained; the fixture now includes required motion groups
and captures its baseline after placement selection.

This source follows installed DESKTOP300 and is excluded from that build. Native
cancellation and latency remain OPEN. Tuple finalization and short cache locks
remain noninterruptible runtime operations; final exact-byte acceptance and
context capture still perform UI work. Requirement1 and the full25 remain OPEN.

## Pasted import paths — 2026-10-08

Import dialogs now accept an absolute or ~/ path in their filename field, with
matching hints and an explicit path label. The selected file still passes the
background filesystem check, suffix validation and changed-selection guard.
Relative traversal remains rejected. Save dialogs retain their current-folder
and no-overwrite semantics. This addresses an installed299 interaction where a
pasted valid full path produced a misleading extension error.

All17 rendered picker cases and package240 typing pass, with lint/format checks.
Coverage includes paths containing spaces and uppercase suffixes, home expansion,
missing files, invalid suffixes, relative traversal and existing save protection.
This follow-on source is excluded from frozen DESKTOP300 (92adec4); native path
interaction remains OPEN. The installed299 synthetic simulation completed and
showed operation/source-line workholding warnings. Cancel was not qualified:
calculation completed before it was reached. After Idle quit, the exact import
merge and own recent entry were checked before restoring original bytes; all seven
tracked operator files match their prior hashes. The full25 remains OPEN.

## Direct stock review and installed preflight — 2026-10-08

The simulation panel's stock placement/work offset action now opens the actual
Stock & program origin editor, containing dimensions, corner and program-origin
fields. It previously only switched to Scene, leaving the relevant editor out of
view. Opening or cancelling this editor leaves active and saved setup unchanged;
repeated activation retains an open draft. All73 rendered setup-editor/clearance
cases and package240 typing pass, with lint/format checks. This source follows
installed DESKTOP299 and is not included in that build.

DESKTOP299 is independently verified and installed from38e524f:554 source files,
no mismatches, strict signature verified and immutable first helper1.214seconds
under the unchanged four-second deadline. DESKTOP298 recovery remains retained.
Native local preview loaded a synthetic2004-line/1002-operation study and showed
the missing-tool prerequisite rather than inventing cutter geometry. Closing the
preview restored no-program Live/Idle. The exact synthetic recent-history addition
was removed with the application closed, and seven tracked operator files match
their prior hashes. This is bounded preflight/navigation proof; loaded-program
calculation cancellation, native latency and the full25 remain OPEN. Receipts:
`carvera-desktop299-20261008/{artifact-verification,native-program-preflight-verification}.json`
under the local artifacts directory. New51a7239 and b17252b remain excluded from299.

## Continuous-clearance CAD preparation — 2026-10-08

Continuous-clearance review now captures declared identities without initial file
reads on the UI thread and verifies detached CAD context on the calculation
worker. Cancel remains available during verification and preserves the prior
clearance review. Same-path changes or missing files invalidate captured inputs
before analysis. The final fresh exact-byte gate remains before plot publication,
rejecting replacements made after verification, including unchanged file size and
timestamp. Existing metadata changes still reject before launching work.

All45 rendered launch/preparation/clearance/remedy cases pass, including four
paused-worker cases: cancellation, changed bytes, missing file and replacement
between verification and publication. They exercise UI frames and Cancel, verify
worker-thread ownership and assert no controller commands or plot publication.
Package240 typing, lint and formatting pass. This source follows frozen DESKTOP298
and is excluded. Native cancellation, full responsiveness and the full25 remain
OPEN; final verification and scene/setup capture still perform UI work.

## Cancellable initial CAD verification — 2026-10-08

Material-removal preparation now captures declared asset identities without file
reads on the UI thread, then verifies a detached context on the calculation
worker. Exact SHA256 reads check cancellation between64KiB chunks and before
publication, retaining the existing24MiB tool and8MiB machine asset limits.
Changed, missing and unversioned assets still reject calculation. Cancellation
preserves previous reports, stock/context, candidates, display and export status.
The final fresh exact-byte identity check remains in place before applying a
result; a same-size, same-timestamp replacement after worker verification is
rejected rather than accepting a metadata proxy.

All72 geometry/assembly/remedy model cases and41 rendered launch/preparation/
clearance/remedy cases pass. The latter include actual background CAD preparation,
UI frame processing, Cancel and the post-verification byte-replacement race.
Package240 and strict114 typing, lint and format pass. An initial mixed-suite
navigation assertion failed; the isolated inspector file and subsequent broader
suite passed. The failed run remains retained without claiming a specific repair.

This source follows frozen DESKTOP298 and is excluded from that candidate.
Requirement1 remains OPEN: final acceptance verification, setup/scene capture and
other explicit review/export actions still perform UI work; an OS-blocked read
cannot be interrupted until that read returns. Installed cancellation and native
large-program latency remain unverified. The full25-item goal stays active.

## Cancellable background stock and collision preparation — 2026-10-08

Initial stock allocation, residual cloning, clearance-baseline cloning and
collision obstacle bounds now prepare on the calculation worker using the captured
setup and scene. Stock allocation/copy checks cancellation between64KiB chunks
and before publishing a complete volume. Collision bounds check every128 vertices
and before scene publication, without materializing a second full point list.
Cancellation discards partial preparation, retains the prior stock/report/display/
candidates/export status and restores controls with the relevant phase named.
Existing model callers without a cancellation callback retain their fast copy path.

Nine allocation/clone model cases cover intermediate and pre-publication exits,
source snapshot preservation and independent successful clone bytes. Three scene
cases cover bounded traversal and pre-publication cancellation without changing
source geometry. Rendered background cases pause allocation, cloning, scene and
motion preparation, process UI frames and dispatch Cancel. Local broader model
suite passes122 cases; package typing passes240 files. Native responsiveness and
full requirement1 remain OPEN: scene capture/generation and explicit setup/asset
verification still occur in preflight. This source follows frozen DESKTOP298 and
is excluded from that candidate.

## Cancellable background motion preparation — 2026-10-08

Material-removal motion selection, source-length accounting and simulation-segment
conversion now run on the calculation worker. Cancel is available while motion is
being prepared. Each traversal checks cancellation every128 entries and checks
again before publishing its tuple; interruption returns no partial input. The UI
shows preparation and calculation phases. A preparation cancellation preserves
the previous report, rest stock/context, candidate panel, display geometry and
export status. Candidate/export clearing is deferred until accepted result
publication. Existing captured-input identity checks still reject older results.
Auxiliary stock/path review now cancels obsolete motion preparation as well.

Seven model cancellation cases cover all three traversals and pre-publication;
rendered cases exercise actual background preparation, UI frame processing and
Cancel while preparation is paused, and obsolete alignment selection without late
delivery. All74 broader model cases and76 rendered simulation/clearance/workspace
cases pass; the final10-case fault/background suite also processes UI frames while
preparation is paused. Strict114 and package240 typing, lint and format pass.
Initial fixture failures are retained: a nonserializable retained-context
placeholder and unrelated periodic selection refresh were corrected. This extends
requirement1, not its completion: setup/geometry capture and stock cloning still
occur during preflight, native large-program latency remains unmeasured, and this
source follows frozen DESKTOP298 (a5221e3), so it is excluded from that candidate.

## Simulation worker launch recovery — 2026-10-08

Material-removal and continuous-clearance calculations now recover when thread
construction or start raises RuntimeError/OSError. The running state clears,
controls restore and an owned message explains that previous results are retained.
Existing report/rest-stock/context, clearance candidates and stock-export status
remain unchanged. The auxiliary stock/path alignment worker also reports launch
failure without preventing the calculation controls from recovering. Candidate clearing and export-status clearing occur only after
a successful launch. Neither calculation is automatically retried and platform
diagnostics are not exposed. Eight rendered fault cases cover both calculations,
both launch stages and both exception classes, including real alignment-worker
launch failure during control refresh; the initial uncaught failure is
retained. The broader rendered simulation/clearance/workspace suite passes74
cases. Local package typing passes240 files; lint/format pass. This advances
requirements1/25; installed fault interaction and full commissioning remain OPEN.

DESKTOP297 is installed from frozen88e0d46 with554 source files independently
matched, strict signature verified and its immutable first helper attempt passing
in3.514 seconds with retained stdin and no file created. Installation independently
reverified source/signature and retained DESKTOP295 recovery. Native Simulation
and Scene navigation and return-to-live are exercised; final readback reports Idle,
no local/remote program, camera age0.7s and telemetry age0.15s. Loaded-program
simulation/cancellation remains unverified. Newer camera navigation, recording
recovery and this simulation recovery source are excluded from DESKTOP297.

## Recording worker launch recovery — 2026-10-08

The recording artifact worker previously set the panel busy before starting its
thread, with no recovery if thread construction/start failed. A regression first
reproduced the uncaught RuntimeError. RuntimeError/OSError during launch now
restore the controls, preserve replay/cursor selection and display a bounded
owned message. No work callback or completion callback runs, no file operation
is retried and platform exception details are withheld from the UI/log message.
All32 rendered recording/playback/workbench cases pass, including the launch
failure, five late camera-search deliveries and existing camera decode/custody
checks. Initial failing proof is retained. This extends failure recovery for
requirements1/25; installed fault interaction and complete commissioning remain
open. The source follows frozen DESKTOP297 and is excluded from that candidate.

## Adjacent recorded-camera navigation — 2026-10-08

Camera replay now groups First/Previous/Next/Last image actions together. Previous
and Next select the nearest retained status associated with a different camera
receipt, skipping repeated status-to-image associations, telemetry gaps and
unassociated events. Distinct receipt identity is preserved even when JPEG assets
are identical. Navigation never wraps at an end; a missing target preserves the
current selection and explains why. Session mismatch and busy state also preserve
selection. Metadata navigation performs no image I/O or machine commands.

A successful navigation enables recorded viewing before moving the cursor, so
its existing callback issues one image read/decode rather than a superseded second
request. Same-index navigation still refreshes the selected observation. Existing
source-generation, asset validation, late-delivery and missing-interval guards
remain active. The compact navigation grid reflows independently of archive-file
controls and keeps the image actions together.

All 37 camera custody/navigation unit cases and 24 rendered recording/receipt
playback/workbench cases pass. Rendered navigation is exercised at 320 and 1200
pixel card widths, including end preservation, distinct receipt stepping and
one asset read for one action. Full local strict checking passes 114 reached
files. The initial invalid-index test used index5, which was actually a retained
telemetry gap; that failed fixture is retained and corrected, with an explicit
gap-navigation regression. This advances requirement3's local replay ergonomics;
exposure synchronization, actual execution association, installed interaction and
full workflow acceptance remain open. This source follows frozen DESKTOP297 and
is not included in that candidate. An additional nine-case compact suite passes,
including two new expanded-navigation layout cases: two columns at320 pixels and
four at1200, with every natural label inside its button and the controls inside
the panel. Initial narrow-grid failures are retained; measured nested content
width and Retina scaling informed compact labels/minimum width. Both expanded
views are retained as rendered PNGs. Package baseline passes240 files; lint,
format and both architecture contracts pass.

### Background image-observation search

A retained 10,000-status stress case exposed0.408–0.959 seconds of metadata search
on the local model (ten samples; median0.722s). The measurement is retained and
is not a native latency claim. First/Last and adjacent image navigation now run
through the existing one-owned recording worker instead of scanning on the UI
thread. Only the UI callback applies a result. It checks the exact replay object,
camera archive, cursor position and camera request generation before selecting or
decoding anything. Competing recording actions stay guarded while the worker is
active; normal UI frame processing continues.

All31 rendered recording/playback/workbench cases pass, including five paused
search cases that change the cursor, archive, replay, live-camera mode or return
to the live buffer before delivery. Late results preserve the newer selection,
clear busy state, never decode an image and send no commands. The earlier37
camera/navigation unit cases and strict114-file model check still cover the
unchanged model. The stress evidence motivated this implementation repair rather
than weakening responsiveness acceptance. Installed latency and the full workflow
remain open; these changes are also excluded from frozen DESKTOP297.

## Parser, tooltip and translation contracts — 2026-10-08

CNC parsing now exposes typed motion coordinates, document units, markup,
feed/spindle values and tool-number contracts. Tooltips retain ToolDefinition
field types through dimension formatting. Document margins now read the bounds
maintained by the parser, instead of referencing nonexistent tool_blocks/toPath
attributes. G-code word formatting now honors the configured decimal precision,
normalizes rounded negative zero and rejects nonfinite values or negative
precision, instead of delegating to nonexistent self.cnc.

Translation callbacks are isolated per translator instance and dispatched from a
snapshot so an observer can unbind without skipping the next callback. The proxy
has an explicit textual translation interface. A scoped declaration describes
the Kivy C-extension methods used by Lang; runtime inheritance still uses the
real Observable and is tested. Binding methods accept Kivy's variadic arguments.
No strictness setting, exclusion or error suppression was added.

The final 166 parser/translation/tool/preview cases pass, including eight new
behavioral tests and real Observable inheritance. Seven rendered program/frame/
tool-comparison cases pass. Full local strict checking passes all 114 reached
files, closing the previous 77 diagnostics locally. Package-wide baseline and
architecture results are recorded separately; local strict success does not
establish exact-head hosted CI, installed interaction or physical qualification.

DESKTOP296's original build39940 exited 1 after the main desktop bundle was
created, before helper packaging: build_artifact_worker imported the application
through a build interpreter path that omitted the checkout. The failure log and
scratch are retained; no helper qualification or install was attempted. The
builder now declares its packaging layout independently of application imports,
with a runtime-layout agreement test and an isolated-import build regression.
All 68 packaging/storage/helper-verification tests pass. Installed DESKTOP295 is
unchanged. A fresh frozen candidate is required for these source changes.

## CAD publication and workholding transform contracts — 2026-10-08

Profile loading now keeps editable preparation buffers local and publishes typed
immutable component/snapshot collections. GeometrySnapshot accepts input sequences,
detaches them into immutable tuples and initializes its surface/render caches
explicitly; copying, pickle reconstruction and two-frame cache behavior remain
covered. Workholding envelopes and placement share a validated finite XYZ pivot.

Workholding/ATC metadata must be objects with textual keys. Declared pivots and
CAD translations must contain exactly three finite numeric coordinates; booleans,
strings, missing coordinates and nonfinite values are rejected before publication.
Malformed component collections, groups and vertex streams fail explicitly with
ValueError. Unknown valid vendor metadata remains retained and immutable.

All 145 profile, rendering-buffer, surface-index, section and scene-geometry cases
pass, including 26 new malformed-input/metadata-detachment cases. The broader 126
rendered profile reuse/preparation/component/interaction/setup cases pass. The real
compressed-profile loader rejection is also exercised through the workspace:
invalid pivot input preserves the active machine selection and scene, reports the
specific failure, never publishes the rejected CAD and sends no machine commands.
Package baseline passes 240 files; lint, format and both architecture contracts
pass. Full strict checking now reports 77 errors in three files, down from 122 in
six; CNC, translation and tooltip contracts remain open. No checking policy was
weakened. These changes follow frozen DESKTOP296 and are not included in its build;
package/native qualification and the full requirements remain open.

## Simulation geometry and tool-mesh contracts — 2026-10-08

Shared simulation contracts now describe finite XYZ vectors, bounds, axial tool
sections, collision contacts, stock queries/removal, planner progress and reports,
and rigid/forward/inverse kinematic results. The machine-view pose has an explicit
schema. Procedural tool builders share a typed profile interface, numeric vertex
and index buffers, optional tool dimensions and CAD cutter/holder attachment
contracts. Known ToolDefinition fields retain their types through mesh preparation
instead of being erased by dynamic attribute lookup. Grid normals/corners and
transformed program normals/corners now use separate render variables.

The existing 147 geometry/stock/clearance/kinematic cases and 134 tool-visualization
and CAD-asset cases pass. Twenty-six rendered comparison/drawing/clearance cases
pass. A first tool-suite command used a nonexistent test filename and ran no
tests; that attempt is retained, followed by the corrected successful suite.
Package baseline passes all 240 files; lint, format and both architecture
contracts pass. Full strict machine checking now reports 122 errors in six files,
down from 364 in 13. Remaining diagnostics are in CNC, translation, tooltip,
CAD-profile, workholding and geometry-snapshot code; the full gate remains open.
No strictness setting, exclusion or ignore was added.

These changes follow installed DESKTOP295 and require their own package/native
qualification. They preserve existing numerical algorithms and do not establish
physical simulation accuracy, backend execution or overall workflow completion.

## Installed DESKTOP295 qualification — 2026-10-08

DESKTOP295 is installed from frozen source abaea67242afc672ef62d98735ea767d4007ef32.
Independent verification matched 554 source files and the standalone worker source,
with zero mismatches and strict signature verification. The immutable first helper
attempt passed in 2.109 seconds within the unchanged four-second deadline, retained
stdin, exited zero and created no file. DESKTOP293 remains available as recovery;
DESKTOP294's failed first attempt remains retained and uninstalled.

Native inspection displayed all 10,000 retained synthetic program entries, filtered
to native-09999.nc, and inspected its empty-file metadata. This inspection added
one synthetic item to Recent. Closing the browser returned to Idle, no selected
program or remote file, fresh reported pose, camera age 0.2 seconds and telemetry
age 0.10 seconds. No upload, run, jog, spindle, probe, tool-change or offset command
was issued. Initial exact-path UI binding timed out while the process had started;
rebinding used the same process. An initially stale camera became fresh.

Receipts are retained under carvera-desktop295-20261008: built-verification.json,
artifact-worker-attempt.json, artifact-verification.json and
native-program-browser-verification.json. This closes this package and bounded
browser interaction check only. General cold-start reliability, measured native
latency, post-freeze cancellation installation, full strict typing, hosted CI,
main integration, physical qualification and the full requirements remain open.

## Cancellable rest-stock viewport preparation — 2026-10-08

Rest-stock mesh construction now observes cancellation before allocation, every
128 candidate cells (including empty cells), and before returning a complete
mesh. Interrupted geometry is discarded. The workbench retains completed stock
results and volumes, clears the rest-stock mesh, explicitly reports visualization
cancellation, and leaves calculation controls available. Cancellation during
viewport preparation does not falsely mark already completed cutting as partial.

Twenty-one simulation-preview cases pass, including occupied/empty-grid cancellation
and publication rejection without stock mutation. Four rendered workbench cases
cover normal stock removal across Simulation/Operations/Scene and cancellation
after cutting but before mesh publication, retaining results without machine
commands. Package baseline passes 240 files; lint/format and both architecture
contracts pass. Native latency remains unqualified. This increment follows frozen
DESKTOP295 and is not included in that build.

## Cancellable complete-segment stock removal — 2026-10-08

Voxel subtraction now checks cancellation before work, every 128 candidate cells
(including already empty cells), and immediately before publication. It stages
mutations in one bounded occupancy-grid copy, allocated only after the first hit.
Interrupted removal leaves the preceding stock occupancy and volume unchanged.
The planner handles this interruption as cancellation and retains only completed
segments in stock evolution, progress and collision-result records. The cutter
profile and continuous-sweep algorithms are unchanged.

Five focused cancellation cases cover flat, ball and bull-nose cutters, resume
against the unchanged reference, interruption at publication, and planner retention
of the preceding completed segment. The broader 68-case simulation/clearance suite
and 17 rendered inspector/plot cases pass. The initial bull-nose test fixture had
an invalid zero corner radius; that failed run is retained, and the corrected
fixture uses an explicit valid radius. Package baseline passes 240 files; lint,
format and both architecture contracts pass. Native cancellation latency and
physical simulation accuracy remain open. This increment follows frozen
DESKTOP295 and is not included in that build.

Fork main advanced to 0fccde5 through PR #30. Read-only merge-tree inspection
finds one conflicting Z-probe validation hunk: our textual parameter annotation
versus upstream removal of a debug print. The debug print is now removed here
while preserving the textual contract; 83 probing regressions pass. The merge-tree
conflict still remains because both histories edit that hunk. No branch merge,
rebase, force-push or PR merge was performed. Hosted integration remains open.

## Standalone filesystem worker startup — 2026-10-08

The check/list protocol now lives in a standalone worker module. Desktop callers
reuse its schemas, validation and execution; the child no longer initializes the
parent service's subprocess machinery, threading locks or slot accounting. Both
the dedicated macOS entry and other platforms' early application dispatch use the
same worker. Request bounds, Unicode case folding, directory ordering, symlink
handling, optional directory creation and response bounds are unchanged.

The new dedicated-v2 package layout binds worker-source.py to the frozen standalone
module. Verification and installation retain dedicated-v1 support for recovery
artifacts, reject mismatched layouts/sources, and preserve the immutable first
qualification and four-second deadline. All 142 protocol, cancellation, packaging,
verification and install-gate cases pass across both layouts. Source import tracing
confirms both worker entry paths avoid subprocess/threading imports. Focused strict
checking passes both service/worker modules; the package baseline passes 240 files,
repository lint/format and both architecture contracts pass. These source results
do not establish packaged startup reliability. DESKTOP293 remains installed;
DESKTOP294 remains preserved without retry or installation.

## Streamed CAM tool metadata and geometry boundaries — 2026-10-08

Tool extraction now captures the leading header once, up to the existing 5,000
line budget, and replays it to Makera Studio, FreeCAD and Fusion parsers. A one-pass
iterator previously let the first parser consume metadata needed by later parsers.
The header reader now also avoids fetching a 5,001st line at the budget boundary.
A parser failure cannot consume the shared header needed by the next parser.
The first non-empty parser still wins; motion-body metadata is not scanned.

Makera/FreeCAD tool identifiers must be finite nonnegative integers. Fractional
identifiers no longer truncate onto another tool number; exact decimal parsing
avoids binary-float rounding of integer identity. Invalid identifier rows are
skipped while valid tools remain available. Non-finite numeric geometry stays
unknown rather than entering simulation dimensions. Existing missing/optional
geometry remains unknown; no physical identity or accuracy is inferred.

All 148 metadata/procedural-geometry regressions pass, including three streamed
CAM dialects, malformed identities, exact large integer identity, non-finite
geometry, parser isolation and observed input-pull budgets. Explicit focused
strict checking passes all seven parser/type-contract files. Nine rendered
inspector/comparison cases pass: streamed metadata from each dialect reaches the
nominal cutter drawing with inch-to-mm dimensions, no profile mutation and no
machine commands. Package baseline
passes 239 files. Full machine/imported-addon strict checking drops from 465 to
365 errors in 13 files and remains open. Source extraction improvements do not
establish full tool/toolpath simulation, installed interaction or machining
qualification. Reliable packaged helper startup remains open; DESKTOP294 was
not retried or installed, and DESKTOP293 remains the retained runtime.

Read-only macOS logs from both first-attempt windows show Python framework loading
about three seconds after qualification starts. DESKTOP294 extension loading
continues near its four-second deadline. Both passing DESKTOP293 and failing
DESKTOP294 show the same ad-hoc signature warnings, so those warnings do not
establish rejection. Startup loading overhead is a diagnostic lead; cause and
reliability remain unproven. No retry, warm-up or installation was performed.

## Background cutter-grid preparation — 2026-10-08

Saved cutter filtering, sorting, record detachment and cell formatting now run on
one background worker. Each table keeps at most one running preparation and one
replaceable pending request. New requests cooperatively cancel obsolete work;
delivery checks query, filter, sort, record snapshot, generation and dialog life.
Closing invalidates the worker without waiting. Preparation errors retain the
existing rows and expose the failure; a subsequent request can recover.

Selection, ranges, Select results and Clear update selection flags without
reformatting the entire table. Existing rows, column resizing, search and Close
remain available during preparation. Copy and Edit wait for the current view to
finish, preventing actions from mixing an old displayed view with newly reloaded
records. On preparation failure, copying uses the retained display snapshot and
editing waits for a successfully prepared current snapshot. No profile save, tool
application or machine command is added.

The focused model/rendered integration suite passes 26 cases, including a paused
1,000-cutter preparation. Thirty successive requests collapse into one successor;
selection and resizing continue during that pause. Dismissal discards late results,
worker failure retains rows, and recovery repopulates the table. The previous
synchronous-selection test failure is retained; that test now waits for explicit
worker completion before selecting an initially empty view. These tests establish
thread ownership and bounded pending work, not native latency. The full responsive
background-work/data-grid requirements and installed qualification remain open.

## Inspection compatibility, pendant dispatch and helper diagnostics — 2026-10-08

The inspection geometry module evaluated a PEP 604 union as a runtime type alias,
which prevented import on supported Python 3.9. It now uses a compatible runtime
union. Probe preset labels have a shared named schema, while construction inputs
and tolerance are passed explicitly. Controller telemetry is explicitly described
as the existing mixed-value dictionary; this annotation does not validate incoming
telemetry. Optional pendant callbacks, display numeric inputs and probe controller
identity now describe their actual contracts.

Queued WHB04 events resolve their current callback when executed. Removed handlers
are skipped; replacement handlers still receive the captured event arguments.
Unsupported MPG/percent distance requests raise a clear error instead of returning
None. Windows HID selection uses the interpreter platform discriminator, with its
branch checked separately. These local regressions never invoke real hardware.

The combined inspection/pendant/probing/helper/install-verification regression
passes 127 cases; existing CNC tests pass eight more. Tests run on Python 3.9 with
the repository's bundled HID library and PIL image provider. Initial collection
failed without a loadable HID library; a broad Homebrew library path then produced
a Kivy image bus error. Both failed logs are retained. The passing environment
uses only the bundled HID directory and PIL rather than hiding the failures.
Package baseline typing now passes 239 source files with both mypy 1.19.1 and a
fresh-cache 1.20.2 check. Strict machine/imported-addon typing remains open, with
465 errors in the preceding refreshed check. No typing suppression was added.

DESKTOP294 independently matched 553 frozen source files and passed strict bundle
signature checks, but its immutable first helper attempt failed the unchanged
four-second deadline. It remains uninstalled and was not retried. DESKTOP293 stays
installed. Future qualification failures now retain response-byte count, first
response/EOF timing, launch duration and observed process exit. Tests distinguish
no response from response-without-exit and preserve those observations in the
failure receipt. No request path, response payload or stderr is added to these
transport observations. This improves diagnosis; reliable packaged helper startup,
installed verification of this increment and the full 25-workflow goal remain open.

## Native tool search and probing contract verification — 2026-10-08

Installed DESKTOP293 loaded a synthetic local preview declaring T1 and T10.
Searching tool:T1 returned the T1 operation and exact T1 entity, excluding T10.
The entity opened Setup/Tools with T1 and its declared CAM diameter of 3.175 mm,
while machine/camera views remained visible. Closing the preview returned no
selected program or remote file; readback reported Idle, spindle/feed zero and
fresh pose/camera observations. The local fixture remains in Recent. No command
was sent to the controller. This verifies the preceding exact-search revision,
not the subsequent background-copy or compact-readiness revisions.

Current 6908a98 hosted quality hooks passed, but its test run completed with
3,712 passes, 18 skips and one recording-evidence failure. That test inherited a
viewer pose from a prior shared-fixture test without supplying its corresponding
fresh controller packet. Heartbeat correctly cleared the stale marker. The test
now owns a fresh live packet and workspace clock; production freshness is
unchanged, and the failed hosted result remains retained.

Local package typing refreshed at 148 errors in 19 files and strict machine
checking at 467 errors in 19 imported files. Both mypy 1.19.1/Python 3.9 and
1.20.2/Python 3.13 reproduced those counts, despite hosted quality hooks passing.
The discrepancy remains open. Probe form callbacks deliver text, including blank
fields, but their operation/settings signatures incorrectly declared floats.
These signatures now describe strings throughout that workflow. Runtime ASTs
match before/after when annotations and the explanatory docstring are removed.
All 86 existing probing regressions pass; explicit focused typing passes all 43
probing source files. Full package typing falls to 83 errors in eight files;
remaining typing failures and the complete physical probing workflow stay open.
Frozen DESKTOP294 predates this annotation/test-fixture increment.

## Concentrated readiness and exact setup navigation — 2026-10-08

Evidence cards now open stock geometry, fixture/vise geometry, required-tool
comparison and Datum directly. Tool review prioritizes a required number without
loaded library geometry. Missing machine identity opens the Machines library.
Navigation re-evaluates the current profile and never records evidence or applies
geometry/machine offsets. Existing receipts and configured setup remain unchanged.

At a rendered 1,000×900 viewport, fixed explanatory content previously consumed
all remaining height and left the evidence viewport at zero. Explanatory headings,
counts and telemetry now scroll with the evidence. Narrow panes retain a one-row
section dropdown; wider panes retain section buttons. Re-selecting the same
section reveals it after manual scrolling. Four sections remain reachable, hidden
pending reveals cannot scroll departed pages, and live media remain in their
existing workspace. This advances concentrated layout and actionable readiness;
complete setup readiness and physical qualification remain open.

The broader local regression passed 125 cases. Earlier ordered failures and
layout traces are retained: Retina size restoration had expanded the test window
to 24,192 pixels, and a vise assertion assumed zero starting jaw offset. Tests now
use the existing rendered-viewport helper, account for dp padding, and compare
jaw movement against the captured starting offset. The actual zero-height source
defect was repaired rather than hidden by enlarging the test viewport. Lint/format,
focused typing and both architecture contracts pass.

Hosted d7bf1b5 completed with 3,705 passes and 18 skips. DESKTOP293, frozen from
74f94a3, independently matched 553 source files and its strict signature; its first
four-second helper qualification passed in 3.459 seconds with retained stdin and
no file creation. It was installed with DESKTOP290 retained as recovery; native
readback reported Idle, fresh machine pose and no selected program. Camera age
varied across startup and remains separately observed. DESKTOP293 predates the
background tool-copy and this readiness increment. Their hosted/package/native
checks and the full controller requirements remain open.

## Exact tool search and package qualification — 2026-10-08

Workspace search now indexes individual library/CAM tools and programmed tool
numbers with missing geometry. Exact T-number queries distinguish T1 from T10;
manufacturer/product metadata is searchable. A result opens that precise tool's
comparison and calibration context, clears an unrelated local filter and preserves
the machine/camera views. Source labels distinguish declared library/CAM geometry
from unverified physical assembly identity. Changed geometry or job analysis rejects
a stale result, including changed CAM unit scale. Search/navigation never selects
or changes a physical tool. All 31 command/search/palette model and integration
cases pass, including real pane navigation with executeCommand guarded. Focused
isolated-import typing, repository lint/format and both import contracts pass.
Hosted and installed tool-search qualification remain open.

A subsequent synthetic scale study exposed expensive UI-thread geometry copying
(about 157 ms for 1,000 tools during packaging load). UI capture now copies only
table membership; the single search worker detaches geometry. Each activation
still rejects changed detached values, units or job identity. All 32 focused cases
pass, including an explicitly paused 1,000-tool copy with Escape available and
dismissed results discarded. This proves thread ownership and interaction under
the injected pause, not a native latency bound. Focused typing and full lint/format
pass. Frozen DESKTOP293 contains the preceding exact-tool search checkpoint; this
background-copy follow-up needs its own package and installed qualification.

DESKTOP292's fresh internal copy matched the signed build archive's complete
file/mode/symlink tree. Independent verification matched 552 source files against
frozen a60e763 and validated the strict signature. Its immutable first qualification
attempt answered and exited with retained stdin in 2.366 seconds, within the
unchanged four-second deadline, creating no file. This closes that candidate's
source/signature/helper gates only. Unknown OS cache context and DESKTOP291's
original timeout remain unresolved. DESKTOP292 remains uninstalled and predates
the pointer and exact-tool-search increments; DESKTOP290 remains installed.

## Pointer work and native timing evidence — 2026-10-08

Workspace hover now prunes hidden/disabled subtrees and scroll content outside
its viewport, and resolves actions in the front modal instead of covered workspace
controls. Previously hovered controls lose highlighting when covered, dismissed
or removed. Scroll clipping uses parent coordinates rather than the translated
content coordinates. The published implementation fails the new modal-hover
regression; the repaired hidden-branch, transformed-scroll and modal/removal cases
pass. A synthetic hidden branch with 10,000 descendants was skipped in 0.02 ms;
this is not an installed pointer-latency measurement.

All 74 hover/workspace/focus/layout integration cases pass, including guarded
navigation and no controller commands in the new modal case. Focused typing,
repository lint/format and both import contracts pass. The first scroll-coordinate
failure and the published-source modal failure are retained as separate evidence.

DESKTOP290's local diagnostic export retained eight navigation records. Seven
post-startup callbacks measured 0.97–2.44 ms, with window-flip notifications of
9.93–122.46 ms. The startup notification was 4.20 seconds and its largest retained
heartbeat gap was 4.64 seconds. Sampled startup locations include grid layout,
label rendering and camera texture upload; samples do not establish a single
cause. Input dispatch and actual display presentation remain outside these
measurements. The native save workflow completed without machine execution.

DESKTOP292 is frozen from a60e763, preceding this pointer increment. Its first
qualification is planned against a fresh internal artifact copy under the same
four-second deadline. A separate external-volume helper copy answered in 1.06
seconds, weakening the storage-location hypothesis; cache state and the original
DESKTOP291 timeout cause remain unknown. DESKTOP291's failure is preserved.
The broader requirements and installed pointer qualification remain open.

Hosted a60e763 CI completed with 3,701 passes, 18 skips and one coordinate-review
failure. Its fixture timestamp preceded popup construction, allowing renderer
delay to age the pose before the first fresh-estimate assertion. That integration
case now controls only the coordinate snapshot clock and advances it by two
seconds to verify stale-estimate removal; production freshness is unchanged.
All 19 coordinate model/integration cases pass locally. Hosted recovery remains
open pending the next batch. DESKTOP292 is retained for package/helper evidence;
the failed hosted gate is not represented as success or installed qualification.

## Program browser navigation and qualification evidence — 2026-10-08

The program browser now recycles visible row widgets instead of allocating every
button or truncating the listing at 250 entries. Arrow, Home/End and Page keys
move a separate cursor; Enter opens a folder or inspects a program. Preview and
upload remain explicit actions. Cmd/Ctrl+F and Cmd/Ctrl+L focus search and location.
Text editing, covering dialogs and dismissed browsers retain their own keyboard
handling. Recycled-row activation checks the listing generation and visible entry;
focused row keyboard handling resolves the current cursor instead of a rebound
widget. Navigation does not issue controller commands.

Synthetic 10,000-entry source studies at 360 and 1,000 dp allocated two and nine
row widgets. End-key dispatch measured approximately 2–4 ms, while publication
varied from 87 to 160 ms across the runs. Initial publication responsiveness and
installed qualification of this new browser remain open. Installed DESKTOP290's
shared artifact picker separately passed End-key reach, filtering and dismissal
without importing anything; ten tracked operator records retained their hashes.
That native evidence does not qualify the new program-browser source.

All 78 focused program-browser, artifact-picker, worker-verifier and installer
cases pass, including real window key dispatch, focused recycled rows, stale
callbacks, modal exclusion and no machine transfers. Lint, format and both import
contracts pass. Isolated-import typing passes for the 238 package source files;
the separate strict machine-layer check covers 113 files. Following addon imports
in the local Python 3.9 environment reports errors and is not a closed full typing
gate. The preceding published revision passed hosted CI with 3,690 tests and
18 skips; this increment needs its own hosted run.

Worker qualification now claims an exclusive first-attempt record before probing,
binds it to the package, helper digest and unchanged four-second deadline, and
retains failures. A retry cannot replace a failed or interrupted first attempt
with a warm success. Dedicated-helper installation requires the bound attempt
and refuses any retained failure. Concurrent verifier, interruption and changed
attempt cases are covered. This preserves the acceptance evidence; it does not
fix the launch latency itself.

DESKTOP291 remains uninstalled after its first four-second worker timeout. A
separate copied-helper launch completed in 1.16 seconds with retained stdin and
no file creation; existing OS cache state makes this diagnostic insufficient to
establish a cold-launch repair. DESKTOP290 and the recovery build remain intact.
Actual helper cold qualification, camera registration, synchronized capture and
the complete controller requirements remain open.

## Inspection receipt ordering and exchange — 2026-10-08

Receipt review supports source, recorded-time, signed-deviation and absolute-
deviation ordering. Stable ties retain input order; unevaluated coordinates remain
last in numerical sorts. Selection, paging and deferred row actions bind exact
feature/receipt identities, preserving selection through sorting and rejecting
departed or filtered-out identities. The deviation chart explicitly names its
current order rather than implying chronological history after sorting.

Focused receipt navigation supports arrows, Home/End and Page Up/Down. Cmd/Ctrl+C
copies the selected receipt; explicit buttons copy the selected or filtered set.
TSV carries full floating-point precision, feature/receipt/nominal identities,
coordinate kind, comparison state, limits and provenance references. Unknown
deviations remain blank, raw triggers remain unevaluated, and proposed entries
are marked proposed with no retained timestamp. Export does not qualify accuracy.

Twenty-one model/integration cases pass, including 360/900-dp review, real
keyboard dispatch, modal exclusion, stale callbacks, unchanged retained bytes,
and no controller commands. A synthetic 1,000-receipt source study observed
9.2 ms publication and 32.1 ms sorting with at most twelve allocated row controls;
copying retained every exact ID. These are source measurements, not installed
latency qualification. This follows frozen DESKTOP291 and is not in that package.
Full grid coverage, native interaction and the broader requirements remain open.

The standard macOS release route now builds and verifies the same dedicated
filesystem helper before creating its DMG. Three isolated real-CLI flow cases
verify helper/version/signature/DMG ordering, refusal on helper or signature
failure, and preserved scratch evidence. Actual standard release packaging
remains separate from the experimental DESKTOP291 artifact.

## Dedicated filesystem helper checkpoint — 2026-10-08

macOS filesystem requests now launch a minimal nested background helper bundle
built directly from `machine/artifact_fs.py`, avoiding the desktop dependency
graph. It retains the existing framing, cancellation and four-second deadline.
The builder signs the helper before resealing the containing app; independent
verification binds its source and executable digest to the frozen build request.
Installation rejects missing, changed or escaped helpers and mismatched receipts.
Other frozen platforms retain the early worker dispatch.

A real signed helper study passed its first execution in 2.1909 seconds with
stdin retained, exit zero and no file created. This is a helper study rather than
full-package or installed acceptance. The failed loose-helper signing study and
missing-default-icon build are preserved; the helper now uses the existing
controller icon explicitly. Final focused unit tests pass 103 cases.

Hosted run 37708239884 at source 9d10a204 passed quality hooks, then completed
with 3,657 tests passing, 18 skipped and one camera-layout assertion failure.
That assertion inferred navigation from window height even though navigation is
width-driven. It now checks the actual navigation width and sole visible control;
all three focused viewport cases pass. A new hosted run remains required.

DESKTOP290 remains verified and uninstalled. Full-package helper verification,
installation, native file-picker latency and the broader requirements remain open.

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

## Keyboard pose inspection with scoped focus — 2026-10-07

The declared-path chart now supports click-to-focus, arrows for individual poses,
Home/End for global endpoints, and Page Up/Down for 200-pose jumps. Keyboard
navigation crosses page boundaries while keeping the global pose, signed joint
demand, reference-frame projection and current program identity linked. A visible
focus border and chart instructions expose the controls. Wheel gestures and
modified shortcuts retain their previous routing.

The chart releases keyboard focus when its data/context is replaced or cleared,
when another motion-study view hides it, and when a covering modal receives a
key. Fifteen declared-path, view-switching and neighboring feedback-chart tests
pass, including actual Kivy keyboard dispatch, covered/empty/replaced contexts,
bounded page reads and no controller command/legacy toolpath seek. Lint and
format checks pass. Installed interaction remains OPEN; this source change
follows the DESKTOP287 freeze.

## Metadata signing and integrated navigation checkpoint — 2026-10-07

The macOS builder now reseals changed outer bundle metadata without recursively
replacing PyInstaller's nested signatures. Strict deep verification is still
mandatory. Sixteen packaging tests pass, including real macOS signing: changing
Info.plist invalidates the previous seal, resealing preserves the helper bytes,
and corrupt nested code is rejected rather than silently signed again. This is a
source packaging checkpoint; no whole-build speedup or installed-runtime result
is claimed. The already-running DESKTOP287 build uses its frozen earlier source.

The combined local inspection-navigation check at 9b8ae6 passed 53 cases and
encountered one 60-second setup timeout while opening its temporary program file,
before UI behavior began. The unchanged targeted case passed on retry (18.02s).
Both logs are retained; the timeout cause is unknown. This is separate from
installed navigation latency and hosted CI, whose acceptance gates remain open.

## Keyboard frame-chain inspection — 2026-10-07

The declared coordinate-frame diagram now participates in desktop focus order.
Clicking an origin focuses its outlined diagram; arrow keys select adjacent named
frames and Home/End reach the chain ends, including co-located origins. Selection
updates the transform details and survives projection/reference changes. Modified
keys retain their normal handling. Hiding the diagram, dismissing its review or
covering it with another modal releases focus. The caption explains these controls.

All seven frame-chain integration cases pass, including real keyboard dispatch,
linked exact identities, reference changes, compact layout, touch selection and
resize centering; the command mock receives no machine commands. Initial failures
in touch compatibility and test placement were corrected with the failed log
retained. Lint, format and diff checks pass. This extends requirement22's local
inspection ergonomics; installed interaction and actual-machine frame qualification
remain open. It follows the frozen DESKTOP287 source.

## Image-linked correspondence review — 2026-10-07

Camera registration now offers Review points on image. Its separate frozen-input
review links exact numbered correspondences to measured XYZ/UV, selected image
markers and current-fit reprojection vectors/errors. Max error selects the largest
residual; dropdown/previous/next and direct image picking retain individual
identities at co-located pixels. Zoom/pan and Fit preserve the image aspect ratio.
Border markers stay visible inside the image. Stale fits withhold residuals, and
changes to the originating panel do not replace the open review's snapshot.

All 63 camera-reference, correspondence and calibration-bench integration cases
pass. A further five-case correspondence run verifies the final rendered selection.
Initial compact failures are retained: controls and wrapped metadata could collapse
the image. Short headings, compact selectors and bounded scrolling details repair
that layout. The existing lens editor's narrow heading also now fits on fewer lines,
keeping its first field inside the viewport without weakening the layout assertion.
No controller commands occur in these checks. Installed interaction, measured
physical registration and exposure synchronization remain open. These changes
follow frozen DESKTOP287; they are not part of that installed package.

## Installed exact search and modal-opening repair — 2026-10-07

DESKTOP287, built from 4cf58392f0514237b30a5d23ce619256b20b082a, passed
source-manifest verification (549 files), strict deep signature verification and
the unchanged four-second retained-stdin worker gate on retry. The original
worker timeout remains retained. The installed executable SHA256 is
c33e2d2ee31a3fe16157873e204989fb09c3b212e3d6054d252b962a38e09713.
DESKTOP286 remains the immediate recovery app.

Native local preview of the retained 2,004-line synthetic program verified exact
phrase search for Feature 1001 and exact operation:1001 navigation, including
the resulting selected operation and line context. No program was uploaded or
run. The test-only recent-file entry was removed after closing the app, and all
ten tracked operator records matched their baseline before relaunch. The app
returned to live view with no program selected. Source-anchor interactions and
picker/startup latency remain unqualified.

Native testing also reproduced Cmd+K opening search over the program picker. A
new real-Window-dispatch regression failed before repair; search now yields to
an existing modal, opens after dismissal, and refocuses its own existing popup.
All 14 palette integration cases pass, with lint and format checks passing. This
repair follows DESKTOP287 and still requires installed verification.

## Camera delivery health and compact recovery — 2026-10-07

Twelve read-only snapshot fetch/decode samples varied from 0.044 to 3.108 seconds.
This establishes delivery variability outside the UI, without identifying its
cause or qualifying either camera clock or exposure alignment. The Camera Source
section now shows generation-bound request/accepted/failure counts, current
in-flight elapsed time, last attempt duration and separate request/read versus
JPEG decode durations. Failed attempts retain the last image while withholding
previous successful timing values. Replaced sources reject old completion, and
a second caller cannot add another in-flight request in the same generation.
Existing capture/receipt timestamps and recording/calibration file schemas retain
their meaning; local timings do not establish exposure synchronization.

Compact rendered checks exposed two real layout faults: the camera's fixed status
footer could consume its entire short-window viewport, and a reconnect banner's
fixed buttons left its text almost no width. Camera sections now use a dropdown
at narrow widths and retain synchronized status messages in their scrolling
content. Reconnect text stacks above its buttons at narrow widths. Reconciliation
is deferred beyond the parent's layout iterator. The machine-action row also
fits the available width; visual review found STOP previously overflowed its edge.
Its callbacks and guards are unchanged.

All 112 camera/recording/calibration unit cases pass, as do all 71 camera and
connection integration cases, including compact/wide resize cycles, hidden banner
pointer behavior and bounds for connection, hold, stop and recovery controls.
Strict model typing, focused UI typing, lint/format and both architecture contracts
pass. Initial assertion, spacing-type and synchronous reparent failures remain
retained. These changes follow frozen DESKTOP288; installed interaction, causal
latency diagnosis, physical registration, synchronized capture and the full
requirements remain open.

## Bounded Linux quality setup — 2026-10-07

Authoritative job 112949754625 in run 37667315796, at published revision
20487bac77d4400a3b96ec72fec5a5ae3af46c39, still reports Install Linux
prerequisites in progress from 18:30:50Z; quality hooks and tests remain pending.
The exact blocking subprocess is unknown. The active run remains untouched.

Future quality runs skip unused AppImage deployment tooling. Dependency setup
steps have explicit 15/10-minute limits; apt-get uses noninteractive mode. Release
setup retains AppImage tooling, with HTTP failures fatal and bounded curl connect,
transfer and retry limits. Invalid script arguments fail before system commands.
Six inert-adapter tests pass for successful quality setup, propagated package
failure, failed bounded release download, rejected options and retained quality
hooks/tests. Shell syntax and lint/format pass. Actual Ubuntu setup, published CI
and overall completion remain open. These source changes follow frozen DESKTOP288.


## Installed correspondence identity and keyboard review — 2026-10-07

DESKTOP288 native review captured frozen frame688 at1280×720 and inspected three
explicitly synthetic, temporary XYZ/UV correspondences. Next retained distinct
identities for two co-located pixels; direct image picking selected the third
point with its exact XYZ/UV details. Unfitted residuals remained unavailable.
No fit or calibration was saved, synthetic point inputs were cleared, and all
ten tracked operator records retained their baseline hashes. This closes only
that installed identity/navigation check; fitted reprojection, measured physical
registration and exposure synchronization remain open.

A source regression then reproduced marker clicks failing to focus the image.
Marker selection now retains focus, with arrows and Home/End selecting exact
points, +/− zooming and0 fitting the image without changing selection. Covering
or dismissing the review releases focus, and modified navigation keys retain their
normal handling. All64 camera reference, correspondence and calibration-bench
integration tests pass, including actual keyboard dispatch, co-located identities,
zoom/reset, modal focus rejection and unchanged inputs with no controller commands.
Focused typing, lint and format checks pass. This keyboard increment follows
DESKTOP288 and still requires installed interaction qualification. The complete
controller requirements remain open.

## Installed spatial-view crash and rendering repair — 2026-10-07

Native DESKTOP288 inspection of the illustrative head/head frame chain exposed
a real rendering failure: opening the spatial diagram exhausted Kivy's 128-level
stencil stack. The crash log and process stack sample are retained in the
DESKTOP288 evidence directory. The focus border had cleared StencilView's
canvas.after cleanup, removing StencilPop. It now owns a separate instruction
group and preserves the framework's clipping instructions.

The regression fails on the old source before repeated rendering. All eight
frame-chain integration tests pass after repair, including 150 render/focus
cycles and an assertion that no controller commands were sent. Focused typing,
lint and format checks pass. The recovered DESKTOP288 process was independently
observed connected and Idle with live reported pose, fresh camera and telemetry;
its installed source still contains the defect. DESKTOP289 was frozen before
this repair and is held from installation. Corrected package verification and
installed spatial-view interaction remain open, as do the full requirements.

## Complete local typing gate refresh — 2026-10-08

Full package and strict machine checks reproduced four errors in the shared
program-analysis geometry variables: NURBS immutable samples/bounds were inferred
more narrowly than cubic/linear lists subsequently assigned to those variables.
The shared read-only geometry contract is now explicitly Sequence[Point], without
changing path conversion or iteration. All 236 package files and all 112 strict
machine-layer files pass the configured local mypy checks. Ninety-eight NURBS,
data-block, geometry and inherited-feed unit cases pass. Full lint/format and both
architecture contracts (307 files) pass. This follows frozen DESKTOP290; its
source/package identity remains the independently tracked spatial-repair revision.
Local checks do not close hosted CI, installed workflows or backend qualification.


## Installed camera receipt navigation — 2026-10-08

DESKTOP298 is installed from frozen source
`a5221e3b4d15849abe0481fc32e467b584f26833`. Independent artifact verification
matched554 source files with no identity mismatch and verified the strict
signature. The immutable first helper attempt passed in1.973seconds under the
unchanged four-second deadline, retained stdin and created no file. Installation
reverified source/signature and preserved DESKTOP297 as recovery.

Native file-picker imports loaded the retained4684-event status archive and
matched camera bundle with28frames and0missing. Camera First/Next/Previous/Last
selected receipts4455/4457/4456/4520; First again returned4455. This verifies
distinct receipt navigation and rendering in the installed app. Live camera and
live recording buffer were restored; final native readback reported Idle, no
local/remote program, fresh reported pose, camera0.5s and telemetry0.14s.
The first launch observation timed out while the process was running; rebinding
reached the same process without a duplicate launch. A First-action observation
took40.85s including automation overhead; native latency is not qualified.

Source revisions315be74, deff8a6, ac0db0c and93ce75c extend cancellable motion,
stock/collision and exact-byte CAD preparation after the frozen build and remain
uninstalled. Final identity checks and scene/setup capture still require further
responsiveness work. Camera registration, exposure synchronization, installed
fault/cancellation interaction, physical qualification and full25 remain OPEN.
No CNC actuation occurred. Detailed build, helper, install and native receipts
are retained in the local carvera-desktop298-20261008 evidence directory.


## Continuous-clearance stock cancellation — 2026-10-08

Clearance review now passes Cancel through both the private residual-stock clone
and ordered cut subtraction. Interrupted stock work unwinds without publishing a
partial plot. The UI also checks Cancel when delivering a completed report, so a
late cancellation preserves the prior review. The diagnostic covers the entire
review rather than incorrectly calling every interruption CAD verification.

Three model cases interrupt actual clone allocation, occupancy copying and cut
subtraction and retain caller stock exactly. Three rendered cases pause the actual
worker during cloning, subtraction or completed-result delivery, process UI
frames, dispatch Cancel, and verify recovered controls, unchanged captured inputs,
previous plot/parent and stock, and no plot publication or controller command.
All62 residual-clearance/trace/stock model cases and39 rendered simulation launch,
clearance plot and inspector cases pass; package240 typing, lint/format pass.
This follows installed DESKTOP298 and requires package/native cancellation
qualification. Final identity checks, scene/setup capture, general native latency
and the complete controller requirements remain OPEN.


## Setup-remedy comparison recovery — 2026-10-08

Baseline and candidate comparisons now clone stock with cancellation enabled;
a cancelled baseline skips candidate preparation. Cancelled clone preparation
returns explicitly cancelled observations with no claimed contact or removal
differences, preserving the caller's stock. Alternative CAD identity reads on the
worker also accept Cancel. Final byte identity and stale setup/alternative guards
remain before accepting a result.

Repeating an unchanged remedy retains its accepted comparison and contact browser
until a replacement is accepted. Cancellation, including after calculation but
before delivery, preserves that review. Thread construction/start RuntimeError or
OSError restores controls, retains the review and reports an owned diagnostic
without retrying or exposing platform details. Changed drafts and stale setup or
alternative geometry still invalidate results and navigation.

All66 remedy/residual/stock model cases and34 rendered remedy/inspector/plot cases
pass. New cases interrupt both actual stock clones and exercise four real worker
pauses (CAD, baseline, candidate, delivery), UI frames and Cancel, plus four launch
faults with a previously accepted comparison. Stock, contact browser and accepted
result remain unchanged with no controller commands. Package240 typing, lint and
format pass. This source follows frozen DESKTOP299 and is excluded from that
build; installed fault/cancellation verification, native latency, final UI
verification/capture responsiveness and the full25 remain OPEN.


## Background selected collision geometry — 2026-10-08

Starting material-removal simulation now captures selected fixture/vise profile
references and placement values without constructing the displayed machine scene.
The worker prepares only those collision components, then computes their program
coordinate bounds. It does not rebuild repeat-stock meshes or mutate viewer edge
state. Immutable profile groups and the worker-safe placement cache retain the
same selected geometry and bounds; existing setup/asset identity checks still
reject results for older selections.

Workholding placement checks Cancel every128 vertices and before publishing its
complete cache entry. Interrupted transforms preserve existing cached placements.
Collision preparation also checks before and after the selected component mapping.
GeometrySnapshot validation and cache-hit locking remain finite, noninterruptible
steps; final exact-byte acceptance and context capture still perform UI work.

All89 profile/simulation input model cases pass, including same geometry/bounds,
empty selections, pre-publication mapping cancellation and five actual placement
interruptions with unchanged prior cache. The rendered preparation case pauses
the worker before collision generation, processes UI frames and dispatches Cancel,
verifying no full viewer-scene call, preserved prior results and no commands.
This source follows frozen DESKTOP299 and is excluded from that build. Native
large-profile latency/cancellation and full25 remain OPEN.

## Exact linear preview and batched source pages — 2026-10-08

Installed DESKTOP301 from ebc183c4 independently matched554 package files,
verified its strict signature and passed its immutable first helper attempt in
1.193seconds. Native absolute and home-relative filename imports merged the same
synthetic cutter without duplicate IDs or replacing the three existing cutters.
A20,008-line local preview reached Calculating; Cancel recovered Simulate and
reported cancelled stock visualization while camera/telemetry stayed fresh.
The native phase was visualization, not identified snapshot preparation. Seven
tracked operator files were restored byte-for-byte, followed by fresh live
Idle/no-program/0RPM/0feed readback. No machining commands were invoked.

That installed preview exposed length-dependent XYZ tessellation. The diagnostic
parser expanded20,000 long straight moves into4,799,771 UI vertices. Its profiled
rendered run hit the existing test timeout; retained49.5seconds of UI profiling
included39.5seconds in load callbacks and30.1seconds in per-vertex parsing. This
failed baseline is not a completed-load timing claim.

Fixed-angle G0/G1 preview now retains exact start/end vertices tagged with each
source line, tool and feed. It does not invent a first approach from origin;
changing rotary angle still uses existing interior samples, and arcs/canned
cycles retain their paths. Linear cutting bounds now include the true start,
rather than excluding the first fractional interpolation interval. This is local
visualization and does not alter transmitted G-code or manufacturing simulation.
Source pages prepare rows locally and publish once, preserving markup, source
numbers and previous/next/last page behavior.

The same completed profiled rendered load used40,003 vertices and took5.269s
including fixed frame-pump waits; ordinary rendered samples took4.768–4.771s.
These are source-harness observations, not installed latency qualification.
Tests verify long absolute/relative lines, inch conversion, fixed/changing A,
stationary commands, first approach, source/tool/feed identity, exact full-line
seeking and one data notification for10,000 rows. Package240 and strict114 typing
remain green. Installed qualification for this newer source, remaining CAD scene
preparation/acceptance work, exact-head hosted CI and full25 remain OPEN.

## Imported-stock desktop integration — source checkpoint, 2026-10-09

Scene → Components → Stock now offers **Import stock STL…**. The import notice
requires a name and an explicit millimetre/inch source unit. Parsing, solid
validation, actual-triangle preview and bounded GPU buffer preparation run in a
cancellable worker. The previous selection stays visible until preparation
succeeds. Changed input bytes, changed setup or a superseding selection withhold
publication. The component worker also recovers from thread-start failure.

The machine viewer renders source triangles and edges, including concavities,
rather than filling the source bounds. Placement translates the source minimum
to the declared stock corner and rotates about the stock center in program Z.
The placement editor retains that model, prepares changed preview geometry in
its worker, and locks source dimensions. Its XY/XZ schematic is explicitly a
bounding envelope. Immutable stock draw batches can be reused during redraws.

Simulation initializes occupancy from the selected solid; initial gaps are not
machined removal. Residual import requires matching source/setup identity,
placement, initial occupied count and no material outside the initial shape.
Scene schema 3 retains source path, SHA-256, units and bounds. Restoring it loads
the actual source asynchronously and shows no placeholder block. Portable jobs
bundle that exact source asset, and retained scene reconstruction reloads it.
A changed or unavailable source is refused, without falling back to a box.

This advances requirements for true stock solids, source-linked simulation,
portable jobs and responsive preparation. Native installation and exercised
import acceptance remain OPEN. Imported-stock arrays, arbitrary stock orientation,
large-model interaction performance, source-contour setup drawings and physical
registration/qualification remain OPEN. DESKTOP328 is frozen at `ae5423f` and
excludes this newer desktop integration; package qualification is separate.

DESKTOP328 package receipt: all 573 source files matched frozen `ae5423f` and its
strict signature passed. Its immutable first helper probe failed at 4.014 seconds
with zero response bytes and no observed startup-stage marker. Launch itself took
0.054 seconds; child PID 87476 was recorded. These observations do not establish
why execution had not reached the instrumented stages. The candidate remains
uninstalled, and no retry changes that failed qualification. DESKTOP324 remains
installed by fresh version-file readback. Receipts:
`/Users/wes/.codex/artifacts/carvera-desktop328-20261009/built-verification.json`
and `artifact-worker-failure.json` in that directory.

Recording context retains stock units, bounds and source SHA-256 while omitting
the local stock path. Setup archive binding refuses a different or omitted stock
identity, and verifies the bytes actually retained against the selected source.
The GPU draw check rendered the L-shaped source with its actual triangles/edges,
reused the unchanged stock context and framed the selected shape. Its synthetic,
disconnected scene render was visually inspected; camera and physical state were
mocked for that check. An earlier supplemental UI run timed out during shared
app startup before any of its tests ran; its failure is preserved independently.
Portable archive export also compares the selected stock digest with the asset
bytes actually bundled before publishing a destination. Changed source bytes
refuse export while retaining an existing destination; an earlier preflight hash
alone does not substitute for this check.

Source verification at this checkpoint records 268 distinct passing test cases
across focused unit, rendered setup/import, GPU draw, package custody and
recording/historical playback runs (overlapping suites are deduplicated by test
identity). The final combined 25-case UI run has 24 passes and one failure in
synthetic camera archive provisioning: the writer remained alive at its existing
five-second flush deadline. The separate recording UI run passed those workflows;
the combined-suite gate remains OPEN. No production deadline was relaxed to
qualify the application. Earlier failed attempts and their logs are retained.
The source receipt is
`/Users/wes/.codex/artifacts/carvera-stock-desktop-acceptance-20261009/source-verification.json`.


## Actual stock edges in the placement editor — source checkpoint, 2026-10-09

Imported-stock placement drawings now project actual source mesh edges in XY and
XZ with one shared scale. They preserve source concavity, nonzero source minima
and explicit mm/inch units. Source-size views omit placement; corner views omit
rotation for editing the unrotated program corner; rotation views rotate both
projections about the stock center; declared-machine views include WCS and stock
rotation. Gray retains the previous placement and teal shows the draft. Hidden
edges and triangulation are explicitly identified, without claiming an occluded
silhouette or measured stock. Source dimensions remain locked.

Edge deduplication, transforms and unsigned-short GPU batch construction run in
a coalesced, cancellable background lane. A changed draft supersedes earlier
work; dismissing the editor closes its lane and prevents late publication. A
missing matching source shows an unavailable drawing without a substitute block.
The drawing changes no controller state. Native interaction/large-source latency,
true silhouettes, arbitrary stock orientation and physical registration remain
OPEN.

A separate DESKTOP328 startup diagnostic completed in 0.216s with all six fixed
stages, while the original first four-second failure remains byte-for-byte
unchanged. Read-only unified logs contain an AMFI ad-hoc/unknown-chain warning
for the exact helper and a later provenance event for PID 87476. Passing older
packages also emitted ad-hoc warnings; these observations do not establish
signature rejection or identify the cause of the original delay. No security
settings, signing credentials, production deadlines or qualification status were
changed. DESKTOP328 remains uninstalled; the installed/native gate stays OPEN.
Receipt: `/Users/wes/.codex/artifacts/carvera-desktop328-20261009/startup-diagnostic-evidence.json`.

Focused verification records 103 distinct passing cases across 26 geometry/model
cases, 73 rendered import/setup cases and the final nine projection/four recovery
cases, deduplicating repeated tests. The rendered source L-shaped notch and its
XY/XZ views were visually inspected. Source drawings prepare off the UI thread;
clock ticks continue while a preparation worker is deliberately blocked, newer
drafts supersede it, and closed editors discard it. Failure recovery can prepare
the same draft again without a block fallback. This does not close the earlier
combined recording-suite flush timeout or installed/native acceptance.
Receipt: `/Users/wes/.codex/artifacts/carvera-stock-projection-20261009/source-verification.json`.


## Retained native helper startup sampling — source checkpoint, 2026-10-09

A separate diagnostic harness copies only the failed native helper into a fresh
output, assigns a fresh ad-hoc signing identity and independently checks that its
Mach-O instruction section is unchanged. It preserves the failed package and
first-attempt receipts, archives its own exact harness source, and emits no
qualification or installation receipt. Output reuse, a changed original helper
or attempt, and destinations inside the failed package are refused. The original
four-second qualification deadline and first-attempt policy remain unchanged.

Sampling targets only the harness-owned child. Tool output, actual stack-file
availability, observed stage tokens, request timing and cleanup are recorded
separately. A sampler exit of zero alone does not prove a captured stack. Two
fresh-identity observations completed in 1.688 and 1.105 seconds without retained
stacks; the early sampler reported pid_for_task failure. Those observations do
not identify whether sampling missed an exiting process or another access/state
condition. They do not qualify the failed package.

The third diagnostic used sample's documented -mayDie option and deliberately
withheld input for five seconds while keeping stdin open. It retained nine
samples of main -> getchar -> __read_nocancel, consistent with that induced input
wait. Input was sent at 5.010 seconds and the valid response/exit was observed at
5.012 seconds; no destination file was created. The main-stage token was observed
at 2.406 seconds, which is an observation time, not a precise execution timestamp.
This demonstrates stack-capture capability on a retained child. It does not
explain DESKTOP328's original no-stage timeout or prove cold OS-cache behavior.
Sampling itself can perturb scheduling. Original receipt and helper hashes remain
unchanged; DESKTOP328 remains FAILED and uninstalled.

Regression verification records 47 distinct passing cases across diagnostic,
first-attempt worker, installer and build-preflight suites. Three transport-only
assertions now use real pipes with a controlled clock so interpreter startup
load cannot substitute for their response-versus-exit and stderr-privacy checks.
Real-worker and immutable package deadline tests remain separate. The initial
45-case run had two startup-sensitive failures; that log and the initial imported
legacy typing failure are retained. Strict typing passes the two new modules;
the application baseline passes 255 files, and both architecture contracts pass.

Diagnostic receipts:
`/Users/wes/.codex/artifacts/carvera-helper-startup-sampling-20261009/diagnostic-evidence.json`,
`/Users/wes/.codex/artifacts/carvera-helper-startup-sampling-early-20261009/diagnostic-evidence.json`,
and `/Users/wes/.codex/artifacts/carvera-helper-startup-sampling-retained-input-20261009/diagnostic-evidence.json`.
Reliable first-launch qualification, installed acceptance of newer workflows,
physical registration and the full controller overhaul remain OPEN.


## Imported solids in repeat-part arrays — source checkpoint, 2026-10-09

Repeat plans now retain immutable per-instance source references with path,
SHA-256, explicit units and source bounds. Schema 2 preserves those declarations;
existing schema-1 block plans remain valid. Parsing and saving a machine plan do
not open source files. Regular-array recovery includes source identity, so a
mixed-shape custom table is not replaced by one common source. Source dimensions
stay locked through array and individual part edits.

Array layout can copy the current scene solid or explicitly choose a rectangular
block. Exact source loading, solid validation, placement geometry, combined nominal
preview and GPU batches prepare in a background lane. Source solids are shared;
each placement has its own bounded preview cache. A final byte refresh rejects a
source changed during preparation. Changing the selected part, plan, profile or
scene placement prevents stale completion. Cancel stock preparation and view
closure retain the previous scene. Preview without its required source preparation
is refused, with no substitute box. Source triangles share a 100,000 budget.

Declared-WCS simulation initializes each source's actual material occupancy and
applies the actual ordered path to every stock. Array result exchange freshly
checks source bytes and validates residual placement, initial material count and
material membership in each source. Swapping occupied material into an initial
notch is refused even with matching counts, volumes and recomputed transport
hashes. Sources remain external references; .cvstocks does not embed source files.
The two-million voxel and 100,000 residual-face budgets remain unchanged.

The first regression also exposed an existing boundary mismatch: array contexts
omit the single active-stock record, while the newer shared asset checker required
it. The checker now handles that omission and array exchange independently verifies
all declared stock sources. Its original 17-failure log is retained. The first
rendered run passed 21 cases and timed out in the existing 20-second array-load
callback wait; that failure remains retained and no production or test deadline
was relaxed. Final source verification is retained separately.

Unrotated imported arrays advance the multi-stock requirement. Arbitrary stock
orientation, exact interlocking-shape overlap, native large-array responsiveness,
installed workflow acceptance, measured registration, physical machining and the
full controller overhaul remain OPEN. DESKTOP328's failed first helper qualification
is unchanged; this checkpoint does not build, install or send machine commands.

Verification records 122 distinct passing unit cases across stock, array,
residual archive and geometry-context checks, deduplicating overlapping runs.
Final targeted checks cover plan-revision cache invalidation, pre-allocation
residual-grid refusal, required-field serialization and nonzero-source-minimum
archive restoration. Six final rendered array cases pass: completion, changed
selection, changed placement, cancellation, changed bytes and view closure.
Saved-plan restoration, explicit source-to-block switching and disabled source
dimensions were exercised. Source control renders were visually inspected; the
calculation/cancel layout was compacted. Strict repeat-plan typing, the final
255-file application baseline, both architecture contracts, Ruff and format pass.

The broader rendered suite's final combined run remains 22 passed / 2 failed:
one custom-plan test attempted a block switch without explicitly starting a new
array and was corrected and passed in the final six-case run; the other exceeded
the unchanged 20-second calculation wait. The preceding run exceeded the same
wait during result loading. Combined-suite timing acceptance remains OPEN; no
deadline was relaxed and no claim of a timing repair is made. Retained source
receipts: `/Users/wes/.codex/artifacts/carvera-import-array-source-20261009/source-verification.json`.

## Repeat-stock calculation and display responsiveness — 2026-10-09

The unchanged 20-second workflow gate was reproduced with stage-level timing
and retained worker stacks. Toolpath simulation took approximately 0.08 s wall,
while one stock's per-cell display surface took 13.5 s; the second surface was
still running at the deadline. Wall time greatly exceeded worker CPU time on
the congested host. This identifies surface work in that failed run; it does
not establish the unrelated native helper's startup cause.

Rest-stock extraction now compares byte-row occupancy masks and merges only
coplanar exposed grid faces into rectangles. Occupancy, collision calculations,
cavities, disconnected islands, normals, outward winding and rotated placement
are preserved. Independent exhaustive comparison covers all 256 occupancy patterns
of a 2 × 2 × 2 grid, checking exact exposed-face coverage with no missing or duplicate
faces. Additional unequal-cell, translated, cavity, checker, island and rotated
cases check boundary area and signed material volume. The 100,000 emitted-face
and shared two-million voxel bounds remain; no deadline or resolution was relaxed.

For a 40 × 40 × 10 mm block, the retained same-host comparison emits 6 quads instead
of 4,800 and reduces CPU from 0.458 s to 0.005 s. Random voids in the same grid reduce
CPU from 0.629 s to 0.245 s and emitted quads from 15,728 to 10,230. Exact triangle
tessellation differs; boundary area and signed volume match. These are scoped
measurements, not universal machine-independent deadline guarantees.

Calculation and archive workers prepare immutable array display surfaces,
edge buffers and render-frame conversions. A selected result view retains
one combined mesh rather than six complete copies. A new active-part selection
prepares off the UI thread; context, selection, scale and cancellation guards
retain the previous scene on stale completion. Imported result displays retain
actual source edges. GPU instruction creation stays on the UI thread. Repeated
scene builds reuse prepared snapshots and render buffers. Unexpected calculation,
archive and playback worker exceptions release controls with an explicit error.

The final combined 28-case rendered run passes, including the original 20-second
calculation and result-load waits. A separate imported-solid end-to-end rendered
case passes simulation, selection, save and reload. All 127 distinct focused unit
cases pass, along with strict typing of three core modules, the 256-file application
baseline and both architecture contracts. Earlier failed runs and their traces
remain retained. Source receipts:
`/Users/wes/.codex/artifacts/carvera-array-responsiveness-20261009/`.

This closes the reproduced calculation/loading **source and rendered test** gate.
DESKTOP324 remains installed; no package, installation, native acceptance or
physical-machine gate is closed by these tests. The full original 25 plus accepted
supplementary controller requirements remain active, including arbitrary stock
orientation, camera registration/synchronization and backend/physical qualification.

## Camera recording group commits and drain recovery — source checkpoint, 2026-10-09

Camera recording now commits up to eight already-queued receipts per journal
sync. It does not wait for a batch to fill. Every new JPEG asset is still synced
and read back against the accepted bytes before its receipt is admitted. The
existing digest chain, source-generation boundaries, queue and byte limits,
immutable assets and five-second production close deadline are preserved.
Written counts advance only after the whole receipt group has successfully
flushed and synced. A failed journal commit accounts for both its batch and
remaining queued frames, releases pending bytes and retains the partial files.
An asset or journal failure cannot produce a successful saved status in the UI.

The recording workbench distinguishes active, flushing, saved and incomplete
parts. Flushing shows written/missing counts and pending bytes. A close timeout
keeps the same owned writer, with capture detached and restart/new-session
controls unavailable until that writer has stopped. Refresh observes eventual
completion without replacing the writer or starting a second drain operation.

In a controlled same-host comparison with 18 identical JPEG receipts, journal
syncs including header/footer fell from 20 to 6; all frame bytes and ordering
were verified in both archives. Wall time was 0.508 s before and 0.213 s after
in this synthetic run. These measurements do not establish a universal latency
guarantee or the cause of the earlier host-dependent timeout.

All 105 focused recording/camera unit cases and 53 combined rendered cases pass.
The combined run includes every test identity from the earlier failing 25-case
stock/history/recording run. It retains the production five-second deadline and
the pre-existing longer synthetic playback-fixture wait without modification.
Fault-injection cases verify sync-before-written ordering, bounded groups,
failed-commit accounting and same-worker timeout recovery at narrow and wide
panel sizes. Strict camera-core typing, the 256-file application baseline, both
architecture contracts and changed-file lint/format checks pass. Receipts:
`/Users/wes/.codex/artifacts/carvera-camera-drain-20261009/`.

This closes the camera drain **source and rendered test** checkpoint. A new
desktop package is not admitted while available storage remains below the
workspace's 200 GB build floor. The installed application is preserved, and
DESKTOP328's failed immutable first-helper attempt remains failed. This source
checkpoint does not qualify a replacement package, native installed workflow,
camera registration, exposure synchronization or physical-machine behavior.


## Full fixed stock orientation — source and rendered workflow, 2026-10-09

Stock placement now accepts fixed X/Y/Z orientation for both blocks and imported
solids. Right-handed extrinsic X, then Y, then Z (`Rz·Ry·Rx`) rotates about the
stock center; stock dimensions and entered corner remain local, and WCS remains
a separate translation. Preview vertices/normals, material subtraction, residual
admission, coordinate review, context invalidation, portable jobs and historical
recording reconstruction share this orientation. This does not implement
simultaneous rotary motion or establish measured mounting.

The reviewed editor adds X/Y tilt controls beside Z rotation, explicit rotation
order, padded responsive fields, and XY/XZ drawings of all block or source-mesh
edges. Draft/previous drawings retain a shared scale. Scene and residual schema 4
retain tilt; Z-only scene records and residual schemas 1–3 remain readable. The
facing shortcut uses the projected bounding-stock envelope and highest program
Z, labeled as unmeasured geometry. Repeat arrays explicitly reject oriented stock
until their placement path supports it.

Validation covers independent Rodrigues-transform agreement (including singular
angles), rotational covariance of flat/ball/bull/drill subtraction, imported
vertices/normals/voids, all block/source projection edges, schema compatibility,
residual mismatch refusal, geometry-context invalidation, inverse coordinate
review, portable residual reconstruction and recorded-scene reconstruction.
Rendered tests exercise draft/apply/save/restart/facing at narrow and wide sizes,
and imported-stock editing/export/restoration after the original source is
removed. Tests intercept machine command writes. Earlier test failures and logs
are retained; the array orientation tests use new editable panels so earlier
retained custom-plan state cannot mask the orientation guard.

All 390 distinct unit-test identities and 96 distinct rendered-test identities
pass across the retained focused suites. Six core modules pass strict typing;
the 256-file application baseline, both architecture contracts and all 34
changed Python files' lint/format checks pass. Narrow drawing captions retain
the plane and geometry label in a compact line. No production deadline was extended.
The verification receipt records distinct test identities and individual suites:
`/Users/wes/.codex/artifacts/carvera-stock-orientation-20261009/source-verification.json`.
Source and rendered validation are independent of installed/native acceptance.
The 200 GB available-space admission floor still blocks a replacement desktop
build. DESKTOP324 is preserved; DESKTOP328's immutable first-helper failure is
not replaced by later diagnostics. Full machine collision, arbitrary array
orientation, camera registration/synchronization, qualified adaptive actuation,
advanced-machine adapters and physical qualification remain open. The full
original 25 plus accepted supplementary implementation goal remains active.


## Fixed XYZ orientation for repeat arrays — source/rendered checkpoint, 2026-10-09

This extends the preceding fixed single-stock checkpoint. Each block or exact
imported solid in a G54–G59 repeat plan now retains fixed X/Y/Z stock angles.
Scene-seeding, regular layout recovery, retained individual drafts and atomic
bulk editing preserve these angles. Different per-part angles remain an explicit
custom layout. Save/Restore retains the reviewed schema-3 plan without opening
source assets or applying controller offsets. Legacy unrotated plans keep their
existing schema and revision representation.

Preview, machine-space simulation and result exchange rotate each stock about
its declared center with the shared fixed X→Y→Z convention. The entered corner
remains the unrotated grid corner. Programmed G54–G59 motion stays a translation;
stock rotation does not rotate or duplicate the toolpath. Active-part changes,
prepared nominal/imported geometry, voxel material and declared-frame playback
retain the same placement. Rest-stock admission validates all angles and the
unrotated grid before decoding occupancy, with the existing shared budgets.
Z-only and unrotated snapshot compatibility remains covered.

Overlap admission uses the 15 separating axes of oriented bounding stock boxes;
a differently tilted skew-box case needs the edge cross axes. Imported voids
do not establish mounting clearance or authorize interlocking. Frame review
labels the displayed gap as a bounding-envelope quantity. Angle fields fit at
360/760 pixels, and changing an applied angle invalidates earlier results while
an unapplied draft retains the displayed scene. Invalid angles leave the plan
and text drafts available for correction.

Verification: 123 current distinct unit identities and 35 rendered identities pass across
the retained focused suites. Tests cover independent Rodrigues corner projections,
3D separation, schema/revision compatibility, exact imported references, actual
subtraction, pre-decode mismatch refusal, save/readback, restored custom angles,
preview, simulation, all-stock result exchange and declared-frame playback. The
rendered workflow intercepts controller writes; both narrow/wide images were
visually inspected. Strict typing covers six core modules; the 256-file
application baseline, both architecture contracts and repository lint/format
checks pass. Earlier failed attempts are retained. No production deadline changed.
Receipt: `/Users/wes/.codex/artifacts/carvera-array-orientation-20261009/source-verification.json`.

Source/rendered array orientation is CLOSED at this checkpoint. Installed/native
acceptance remains OPEN: available space is below the 200 GB build-admission
floor, DESKTOP324 is preserved, and DESKTOP328's immutable first-helper failure
remains failed. Changing rotary pose, complete machine collision, camera
registration/synchronization, adaptive actuation, advanced-machine adapters and
physical qualification remain open. The full original 25 plus accepted
supplementary implementation goal remains ACTIVE.


## Continuous articulated body clearance — source/rendered checkpoint, 2026-10-09

The Machine workbench now includes a collapsed Continuous machine-body clearance
section within the declared kinematic workflow. Conservative boxes can attach to
world, chain bases or individual spindle/workpiece links. The responsive editor
retains independent body drafts, validates changes atomically, and requires
explicit named exclusions for intentional mounting contact. Geometry can be
saved/read back; `.cvclearance` exchange retains the route and recomputes the
saved report before admission. Rejected loads preserve the current result.

The engine bounds motion between poses using analytic chain displacement
bounds and oriented-box separating axes. Full rotary turns are retained, both
chains may move, and the earliest possible interval per pair/segment is reported
with a separate midpoint-overlap witness. Linked XY/XZ projections show the
selected interval. Bounded work, cancellation, stale-result rejection and worker
failure/launch recovery preserve UI responsiveness. No controller writes occur.

Verification covers between-endpoint collisions, nested pivots/translations,
intermediate links, moving workpiece chains, limits, explicit exclusions,
budgets, cancellation, atomic file preservation, tampering despite re-signed
payloads, recomputation, retained drafts, save/reload, rejected-load preservation,
stale file pickers and worker recovery. Narrow/wide renders were inspected. The focused suites pass 150 distinct unit
identities and 16 rendered identities; four core modules pass strict typing,
the 260-file application baseline passes, both architecture contracts are kept,
and repository lint/format checks pass. Earlier failed attempts are retained.
Receipt: `/Users/wes/.codex/artifacts/carvera-joint-clearance-20261009/source-verification.json`.

This is declared-body continuous clearance only. Complete measured Carvera CAD
linkage, rotary material removal, camera registration/synchronization, adaptive
actuation, advanced-machine adapters, installed acceptance and physical
qualification remain OPEN. The full original 25 plus accepted supplementary
overhaul goal remains ACTIVE. Package admission and immutable first-helper
acceptance remain independent of this source/rendered checkpoint.


## Workspace geometry to articulated clearance — source/rendered checkpoint, 2026-10-09

The Kinematics & machine clearance workbench connects the current C1 CAD scene
to the continuous body review. Explicit capture retains selected component
profiles, placed fixture/vise geometry, hidden components, stock/repeat-plan
bounds and a chosen loaded tool assembly. Separate components follow the same
X/Z spindle and negative-Y table motion as the viewer. Source metadata binds the
original captured declarations and survives review exchange. Capture starts
with two stationary preview-point waypoints, ready for explicit route editing.

This uses conservative component and initial-stock boxes. Open enclosure space,
imported voids and removed material remain occupied in these envelopes. Contact
pairs are never omitted automatically. Missing holder geometry is identified as
unknown. Pending drafts, changed selections, changed/unreadable CAD assets,
cancellation and body-budget exhaustion preserve the prior declaration.

Verification compares captured frames against independent viewer poses at three
machine positions, selected component overrides, tilted stock, rotated/translated
movable jaws, every repeat stock, retained tool definitions, exact source changes,
bounded provenance, cancellation, asset mismatch and no silent truncation.
Rendered workflows cover explicit capture/review/save/source comparison and stale
capture refusal at narrow/wide widths. Shared disclosure headers now wrap, grow
to fit their text, and retain left alignment across resize; existing surface
planning and heading-reveal workflows are included in the regression pass. Readonly actual local C1/Saunders/Mod Vise
CAD capture also produces 16 bodies with synthetic tool/stock declarations;
that observation is not installed runtime or physical acceptance. Focused suites
pass 158 distinct unit identities and 33 rendered identities. Five core modules
pass strict typing; the 262-file application baseline, both architecture contracts
and repository lint/format checks pass. Earlier failed attempts remain retained.
Receipt: `/Users/wes/.codex/artifacts/carvera-scene-clearance-20261009/source-verification.json`.

The source/rendered connection is a separate checkpoint. Exact surface contact,
complete multi-tool program machine-collision playback, measured registration,
rotary subtraction, installed/native acceptance, hosted CI, camera synchronization,
adaptive actuation, advanced-machine adapters and physical qualification remain
OPEN. The full original 25 plus accepted supplementary overhaul goal stays ACTIVE.

## C1 continuous triangle-surface refinement — bounded source/rendered scope, 2026-10-09

Program machine clearance now offers a separate CAD triangle-surface review for
all loaded source motion or a selected operation. It refines every candidate
body pair over its complete original chord, retaining imported CAD/stock faces,
original triangle IDs, source parameters and curve-error enclosures. Continuous
rational projection intervals and a triangle BVH cover between-endpoint and
coplanar contact without time sampling or decimation. A small outward numerical
allowance precedes the rational tests. Identical machine/workholding/stock meshes
are shared only after the required tool captures pass the same-scene check;
per-tool spindle registration and rotating tool envelopes remain separate.

The workbench pages contacts and explicit remaining gaps, shows the selected
triangles in equal-scale XY/XZ projections and links the retained source line.
Shared cancellable workers reject stale source/settings/range/scene completion.
Result labels settle before publishing compact card height, preserving narrow
coverage disclosure behavior. Save body review exchanges only the separately
recomputed declared-body report; reopening clears local triangle results.

This is an independently closeable source/rendered increment, not full solid or
physical clearance. Surface separation does not exclude solid containment.
Rotating cutter/shank/holder geometry retains conservative envelope results;
removed-stock geometry, uncertified curves, unresolved/backend/ATC motion,
measured registration, dynamics, installed/native acceptance, hosted CI, camera
synchronization, adaptive actuation and advanced-machine adapters remain OPEN.
The complete original 25 plus accepted supplementary overhaul goal stays ACTIVE.
Verification and publication receipts are retained under
`/Users/wes/.codex/artifacts/carvera-surface-clearance-20261009/`.


## Closed-solid occupancy — bounded source/rendered checkpoint, 2026-10-09

The CAD surfaces & solids review now admits closed manifold triangle meshes and
classifies the intervals between complete continuous possible surface contacts.
Separation checks every connected boundary shell in both directions; containment
retains its first shell witness. True cavities and
disconnected components remain represented. Open, duplicate, self-intersecting,
degenerate or inconsistently wound geometry retains an explicit pair gap. The
shared stock geometry engine supplies the validation without claiming file
provenance for machine meshes or silently repairing imported geometry.

The workbench pages contained/separated intervals alongside retained triangle
contacts and gaps. Containment details identify a shell face, nominal world
witness and original source interval; separation explains its admitted-solid
scope. Existing source links, cancellable workers, stale-result rejection and
body-only review exchange remain in place. Closed contact boundaries and open
neighboring solid intervals preserve the conservative contact enclosures.

Source/rendered verification receipts are retained under
`/Users/wes/.codex/artifacts/carvera-solid-clearance-20261009/`.
This bounded increment does not close rotating-tool occupancy, removed-stock
coupling, portable triangle/solid replay, uncertified/backend/ATC motion, measured
registration, installed/native acceptance, hosted CI or physical qualification.
The original 25 plus accepted supplementary controller overhaul remains ACTIVE.

Readonly admission of the actual local C1/Saunders/Mod Vise asset prepared all
123,594 surface triangles. The first ATC component admitted six closed shells;
the second exhausted the shared 250,000-pair solid budget. The full assembly
therefore remains unqualified for solid occupancy; no partial assembly result
was accepted. Optimizing admission while preserving complete geometry and the
whole-operation limits is a separate next step.


## Complete-CAD admission optimization — bounded source/rendered checkpoint, 2026-10-09

Closed-solid admission now uses exact integer plane and coplanar-edge certificates
before the full rational triangle predicate. It retains the original binary64
coordinates, shared-boundary rules and every face. A cancellable twelve-bin
surface-area tree reduces overlapping branches; floating-point costs select
only its layout. Tree traversal and cheap certificates share the existing two
million validation-step limit. Inconclusive full predicates retain the 250,000
pair limit. Ray/query limits, whole-operation refusal and legacy stock admission
accounting remain unchanged.

The standalone C1 converter now preserves position coordinates at full binary64
precision. Its former post-area-check rounding could collapse a small valid
facet. Regression cases include adjacent representable coordinates, subnormal
facets and large finite coordinates. True zero-area faces are retained for
explicit admission failure; missing face triangulation refuses conversion.
The existing installed CAD asset has not been regenerated by this source fix.

Verification receipts are retained under
`/Users/wes/.codex/artifacts/carvera-solid-admission-20261009/`.
Four hundred distinct unit identities, 28 rendered workflows, four strict core
modules, the 269-file application typing baseline and both architecture contracts
pass. Earlier failed attempts and real-CAD diagnostics remain retained.
Readonly replay of all 123,594 prepared triangles now admits all four ATC
components, the carriage, the complete 99,760-triangle Saunders plate and the
spindle. The plate admits one closed shell with nominal material volume
1,327,543.5362807112 mm³. The complete review then exhausts the unchanged shared
250,000 full-predicate limit at the first Mod Vise component (1,885,704 validation
steps used). No partial assembly result is accepted, and later components were
not attempted. The bed mesh is open/nonmanifold. The exact source/asset/snapshot
identities and counters are retained in `actual-replay-readback.json`.
The original frame contains four exact degenerate facets (zero-based IDs 1301,
1302, 5247 and 5248). They remain unavailable in the existing asset. The rounding
regression establishes a conversion failure mode; attribution of those specific
facets requires exact-source regeneration and readback.

This increment does not establish complete assembly admission, regenerated CAD,
rotating-tool/removed-stock occupancy, portable triangle/solid replay, measured
registration, backend execution, installed/native acceptance, hosted CI, camera
synchronization, adaptive actuation or physical qualification. The full original
25 plus accepted supplementary controller overhaul remains ACTIVE.


## Exact plane-line admission certificates — source/rendered checkpoint, 2026-10-09

The closed-solid fast path now computes exact triangle/plane cut intervals along
the intersection of two nonparallel triangle planes. Binary64 positions retain
the common integer embedding. Numerator/positive-denominator endpoints and cross
multiplication prove strict interval separation without floating division,
normalization, epsilon or time sampling. Any exact endpoint contact or overlap
retains the original full rational predicate and shared-boundary classification.
Solid-review leaves hold at most 16 complete faces, reducing tree visits while
retaining and charging every overlapping candidate. The legacy stock tree keeps
its eight-face leaves and original accounting. Whole-review limits are unchanged.

Analytic tests exercise sign reversal, zero-distance vertices/edges, nonintersecting
cuts, endpoint touch, crossing, adjacent binary64 values, subnormal coordinates,
axis permutations and winding reversal. The previous random comparisons against
the independent full rational predicate, cancellation, fallback budget refusal,
complete spatial-tree geometry and stock/program workflow regressions remain.

The exact-source actual-CAD replay, unit/rendered and publication receipts are
retained under `/Users/wes/.codex/artifacts/carvera-line-separation-20261009/`.
The actual source-bound replay now attempts every one of the 14 prepared meshes
(123,594 triangles) within the unchanged shared caps: 1,838,674 validation steps
and 100,698 full predicates. All four ATC components, carriage, complete Saunders
plate, spindle, all four fixed/adjustable Mod Vise components and nominal synthetic
stock admit. The plate full-predicate count falls from 239,603 to 92,228 on the
same retained triangles; its validation steps fall from 1,782,495 to 1,535,931.
The frame remains unavailable because of four degenerate facets; the bed has four
edges with four incident faces each. This closes the current asset's processing
budget bottleneck, not full assembly geometric admission. No partial assembly
result is accepted. An interrupted process with no completion receipt remains
preserved separately; one replacement after independently verified process
absence produced the final source/asset-bound receipt.

426 distinct unit identities, 28 rendered workflows, four strict core modules,
the 269-file application typing baseline, both architecture contracts and lint/
823-file formatting pass. Exact original v9 machine STEP bytes have also been
located and hash-verified; regeneration and solid decomposition remain OPEN.

Complete assembly geometry, installed/native behavior, measured registration,
rotating-tool/removed-stock coupling, portable surface/solid replay, backend/ATC
motion, camera synchronization, adaptive actuation, advanced-machine adapters,
hosted CI and physical qualification remain separate OPEN gates. The full
original 25 plus accepted supplementary controller overhaul stays ACTIVE.


## Original STEP solid boundaries — source checkpoint, 2026-10-09

The standalone C1 converter now keeps each native STEP solid as a distinct
component. It retains assembly/motion group, full-precision coordinates, source
component name, native solid index/count and source-local face IDs. A face-
occurrence census compares the complete source shape with all extracted solids;
missing/orphan faces refuse conversion. Surface-only source components remain
explicitly labelled and retain every face. No mesh connectivity guess, Boolean
union, welding, tolerance repair or face omission substitutes for source topology.

Readonly original v9 STEP diagnosis confirms the earlier geometry gaps. The frame
has 5,570 complete nondegenerate triangles at full precision. The 84-triangle bed mesh
is a compound of three native solids, each with 28 triangles and valid edge
incidence; its aggregate has four edges with four incident faces. The regenerated
frame and each native bed solid pass complete geometric admission independently.
This uses the existing OCCT 8.0.1 conversion environment without installing a
new runtime. Ten native OCCT tests exercise touching faces/edges/vertices, separate
solids, full coordinate transforms, aggregate refusal, surface-only sources,
orphan/missing face refusal and immutable profile-loader interoperability.

The complete in-memory candidate replaces only the frame and bed from that
original STEP; the selected asset's ATC, plate, vise and moving assemblies remain
unchanged. Ordinary controller coordinate preparation produces 18 bodies and
16 surface meshes, retaining all 123,594 triangles. Every mesh admits under one
unchanged shared budget: 1,929,627 validation steps and 101,816 full predicates.
This closes geometric admission of this source-bound in-memory candidate; it
does not prove measured registration, dynamic clearance or a persisted asset.
426 regression tests, ten actual native CAD tests and 28 rendered workflows pass,
along with four strict core modules, the 269-file application typing baseline,
both architecture contracts, lint and 824-file formatting.

Exact source hashes, original topology diagnosis, in-memory scene admission,
unit/rendered validation and publication receipts are retained under
`/Users/wes/.codex/artifacts/carvera-cad-solids-20261009/`.
The selected CAD asset, machine settings and installed DESKTOP324 remain unchanged.
Complete persisted-asset regeneration, installed/native acceptance, backend motion,
measured registration, camera synchronization, adaptive actuation, rotating-tool/
removed-stock coupling, portable surface/solid replay and physical qualification
remain separate gates. The full original 25 plus accepted supplementary controller
overhaul remains ACTIVE.


## Portable CAD surface and solid review — source/rendered checkpoint, 2026-10-09

The CAD surfaces & solids card now has separate Save surface review… and Open
surface review… actions. `.cvsurfacereview` retains exact parser text/settings,
work offsets, selected range, detached body declarations, prepared triangle
geometry with cross-tool sharing, rational contact/source intervals, closed-solid
containment/separation, witnesses, numerical counters and remaining coverage
gaps. Opening reparses the source, rebuilds every mesh index and recomputes all
body/surface/solid claims. Both save and open run through the existing cancellable
worker. A stale file picker or generation change cannot publish an old result;
invalid or cancelled exchange preserves previous state. Active program, scene,
tool library, datums and controller state are preserved on detached open.

The format is bounded to 64 MiB, 250,000 unique triangles, 4,096 meshes and the existing
whole-review solver budgets. Exact numerator/denominator strings retain binary64
rational evidence and endpoint closure. Mesh/body references are validated at
zero-joint registration, with the existing1e-6mm numerical allowance. Complete
geometry is bound to the result, so a rehashed geometry edit cannot reuse earlier
contact or occupancy evidence. Retained prepared declarations and scene IDs do
not independently certify original CAD provenance or physical registration.

The corrected in-memory actualC1 scene transports every one of its16meshes and
123,594triangles through this format with exact face/body binding and sharing:
17,208,210serialized geometry bytes. This is full geometry transport, not an
actual-program surface/solid replay-solver claim. Native geometry/profile bytes
and the installed DESKTOP324 remain unchanged. Source/test/publication receipts
are retained under `/Users/wes/.codex/artifacts/carvera-surface-replay-20261009/`.

Installed/native acceptance, complete actual-program replay qualification,
rotating-tool/removed-stock coupling, persisted CAD adoption, measured camera
registration/synchronization, backend/ATC execution, adaptive actuation,
advanced-machine adapters and physical qualification remain OPEN. Packaging
waits for admitted storage. The full original25 plus accepted supplementary
controller overhaul remains ACTIVE.

110 unit tests and 32 rendered workflows, two strict surface modules, the270-file
application typing baseline, both architecture contracts, lint and827-file
formatting pass. Current360/800px exchange screenshots have been inspected.


## Continuous surface indexing and replay compatibility — source/rendered checkpoint, 2026-10-09

Continuous contact review now uses a cancellable twelve-bin surface-area tree
with two-face leaves and bounded balanced fallback. Float costs only choose
partitioning; original faces and IDs remain complete, and exact rational box
intervals still prove separation. Coordinate axes precede lazily constructed
face, edge-cross and coplanar axes. Independent full-axis rational oracles cover
random translations, error allowances, permutations, subnormal coordinates,
degenerate geometry and exact endpoint contacts.

New portable reviews declare the v2 index method. Existing v1 files rebuild
the original eight-face median tree so their numerical work counters remain
reproducible. Resaving an opened v1 file preserves its method. A fixture written
by the original published a06f926 production writer replays with its original
30 node visits, 576 triangle pairs and solid work counters and resaves
byte-for-byte. Rehashed method changes and mixed-index saves refuse exchange.

A complete synthetic thin-cluster case returns the same 18 exact contacts and
original face IDs with both methods: 241 triangle-pair tests for the median
tree and 30 for the new tree. It now completes within a 100-pair test allowance
that refused the old tree. This proves less pair work for that case; it does
not claim a general wall-time speedup.

The full nominal C1 diagnostic retains all 16 prepared meshes, 123,594 faces and
18 bodies, including the native Frame/Bed replacements. It uses a one-mm test
move and synthetic tool/stock, without excluded mounting pairs. The original
index refused at 100,000 triangle pairs. The indexed candidate reached
137,953 node visits and 20,419 triangle pairs, completed solid admission with
1,930,347 steps, 101,816 full solid pairs, 712 rays and 41 queries, then refused
at the separate 10,000-contact limit while comparing fixture 7 (INCH Plate)
with table 3 (a native Bed solid). No partial report or portable replay was
published. The diagnostic precedes the subsequent error-context wording change;
its exact candidate hashes and patch are retained in the evidence folder.
These are nominal geometry contacts, not evidence of a physical collision.

A typed surface-budget exception now distinguishes work exhaustion. Program
review adds source line, tool, body names and both work-counter summaries to
surface or solid budget errors. The existing worker displays that context,
restores its controls and withholds incomplete results. Mounted pairs are not
automatically allowed and limits have not been raised.

Verification covers 257 distinct unit cases across the broad suite and final
additions, 33 rendered workflows, three strict modules, the 270-file application
typing baseline, both architecture contracts, lint and 828-file formatting.
Receipts, the preserved first pair-limit refusal, indexed contact-limit refusals
and the older-file fixture-generation correction are retained under
`/Users/wes/.codex/artifacts/carvera-actual-surface-replay-20261009/`.

CLOSED: this source/rendered index, compatible exchange and diagnostic-error
increment. OPEN: complete actual-scene refinement/replay within bounded contact
reporting, explicit mounted-contact review, rotating tool/removed-stock coupling,
measured camera registration/synchronization, backend/ATC execution, adaptive
actuation, advanced-machine adapters and physical qualification. Owner: controller
lane. Next: address the actual plate/bed contact representation or explicit
review policy without silent exclusions, then qualify the complete report.
WAITING: packaging and installed acceptance need admitted storage plus the
immutable first-helper gate. DESKTOP324 and selected CAD asset bytes are unchanged.
The full original25 plus accepted supplementary controller overhaul remains ACTIVE.


## Exact interval contact groups — source/rendered checkpoint, 2026-10-10

The CAD surfaces & solids workbench defaults to Exact interval groups, with
Individual triangle contacts available explicitly. A group combines only
identical rational intervals for one body pair and original program segment.
Every original face-pair member remains retained; distinct, adjacent and
tolerance-near intervals are never combined. The inspector exposes complete
body/source identity and pages members in batches of 64, preserving original
faces and XY/XZ nominal chord projections at narrow and wide widths. Mode
changes invalidate prior evidence and busy controls use the cancellable worker.

This is a separate bounded representation: at most 10,000 groups and 100,000
total member pairs. The original individual-contact API retains its unchanged
10,000-contact guard. Both modes retain the same two-million-node/100,000-pair
work limits, complete exact predicates, shared solid budgets and complete
continuous occupancy partition. No mounting pair is excluded or approved.

Grouped portable exchange declares a distinct v3 method, reparses retained
source, rebuilds all meshes, and recomputes every group, member, interval, solid
witness, gap and counter. Edited/rehashed evidence refuses replay. Older v1/v2
reviews preserve their original method/accounting and byte-stable resave. Unit
coverage compares complete expansion with independent full-axis rational
predicates, exercises more than 10,000 retained members, shared limits,
containment/cavities, modal/source parameters, arcs, splines and NURBS. Rendered
workflows cover member paging, detached save/open/resave, active setup retention
and mode invalidation without controller writes.

The full nominal C1 diagnostic retained all 16 meshes, 123,594 triangles and
18 bodies, including native Frame/Bed replacements. The one-mm diagnostic uses
synthetic tool/stock and no exclusions. Grouping reached 50,305 original contact
members in four exact groups before the unchanged 100,000-triangle-pair work
guard refused the whole review on fixture 7 (INCH Plate) / table 3 (native Bed).
It visited 391,362 surface nodes; solid work was 1,930,347 steps, 101,816 pairs,
712 rays and 41 queries. No partial report or full actual-scene portable replay
was published. These are nominal geometry contacts, not physical collision proof.
The selected CAD/native STEP bytes and installed application were not changed.

Verification: 279 distinct unit cases, 36 distinct rendered workflows, four
strict core modules, the 270-file application typing baseline, both architecture
contracts, lint and 831-file formatting. Expanded inspector screenshots are
checked at 360/800px. First failed test-helper attempts remain preserved.
Receipts: `/Users/wes/.codex/artifacts/carvera-contact-groups-20261010/`.

CLOSED: exact grouped representation, complete member inspection and versioned
portable replay source/rendered increment. OPEN: complete actual-scene refinement
and replay within existing work limits, explicit mounted-contact acceptance,
rotating-tool/removed-stock coupling, measured camera registration/synchronization,
backend/ATC execution, adaptive actuation, advanced-machine adapters and physical
qualification. Owner: controller lane. Next: improve bounded plate/bed pair
search with independently checked exact certificates, then repeat the complete
nominal report and replay. WAITING: packaging/installed acceptance need admitted
storage and the immutable first-helper gate. The full original25 plus accepted
supplementary controller overhaul remains ACTIVE.


## Exact directional contact search — controller continuation, 2026-10-10

Current contact preparation retains every original face in a single-face
surface-area leaf and exact projections along eighteen fixed integer directions.
Parent bounds union complete child projections. Continuous culling intersects
those complete closed intervals with the original coordinate slabs, including
the original position allowance scaled by each exact L1 norm. A surviving
leaf pair remains charged before the full triangle predicate. No mounting pair
is permitted/excluded and all existing whole-review bounds remain unchanged.

The original coordinate slabs use direct exact endpoint arithmetic. Static
triangle queries use the same complete SAT family on a common exact integer
grid, retaining padding and closed endpoints; moving triangles retain rational
intervals. Node bounds can prove empty portions of former conservative boxes,
including degenerate geometry. Every original face remains retained and
unavailable solids keep their explicit gaps. The workbench coverage card shows
the retained index method. Directional raw/grouped reviews declare distinct
v4/v5 methods. Published v1/v2/v3 reviews reconstruct their original indices and
accounting; the original production-writer fixtures resave byte-for-byte.

Independent rational/analytic cases cover random motion/static comparisons,
subnormal coordinates, axis permutations, padding and exact endpoints,
degenerate false box contacts, complete hierarchical projections, budgets and
cancellation. Rehashed methods and result/membership changes cannot reuse
evidence. Source and rendered workflows cover the full grouped/individual
exchange, member/source inspection, active setup retention and responsive
360/800px inspector layouts. The exact final source passes 322 unit cases, 36
rendered workflows, six strict core modules, 272-file application typing, both
architecture contracts, lint and 836-file formatting.

The isolated repeated coplanar static comparison made 2,000 calls: 5.208s using
the rational implementation versus 0.199s for the integer helper on prevalidated
points. This is a limited helper benchmark, not a whole-job/native speed claim.
Initial actual-profile measurements showed that single-face leaves alone and
six directions alone barely reduced candidate work. Combined six directions
reduced the plate/Bed pair to 94,265 candidates but the complete review still
refused at 100,000 shared pairs. Eighteen directions reduced that pair to 78,808.
The preserved preformat candidate completed full nominal refinement within the
work bounds; its diagnostic tracing wrapper then failed on rebuilt mesh IDs
during portable replay. That helper failure is retained and does not qualify
replay. The final-source helper restores the original production pair function
before reopening and is qualified as a separate operation.

The final-source nominal whole-scene refinement and independently recomputed
portable replay are CLOSED at source. The hybrid actual C1 geometry retains
all 16 prepared meshes, 123,594 triangles and 18 declared bodies; the one-mm
synthetic-tool/stock diagnostic checks 37 body candidates. Complete refinement
uses 1,163,206 surface nodes and 97,345 triangle pairs inside the unchanged 2M-node
and 100K-pair limits. It retains 8 groups with 77,362 original face-pair members,
22 solid intervals and 7 explicit gaps. The 18,090,242-byte in-memory v5 review
reopens and reproduces the complete report exactly. Its payload SHA256 is
`35e58a6cdafb1957ab4eed447a2c75a9653bec444f8cced22a5791bf2819ed06`.
The receipt is
`/Users/wes/.codex/artifacts/carvera-fine-surface-index-20261010/actual-final-direction-replay.json`.

This closes only the nominal full-scene work-limit/replay diagnostic. Native
Frame/Bed geometry was substituted in memory from the source STEP; the selected
installed CAD profile was not changed. The nominal program, synthetic cutter
and stock do not qualify the user's real cutting job, rotating-tool/material
removal coupling, measured registration, backend or physical execution. No
partial results, mounting exclusions or increased budgets were used.

The original 25 plus accepted supplementary overhaul remains ACTIVE. Measured
registration, actual-job/rotating-tool/removed-stock coupling, backend/ATC
execution, adaptive actuation, advanced-machine adapters and physical
qualification remain OPEN. Packaging/installed acceptance WAIT for admitted
storage and the immutable first-helper gate; installed DESKTOP324 remains
unchanged. Controller lane owns these scopes.


## Continuous declared rotating assemblies — source/rendered checkpoint, 2026-10-10

Loaded tool definitions now carry their declared cutter, shank and holder axial
sections into the same detailed whole-program review. Their exact continuous
queries use the complete axial/barycentric/time prism projected into the radial
plane for triangles, and exact axial intervals plus radial minimization for
parallel cylinders. Node-box certificates reject only complete empty bounds.
All sections are reviewed, using the same original surface/solid work budgets.
No time/angle sampling, polygonal circle approximation, skipped mounting pair,
changed bound or partial report is used. The original C1 tool-base translation
is included; tilted/rotated tool frames refuse this +Z method.

A positive query retains one exact rational existence witness per section,
with its source parameter and original obstacle face or other section. It is
not first-contact time, a tool-boundary point, entry/exit interval or exhaustive
face membership. With no surface overlap over the complete chord, admitted
closed-solid material is classified by a center witness; unavailable topology
keeps an explicit unavailable state. Cutting contact remains reviewable and is
not automatically permitted. Procedural cutting sections remain outside-radius
cylinders and existing CAD bands remain declared envelopes. Manufactured flute
shape, missing holder geometry, dynamic removed stock and physical registration
are separate open requirements.

The workbench places these states beside existing triangle contacts, groups,
solid intervals and gaps. Detail inspection shows the source-bound height/radius,
world witness and source parameter; XY/XZ projections mark the witness in red.
Source navigation and detached save/reopen preserve current profiles, datums and
scene. Current raw/grouped reviews use distinct v6/v7 methods with complete
section/body/tool bindings in the geometry digest. Existing v1 through v5
readers reconstruct their original review semantics. Unmodified published
69cdd2b production-writer v4/v5 dense-contact fixtures retain 144 face pairs,
original counters, gaps and groups and resave byte-for-byte.

Final source passes 359 unit cases, 38 rendered workflows, strict typing across
all 137 machine-layer files, 274-file application typing, both architecture
contracts, lint and 842-file formatting. Published v1/v2/v3 and the unmodified
69cdd2b v4/v5 production-writer fixtures retain their original semantics and
resave byte-for-byte. The two rendered rotating-witness layouts were independently
inspected at 360 and 800 pixels. A diagnostic launch import-path failure is
preserved separately; both processes were terminal before the corrected launch.

The bounded nominal whole-scene declared-rotation refinement and portable replay
are CLOSED at source. All 16 prepared hybrid actual-C1 meshes, 123,594 triangles and
18 bodies remain included. The one-mm synthetic-tool/stock program has 37 original
body candidates. Complete refinement uses 1,163,354 surface nodes and 97,371 shared
primitive-pair checks inside the unchanged 2M/100K limits. It retains 8 triangle
contact groups with 77,362 original face pairs and 22 solid intervals. It reports
7 rotating-section outcomes (1 possible contact, 0 contained, 6 separated, 0 unavailable) and
0 remaining legacy pair gaps. The 18,092,610-byte v7 payload independently
reopens and reproduces the complete report exactly. Payload SHA256 is
`5a5a5fb34e61204dd38d3389795f4845edbeccb3fd78f657b038f361194f872a`.
The terminal receipt is
`/Users/wes/.codex/artifacts/carvera-rotating-clearance-20261010/actual-rotating-replay.json`.
Native Frame/Bed components were derived in memory from the source STEP; no
selected profile or full geometry artifact was written. This closes the declared
nominal diagnostic, not the real cutting job or installed/physical qualification.

The original 25 and accepted supplementary controller overhaul remains ACTIVE.
Actual loaded physical tools/cutting jobs, shaped-flute/removed-stock coupling,
measured camera/machine registration, backend/ATC and adaptive execution,
advanced-machine adapters and physical qualification remain OPEN. Packaging and
installed acceptance WAIT for admitted storage and independent immutable helper
qualification. The installed DESKTOP324 and selected CAD profile remain unchanged.
The controller lane owns the next source action; no machine actuation occurred.

## Shaped cutter continuity — source/rendered checkpoint, 2026-10-10

Loaded ball, drill, chamfer, engraving and supported tapered profiles now replace
the full-diameter cutting cylinder with their complete nominal spherical-cap,
increasing-cone and cylindrical pieces in detailed surface review. Exact rational
quadratic minimization enumerates every independent feasible face of the complete
axial/barycentric/time polytope. Endpoints, caps, degenerate triangles, tangent
edges, triangle interiors and shared diagonal timing retain exact witnesses.
No temporal stepping, tessellated circle or numerical optimizer is used.
Position/curve allowances remain outward and original whole-review budgets
remain unchanged. Original C1 tool-base registration is retained.

The workbench shows the primitive, sphere center/radius or cone endpoint radii,
source-bound declaration and red world witness. Detached source inspection and
save/reopen retain active profiles, scene and datums. v8/v9 reviews retain complete
primitive parameters and recompute the same report. Unmodified published v6/v7
cylinder writers retain their original semantics and byte-exact resaves, alongside
existing v1–v5 compatibility. Assembly pairs retain outer-cylinder envelopes and
state that limitation explicitly. Bull corners, thread teeth and arbitrary CAD
flutes remain open requirements; nominal rotational profiles are not manufactured
flute geometry. Initial stock is not dynamically removed material.

The evolving-stock engine now clips its swept ball to the lower hemisphere
and upper cutting cylinder using the same axial/radial time interval. Five
independent before-fix controls demonstrated excess removal above finite flute
length, including a diagonal move and fixed/tilted axes. Existing ordered stock
updates and cancellation remain; detailed C1 surface review still retains initial
stock and does not claim changing-material coupling.

Final source passes 503 unit cases and 40 rendered workflows, strict typing
across all 138 machine files and the changed stock engine, 275-file application
typing, both architecture contracts, lint and 846-file formatting. Analytic
controls independently compare complete point-chord quadratics, exact caps,
interior crossings, triangle interiors, tangent edges, subnormal coordinates,
position-error corners and short rounded tapers. Published v1–v7 methods retain
their original semantics; v6/v7 production-writer fixtures reopen/resave byte
for byte. Shaped witness layouts were independently inspected at 360 and 800px.

The first complete nominal shaped-C1 refinement/replay is preserved before the
short-tip correction. That correction is applied only after the original
producer/consumer operation is terminal. The exact final core is independently
qualified by a second complete refinement/replay; no duplicate active operation
or changed work limit is used. The final nominal diagnostic retains all 16
hybrid actual-C1 meshes, 123,594 triangles, 18 bodies and 37 broad-phase pairs.
It uses 1,163,410 nodes and 97,376 primitive-pair checks inside the original
2M/100K bounds, retaining eight contact groups and all 77,362 original face-pair
members plus 22 solid intervals. Its 12 shaped/rotating
section outcomes are 1 possible contact, 0 contained, 11 separated, 0 unavailable; 0 legacy pair gaps remain. The complete
18,095,167-byte v9 payload reopens and reproduces the entire report exactly.
Payload SHA256: `e014ff6722df233194014d54f43f9ce7ee5e5adf466d99c9e4e7ce0286d32b67`.
Receipt:
`/Users/wes/.codex/artifacts/carvera-shaped-clearance-20261010/actual-shaped-replay.json`.
The diagnostic uses a synthetic six-mm ball tool, synthetic stock and nominal
one-mm motion; real cutting jobs, changing material, measured registration and
physical execution remain unqualified. Source STEP/native Frame/Bed components
are derived in memory; no selected profile or full geometry artifact is written.

The original 25 and accepted supplementary overhaul remains ACTIVE. Real cutting
jobs and physical tool qualification, CAD flute/complex cutter shapes, evolving
remaining-stock coupling, measured registration, backend/ATC/adaptive execution
and advanced-machine adapters remain OPEN. Packaging/installed acceptance waits
for admitted storage and independent immutable helper qualification. Installed
DESKTOP324 and the selected CAD profile are preserved; no machine actuation.

### Ordered remaining-material review — 2026-10-10 source checkpoint

The CAD review now optionally includes ordered stock evolution, with retained
initial cell occupancy and explicit per-instance WCS transforms. Every resolved
move checks rapid cutters and non-cutting tool sections against the current
occupied cells before subtraction; cutting profiles estimate removal at cell
centers. Source-linked, paged history entries show before/removed/remaining
volume, contact estimates and equal-scale contact projections. The original
exact CAD report remains visible with its initial-stock interpretation.

Full history from source line 1 is required. Material on chords with nonzero
curve error or missing curve certificates is retained. All original unresolved,
ATC and physical-registration gaps remain. New v10/v11 portable files reparse
source and recompute both the exact CAD report and all material steps, verifying
tool/body/datum bindings and final occupancy before accepting a detached result.
Shared cell/work/result/archive limits refuse partial reports; cancellation
preserves prior results and never mutates retained initial declarations.

This closes the implemented source workflow for ordered cell estimates beside
detailed C1 review. Whole-physical-cell removal, real-job qualification,
manufactured flute meshes, measured registration and installed/backend/physical
acceptance remain OPEN; the broader overhaul remains ACTIVE. Historical exact
CAD and nominal diagnostics above retain their original scope and receipts.

Verification for this checkpoint: 530 focused unit tests and 44 rendered source
tests pass; strict machine typing covers 139 files, application typing 276 files,
and both architecture contracts pass. Imported closed-cavity stock, fixed stock
tilt, multiple WCS instances, ball-to-flat tool changes, conservative rapid/shank
contacts, bounded/cancelled work, rehashed tampering and v1–v9 compatibility are
covered. The final occupied-cell wireframes were visually inspected at 360/800px.

The single immutable nominal actual-C1 refinement/replay retains all 16 hybrid
meshes, 123,594 triangles, 18 bodies and 37 body candidates. It uses 1,163,410
surface nodes and 97,376 pair checks inside the original 2M/100K limits, retaining
eight groups with all 77,362 original face-pair members and 22 solid intervals.
Its ordered estimate accounts for 3,000 conservative cell-work units at 1mm
resolution; this nominal move removes zero cells and leaves the declared 1,000mm³
stock unchanged. This diagnostic proves coupled recomputation, while engaging
removal/later-stock contacts are verified separately by analytic controls.
The entire 18,097,642-byte v11 payload reparses and reproduces both reports.
Payload SHA256: `74cc0db1ecdf7fe78ddceb73d7c424def98ec0d2bb53f86ff4b9387c70f0abd0`.
Receipt: `/Users/wes/.codex/artifacts/carvera-ordered-stock-20261010/actual-ordered-replay.json`.

Temporary shared UI/typing dependency directories lost source files during this
checkpoint. Their refusals are preserved. Verification continued using an intact
existing mypy 1.19.1 runtime and the signed DESKTOP324 bundle's existing dependency
code/assets read in memory for source tests. No dependency installation, bundle
mutation or duplicate nominal operation occurred. This does not close installed
workflow acceptance; storage admission and independent packaging qualification
remain required.


## Ordered-stock section inspection source checkpoint — 2026-10-10

Requirement 16 now exposes before/after material sections for a selected retained
move. Previous/next navigation follows the same stock instance across all resolved
moves, including other datums and tool changes. XY/XZ/YZ planes and explicit cell
layers use the stock's own local axes. Both panes share scale and complete grid
bounds; green remains, amber was removed by this move and dark was already empty.
Existing cavities and prior cuts never become new removal. Small layouts retain
both proportioned images; detailed frame/estimate limits are collapsible.

A background worker reconstructs the prefix once and then the selected move.
Both calculations share the original 50-million cell-work limit and validate
stock/tool/body declarations. Recomputed steps must match retained history; the
last move also checks complete final snapshots. Plane/layer/result/target changes
withhold stale delivery. Cancellation or a failed replacement retains the previous
complete section for unchanged options. Exact cell-run merging preserves voids
and disconnected material; 8,192 rectangles is a complete-section limit, with no
truncation or decimation. A million-cell section is covered independently.

The source regression passes 564 focused unit and 51 rendered cases, including
34 new analytic/admission/history tests and seven new rendered worker controls.
Machine strict typing covers 140 files; package typing covers 278 files, and the
new UI function bodies are checked. Both architecture contracts, lint and format
pass. The nominal full C1 scene/stock reconstruction retains all 123,594 triangles,
16 meshes and 37 body candidates and reproduces the earlier ordered stock in all
three section planes. The same one-mm synthetic diagnostic removes zero cells;
engaging removal and imported cavity sections are separately controlled.
Receipt: `/Users/wes/.codex/artifacts/carvera-stock-sections-20261010/actual-stock-sections.json`.
The earlier exact-CAD refinement and portable replay receipt remains CLOSED with
all 19 bound algorithms unchanged; it is not claimed as newly run evidence.

The first attempted broad test launcher exited without waiting: its child PIDs
were independently absent, empty logs and missing XML were preserved, and no
pass was inferred. The replacement owning launcher waited both processes to
exit0. No dependency install, full geometry persistence, controller command or
package/install mutation occurred. The installed controller remains DESKTOP324.
Storage admission and immutable package-helper acceptance remain waiting.
The original 25 and supplementary overhaul stays ACTIVE: measured registration,
real jobs/tools, physical clearance/removal, finishing decisions, advanced adapters
and adaptive execution remain separate open gates.
