# Workflow completion and advanced-machine requirements

The latest 25 recommendations extend the existing requirements ledgers. They do
not replace earlier requirements or treat existing partial foundations as complete.
The implementation goal remains active. Each workflow needs source validation,
installed interaction evidence and, where applicable, actual backend and physical
qualification. A machine profile declaration does not establish installed hardware.

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
is not included in that candidate.

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
