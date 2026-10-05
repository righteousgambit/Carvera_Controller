# Workbench responsiveness evidence

The Machine workbench's Connection health card reports the last tab callback,
its largest measured phase, the next Kivy clock turn, and the first window flip
notification after selection. These are separate observations. Callback entry
does not include the time from mouse/key input to dispatch. A window flip event
does not establish display presentation, camera freshness or machine response.

Navigation retains the latest 120 selections in memory. Each selection includes
local monotonic time, source/target section, callback duration, completion state
and measured phases: departure history, scene selection when applicable, keyboard
focus release, page activation, tab styling and arrival history. Failed callbacks
remain incomplete; a newer selection withholds later observations for the older
target. No field contents, program bytes or exception messages are captured.

The latest 60 periodic UI refreshes are retained separately. Total refresh time
includes all work; measured subphases include readiness, capabilities, tool
comparison, operation/tool-bank context and simulation inputs. The largest retained
refresh and its largest measured subphase are displayed. Uninstrumented work is
still part of the total, so the largest measured phase need not explain the total.

Spindle > Export diagnostics includes both sets of records with retention limits,
eviction counts and timing limitations. Capture performs no disk I/O, camera fetch,
additional status polling or machine command. Explicit export uses the existing
local diagnostics destination and readback. Disposal removes the flip observer
and cancels the pending clock observation.

Installed DESKTOP140 predates this instrumentation. Its tab observations include
computer-use bridge overhead; they do not resolve the reported freeze. The source
timings need installed/native exercise on empty and loaded programs, focused inputs,
and active camera viewing before deciding which path causes the stall. Passing
source regressions alone does not close that performance requirement.

Logical-size source correction: native Kivy on Retina returns framebuffer pixels
from Window.size, while its size setter/configuration use logical dimensions.
Repeated integration-test restoration previously doubled the window width.
Tests now use Window.system_size; application shutdown saves that logical size
directly rather than dividing framebuffer size by widget Metrics.dp. Five pure
regressions cover 1x/2x/3x framebuffer ratios and invalid dimensions. The affected
80-test suite passed; this fixes dimension semantics, not native tab responsiveness.


DESKTOP141 native observation (application source 02903ca, installed verification
2026-10-05T06:06:44Z): empty-program selections completed in about 1–2 ms
with subsequent clock/flip observations at 14–46 ms. Initial startup included
1.49 s to the next clock turn and 1.78 s to the flip notification. A local
44-line drill/thread preview then exercised Scene, Position, Setup, Spindle,
Console, Machine and Camera, plus leaving a focused camera-source field.
Loaded-case callbacks were 0.77–2.10 ms; clock turns 13.60–23.82 ms and flips
10.82–20.28 ms. These results do not include input dispatch or presentation and
cannot resolve larger-program, active replay or intermittent stalls.

Independent export readback and native observation receipt:
`/Users/wes/Downloads/carvera-desktop141-20261005/native-navigation-acceptance.json`.
The UI bridge timed out on both diagnostic saves, but independent destination
readback confirmed each completed. This does not prove the original tab freeze
was caused by export storage. The export code did perform synchronous encoding,
write and readback on the UI thread; subsequent source moves those operations
to a worker with a frozen observation snapshot, disables duplicate exports while
busy, and publishes completion/error only on the UI clock. A unique sibling
staging file is read back before atomic replacement; pre-publication failures
preserve the previous export and retain the failed staging file. Installed acceptance
of that worker change remains open.

Final atomic export regression: five tests passed (21.75 s), including frozen
observations, a blocked worker write while the UI clock advances, duplicate
suppression and failed staging readback preserving an existing destination.
Receipt: `/tmp/carvera-async-diagnostics-atomic-tests.log`. Ruff lint/format
passed; both architecture contracts were kept (210 files, 905 dependencies).
The broader first run retained 12 passes and 11 setup errors from a timed-out
requests/idna dependency import before full-app navigation checks executed.
Receipt: `/tmp/carvera-async-diagnostics-navigation-tests.log`. That failure
is not counted as navigation acceptance.

## Visibility synchronization feedback path

A broader ATC/scene regression passed 30 test bodies but hit a 60-second teardown
timeout while a periodic workspace refresh synchronized a visibility checkbox.
The checkbox invoked the scene toggle callback, which rebuilt all CAD batches.
The failed attempt and process sample are retained:

- /tmp/carvera-atc-target-ui-tests.log
- /tmp/carvera-atc-ui-process-sample.txt

Source now guards checkbox readback synchronization so it cannot invoke scene
editing/persistence callbacks. Unchanged group-visibility requests return before
rebuilding or refitting. A regression requires status readback to update the
checkbox without rebuilding geometry, saving setup or issuing machine commands.
This removes an observed feedback/rebuild path; native measurement is still
required before claiming the user's complete tab-switch freeze is resolved.

The replacement regression process is still live before collection, blocked in
Python initialization reading the external build environment's
`distutils-precedence.pth`. Its process sample is retained at
/tmp/carvera-atc-final-startup-sample.txt. The new synchronization regression
remains unverified until the owned run reaches a terminal result. No native
responsiveness closure is claimed.


Source follow-up removes reliance on checkbox callbacks to maintain outer-machine
framing: changing fixed-shell visibility updates the viewer framing declaration
directly. Camera fitting now reuses the rendered per-component bounds, rather
than rebuilding placement geometry and scanning every CAD vertex again. The
visibility regression requires fitting to avoid _machine_scene reconstruction.
The initial full scene rerun failed 5 tests (27 passed), including the latent
framing invariant and a marker getter read before Kivy processed a graphics frame.
Corrections remain pending full scene/native acceptance. Runtime migration and
preserved logs are documented in atc-inventory.md; no tab-freeze closure is claimed.


Verification follow-up: the internal-runtime scene/panel suite passed 34 test
bodies, with one teardown error from a test-only injected failure persisting
into geometry restoration. The fitting/visibility test now restores its mocks
before fixture cleanup. The corrected exact regression passed (20.42 s),
including finite fallback framing when rendered bounds are empty. Receipts:
/tmp/carvera-atc-internal-scene-final-tests.log and
/tmp/carvera-visibility-cleanup-final-tests.log. This closes the source regression
gap for visibility synchronization/cached fitting, not native tab responsiveness.


Native DESKTOP148 review identified a navigation defect: the Connection header
action selected Machine but left its controls below the capability panel. Source
ed05921 queues a guarded reveal of the Machines & connection card; opening ATC
review similarly reveals its controls. A real workspace regression passed
(18.26 s), verifying that Connect profile is visible and a subsequent task change
prevents delayed scrolling. Receipt: /tmp/carvera-connection-navigation-final-tests.log.
The first alignment assertion was too strict when scrolling is clamped; the final
check verifies the actual connection button lies inside the viewport. Installed
acceptance remains OPEN. Native artifact-browser delays and a connection loss
were observed; no attribution or full tab-freeze closure is claimed.

Artifact-browser filesystem checkpoint: constructor folder checks, navigation
validation/resolution, Jobs directory creation and selection existence checks now
run on a worker. Each dialog retains one active operation and at most one latest
pending request. Loading clears stale entries and disables selection; rejected
locations cannot select from the previous directory. Edited, superseded or closed
selections cannot dispatch a delayed callback. Callbacks remain on the UI clock
for existing workspace consumers. The final picker/connection suite passed 11
tests (18.45 s, one runtime SSL warning), including deliberately blocked path and
save checks while the clock advances, request coalescing, duplicates and stale
selection rejection. Receipt: /tmp/carvera-picker-navigation-final-tests.log.
Ruff lint/format and diff checks passed. Row construction and callback consumer
work are not made asynchronous by this change. Native responsiveness and the
reported intermittent tab freeze remain OPEN pending installed exercise.

DESKTOP149 installed/native checkpoint: frozen source 14498f872e15f04da463be6f00cb412bf75f4206,
474 installed files without mismatches, strict signatures passed. DESKTOP148
recovery retained. Native header Connection and ATC review reveal their controls.
The artifact picker populated the 242-item Downloads listing, resolved a full
receipt path and imported historical configuration through asynchronous selection.
A connection-loss popup recurred during path entry; automatic reconnection completed.
Bridge calls took several seconds and cannot establish input/presentation latency.
The original freeze remains OPEN; callback/row construction, native clipboard/input
and receive/poll behavior require evidence before attributing the cause. All nine
operator-store baseline entries matched. Receipt:
/private/tmp/carvera-desktop149-20261005/native-picker-navigation-acceptance.json.
Native save selection remains unexercised for this build. The import-architecture
checker was unavailable in the internal runtime (ModuleNotFoundError: importlinter);
/tmp/carvera-picker-import-contracts.log retains the attempt. No new import-contract
pass is claimed.

Receive-path source audit (9682056 source checkpoint): streamIO holds
_adaptive_lock while dispatching protocol messages. _observe_adaptive creates
its telemetry directory, encodes JSON and opens/writes its log under the same
reentrant lock. machine_response_age and diagnostics export also acquire that
lock. Thus filesystem latency can hold the receive loop and delay UI consumers;
this is source evidence of a blocking path, not attribution of the observed
connection loss. Next required implementation: bounded asynchronous telemetry
persistence with explicit loss/error/drain receipts, followed by a blocked-storage
regression proving fresh receive observations and UI clock progress. Preserve
heartbeat timeout and actual receive timestamps; do not suppress disconnects or
invent freshness to make the popup disappear.


Asynchronous telemetry persistence source checkpoint: monitor records now hand off
to a bounded 512-record background writer. Directory creation, JSON encoding,
open/write/flush and storage errors no longer execute on the receive thread or
under its monitor lock. The queue includes the in-flight record; saturation rejects
new records with explicit counts. Saved records retain connection generation,
sequence and preceding-loss counters. Storage failure abandons/counts pending
records, preserves any partial file and stops that log rather than duplicating
uncertain writes. Idle workers exit and restart on demand.

Spindle diagnostics show written/pending/lost counts and errors; diagnostics export
retains the writer snapshot. App shutdown stops admission and waits at most one
second, returning/logging queued/in-flight/drained/error counts. These shutdown
receipts are in memory/controller output, not a durable final recording manifest;
trailing losses after the last saved record require the diagnostics/shutdown
receipt. Flushed-to-OS counts do not prove fsync, power-loss durability or readback.
Neither storage state nor UI timings replace actual received-machine timestamps.

Final affected suite: 34 passed (15.57 s, one SSL runtime warning); process exited
zero. Blocked-storage coverage exercises status parsing under the actual receive
lock ownership and a Kivy-clock callback that reads received status age, without
transport commands. Queue saturation, frozen records, error/abandon counts, bounded
shutdown, idle-worker restart, saved gap sequence, reconnect generation and native
component-layout/diagnostics-export fixtures are covered. Receipt:
/tmp/carvera-async-telemetry-final-tests.log. Earlier passing run and Kivy teardown
warnings are retained in /tmp/carvera-async-telemetry-tests.log. Ruff lint/format
and diff checks passed. Installed/native validation and attribution/resolution of
the reported tab freeze remain OPEN.


DESKTOP151 installed/native telemetry checkpoint: frozen source
8d533eea02a7dd91ea587b61a27dadc8e7444827; installed at
2026-10-05T14:04:06.293880Z, 475 files without manifest mismatches and strict
signatures passed. DESKTOP150 recovery is retained. Native Spindle review displayed
background storage counts; native export to internal storage completed and independent
JSON/log readback verified the persistence snapshot and connection generations.
All nine operator-store baseline entries still matched. Receipt:
/private/tmp/carvera-desktop151-20261005/native-telemetry-acceptance.json.

The native responsiveness defect is not resolved: opening the export picker timed
out twice before recovering; path paste again triggered connection loss and automatic
reconnection. The saved observation stream contains a 73.671468959-second maximum
arrival gap in the retained initial readback. Zero log-queue losses does not mean
zero missed machine packets. During the stall, sample 75986 shows the main rendering
thread and other Python threads waiting in PyEval_RestoreThread, with one Python
thread inside lstat. This is a concrete process-wide blocking lead, not proven
attribution to a particular Python source call. Process sample:
/private/tmp/carvera-desktop151-20261005/native-export-process-sample.txt.
Next: qualify the exact blocking path and isolate filesystem work from the process
where needed; a thread alone cannot protect against an operation holding the GIL.
Do not suppress the received-status timeout. The app was left Live/Idle with fresh
reported status, no program selected and camera unavailable. No motion, upload,
tool change, offsets or calibration were issued. No original requirement closes.


Isolated artifact-browser source checkpoint: folder resolution/listing, Jobs creation
and selection existence checks now run in a separate metadata-only process. Source
and frozen worker entry points dispatch before Kivy/controller imports. Requests
have a four-second deadline and cancel on changed navigation/dismissal; the parent
retains at most two helper slots, including kernel-blocked children that cannot yet
be reaped. Timeout/error messages keep selection disabled and permit another
location. Existing one-active/one-latest scheduling and stale-selection guards remain.

A RecycleView replaces the 250-widget cutoff with reusable visible rows, preserving
all matching entries, folder-first sorting and selected filenames. Text is left
aligned and shortened to fit. The 1,500-entry rendered regression reaches the last
entry, filters back to the first, verifies rebinding and rejects selection after
dismissal. Final combined suite: 23 passed (27.72 s, one SSL warning); later frozen
stream/bootstrap adaptation: seven engine/bootstrap tests passed (2.05 s). Receipts:
/tmp/carvera-isolated-picker-final-tests.log and
/tmp/carvera-isolated-picker-bootstrap-tests.log. Initial scheduled-metadata test
interference and missing RecycleView layout binding failures remain retained.

This contains a class of process-wide filesystem stalls; it does not prove the
precise source of DESKTOP151's lstat/GIL sample or resolve all native tab freezes.
Frozen helper output, installed folder timeout/retry, native recycled-row behavior
and connected tab responsiveness require separate verification.

CAD startup work reduction (source checkpoint): full-app cProfile identified
synchronous default MachineProfile loading plus repeated per-vertex work_point
validation in the first rendered scene. Validated numeric vertex streams are now
copied directly into immutable tuples, preserving canonical JSON/fingerprints.
Rendering uses the already validated geometry and MachineSetup offset to apply
identical float translation/scale while retaining normals/colors and source buffers.

The initial affected run passed 40 tests and failed the pre-render full-machine
framing case. Uncomputed bounds were {} and therefore treated as a rendered empty
scene. Initialization now uses None; rendered empty {} remains a valid cached result.
The corrected framing/render/picking/rotation/tab suite passed 32 tests, one existing
SSL warning, 227.47 seconds. Logs: /private/tmp/carvera-cad-startup-tests.log and
/private/tmp/carvera-cad-startup-render-tests.log. No new import-contract pass is claimed.

Single-run instrumented comparison: profile loading 4.873 -> 3.713 seconds;
first scene build 2.838 -> 1.968 seconds; recursive freeze calls 3,201,207 -> 17.
Full fixture startup including fixed sleeps was 22.650 -> 22.238 seconds, so this
is not evidence of a large end-to-end startup improvement. cProfile adds overhead;
these runs suppress hardware/camera and are not installed/native latency proof.
Evidence: /private/tmp/carvera-startup-before.prof,
/private/tmp/carvera-startup-after.prof and
/private/tmp/carvera-startup-profile-comparison.json. Broader startup responsiveness
and all original complete requirements remain open.

## Deferred probing construction and settings isolation

The main workspace no longer constructs ProbingPopup or its preview/settings
panels during startup. First-use construction binds settings synchronously after
KV creation, initializes step controls from current jog mode, and retains the
same popup/settings on subsequent opens. Modal/jog readback tolerates absence
without constructing it. Probe selection for an ordinary cutter does not build
the probing workbench. The nullable Kivy property is explicit.

Source acceptance: 53 integration tests passed (55.72 s, one existing SSL warning),
including first opening before scheduled frames, keyboard-jog disable/restore,
continuous/step mode, retained edits, non-probe selection, workbench navigation
and focus safeguards. Another 83 probing/configuration tests passed (0.43 s).
Receipts: /private/tmp/carvera-lazy-probing-accepted-tests.log and
/private/tmp/carvera-lazy-probing-engine-final-tests.log. Initial import, inherited
disabled-state and nullable-property failures remain in the earlier logs.

Test-isolation incident: the old ConfigUtils hard-coded ~/.kivy instead of
respecting KIVY_HOME. The first retained-edit test changed the operator's saved
single-axis D setting to 4.25 mm. Its previous value is unknown and has not been
invented/restored. Review that diameter before physical probing. Evidence:
/private/tmp/carvera-lazy-probing-20261005/operator-settings-incident.json.
ConfigUtils now honors explicit KIVY_HOME, and the integration fixture separately
patches its directory. Subprocess tests verify isolated write/read and default
home compatibility. No physical probing or other machine action was performed.

cProfile confirms probing construction is absent from startup and reduces widget
construction from 4,807/1,556 to 3,553/1,551 total/primitive calls. Elapsed fixture
measurements varied with cache/load; they are not a native startup speed guarantee.
Other legacy dialogs, CAD preparation and first-use probing construction still
need responsiveness work. Packaging, installed first-use acceptance and the
complete intermittent freeze requirement remain open.

DESKTOP155 installed/readback: source 83781d6, independent manifest/strict-signature
verification passed; DESKTOP154 retained. Startup again timed out observation,
then the same PID 98227 rendered normally. Saved-profile reconnect and native
Scene/Setup navigation succeeded. A batched initial Setup selection only focused
the button; a subsequent single selection completed, so reliable complete input
latency is not claimed. Sequential profiled fixtures were 12.35 s for frozen
DESKTOP154 versus 10.85 s with deferred probing, including ~3 s of deliberate
fixture sleeps. These are cache/load-sensitive source observations, not native
startup timings. The installed startup timeout remains unresolved.
Receipt: /private/tmp/carvera-desktop155-20261005/native-startup-navigation-acceptance.json.

## Repeated assembly validation during scene restoration

Saved machine restoration seeded its scene twice. Each seed independently loaded
its machine-owned Saunders plate and Mod Vise references, revalidating millions
of coordinates from the same assembly. Startup now seeds once after successful
profile restoration. Component selection may reuse the loaded machine assembly
only when the resolved asset path and SHA-256 of current bounded file bytes match.
Different paths, changed bytes, missing files, invalid replacements and oversized
assets still follow validation or reject. No timestamp-only cache is used.

The real c1-v9-saunders-vise asset check compared all group vertices/indices,
canonical metadata and geometry/asset hashes: unchanged. Two complete reloads
took 4.358 s versus 0.0028 s for two verified reuses after the original load.
This is local data preparation timing, not an installed startup benchmark.
Receipt: /private/tmp/carvera-cad-reuse-real-asset.json.
Affected engine/integration suite: 24 passed (22.07 s, one existing SSL warning),
including actual machine selection and repeated scene restoration validating the
assembly once without commands. Receipt:
/private/tmp/carvera-scene-profile-reuse-tests.log. Ruff/diff checks passed.
Packaging/native acceptance remains open. Default-versus-selected loading,
background preparation, GPU publication and other startup work remain unresolved;
no complete responsiveness or original requirement is closed.

DESKTOP156 installed acceptance: package/source manifest and strict signatures
passed; native saved scene restored with no bridge timeout on the first launch.
getApp took 12.73 s and the following screenshot 0.94 s; these include automation
and observation overhead and do not prove input/presentation latency. Fresh
reported Idle status, Live mode and Scene navigation were observed after explicit
profile reconnect. The 18 post-incident stores matched. Camera remains unavailable.
Receipt: /private/tmp/carvera-desktop156-20261005/native-scene-restoration-acceptance.json.
Repeated restoration work is removed; startup/loaded-program/camera/replay
responsiveness and background CAD preparation remain open.

## Background machine-profile preparation

Startup restoration and the library's Use machine profile action now validate
CAD on one background worker, retaining one latest pending request. Current
machine/scene/connection metadata remains active during preparation. Completion
publishes on the UI clock only when its generation, owner and scene identity
still match. A newer request replaces the pending slot, direct selection
invalidates an older worker result, changed scene/recording context rejects
publication, and disposal suppresses late work. The library reports Preparing,
Loaded or failure only at the corresponding stage and avoids overwriting another
selected editor's status. No machine connection or command is issued by selection.

The broader affected suite passed 52 tests (64.46 s, one existing SSL warning),
including real CAD/component publication on the UI thread. A final 10-test
lifecycle suite passed (11.21 s), covering blocked-worker/UI-clock liveness,
bounded latest selection, invalid CAD, scene changes, shutdown, startup routing,
editor feedback and synchronous supersession. Receipts:
/private/tmp/carvera-async-profile-final-tests.log and
/private/tmp/carvera-async-profile-lifecycle-tests.log. Initial missing-ID test
failures are retained in /private/tmp/carvera-async-profile-tests.log.
Ruff/format/diff checks passed. All 18 post-incident operator-store entries matched.

This moves custom profile decompression/validation out of the UI callback;
it does not isolate GIL-holding filesystem operations into another process.
The viewer's initial default profile load, GPU publication, component selection
byte reads and Config.write remain synchronous. Native profile preparation,
loaded-program/camera/replay responsiveness and original requirements remain open.


DESKTOP157 native checkpoint: source 20dbf1829562231e0ac6ae1eb58f4a51317356d0,
476 installed files without manifest mismatches and strict signatures passed at
2026-10-05T15:19:55Z. DESKTOP156 recovery is preserved. Startup restored the
selected assembly and saved scene; the initial UI bridge still timed out and
recovered in the same PID. Native Use machine profile reported Loaded; transient
Preparing feedback was not captured. Explicit profile connection completed,
then Live/Scene and fresh reported Idle telemetry were observed. All 18
post-incident operator stores matched. Camera remains unavailable and the
unknown original probe diameter remains unresolved. Receipt:
/private/tmp/carvera-desktop157-20261005/native-profile-acceptance.json.
No motion, upload, tool change, offset or calibration was issued.

## One final scene build during profile publication

Profile publication previously built the imported assembly before workholding
placement, rebuilt after placement, then rebuilt after saved Scene restoration.
Publication now suppresses intermediate scene construction through the existing
visibility guard and restores the original visible/hidden state after the entire
selection. A visible scene is constructed/attached/fitted once with final setup,
components and stock; a hidden scene remains hidden. Failure restores visibility
while propagating the original error; this is not transactional metadata rollback.
Twelve lifecycle checks passed (14.88 s, one existing SSL warning), including
actual CAD publication on the UI clock, exact build count for visible/hidden
views and restoration after a rejected selection. Receipt:
/private/tmp/carvera-batched-profile-tests.log.
Packaging/native validation of this change remains open. The final GPU build,
initial default profile and other startup work remain synchronous.

The affected scene/workspace/profile-draft suite also passed 44 tests (78.45 s,
one existing SSL warning). Receipt:
/private/tmp/carvera-batched-profile-affected-tests.log. Ruff/format/diff passed.


DESKTOP158 installed/native publication checkpoint: source
5e5ee511db46d0eecb933f8bfc5d6f5176661f5a, installed at
2026-10-05T15:25:16Z; 476 files without mismatches and strict signatures passed.
DESKTOP157 recovery retained. Native Use machine profile reported Loaded and
rendered the saved machine, plate, vise and stock. Explicit reconnect completed;
Live/Scene and fresh reported Idle telemetry were observed. Same-process startup
again recovered after a UI-bridge timeout; the UI reported a 3.57 s largest
interval since launch, without attribution or input/presentation timing proof.
All 18 post-incident operator-store entries matched. Camera remains unavailable,
unknown original probe D remains unresolved, and the caught missing mdi_history
configuration traceback remains. Receipt:
/private/tmp/carvera-desktop158-20261005/native-profile-publication-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. This closes the
bounded installed profile-publication regression only; default CAD loading,
final GPU construction, comprehensive responsiveness and all 25 full workflows
remain open.


## Deferred default CAD preparation

Viewer construction no longer checks, reads, decompresses or validates the
optional default machine CAD. A scheduled worker prepares it after construction;
missing assets retain the schematic, invalid assets retain it with an error.
Publication runs on the UI clock only for the unchanged default owner, current
base profile and setup. A selected profile cancels scheduled default work and
invalidates an already-running default result; workspace disposal does the same.
Custom saved startup selections therefore prepare only their selected asset.
An empty CAD selection made before default preparation retains its former default
fallback behavior through the selected-profile worker; an existing base profile
is retained. No controller command or configuration selection is inferred by
loading the default. Loading is reflected in the machine-pane caption.

Twenty default/selected-profile lifecycle tests passed (21.18 s, one existing
SSL warning), including constructor-with-forbidden-I/O, deliberately blocked
worker/UI clock, superseded owner/profile/setup, missing/invalid default and
blank-selection fallback. Receipt:
/private/tmp/carvera-default-profile-corrected-tests.log. The original import-case
collection failure is retained in /private/tmp/carvera-default-profile-tests.log.
Final GPU construction remains on the UI thread. Installed/native startup,
loaded-program/camera/replay responsiveness and all 25 full workflows remain open.

Affected scene/workspace/profile-draft regressions passed 44 tests (75.86 s,
one existing SSL warning). Receipt:
/private/tmp/carvera-default-profile-affected-tests.log. Ruff/format/diff passed.


DESKTOP159 installed/native startup checkpoint: frozen source
de5f15bbefdca0ce4ffd4c0d2b087248945936c8, installed at
2026-10-05T15:33:16Z with 476 files without mismatches and strict signatures
passed; DESKTOP158 recovery retained. Saved custom assembly restored; native
profile-library selection reported Loaded and preserved machine/plate/vise/stock.
Fresh reported Idle telemetry and Live/Scene were observed. Initial UI-bridge
timeout still occurred and recovered in the same process; no startup speed
claim is made. Native default-only startup and transient loading-caption visual
acceptance remain open. All 18 post-incident operator stores matched. Camera
unavailable, unknown original probe D unresolved, caught missing mdi_history
traceback remains; no AttributeError or connection-loss event in the current log.
Receipt: /private/tmp/carvera-desktop159-20261005/native-default-preparation-acceptance.json.
No motion/upload/tool change/offset/calibration was issued. Default CAD I/O is
removed from viewer construction; final GPU construction, other startup work
and comprehensive responsiveness remain open. All 25 full workflows remain open.


## Profiled immutable CAD bounds

DESKTOP159 native startup was sampled in the same launch at PID 18145 for eight
seconds beginning approximately 0.49 s after launch. The sample completed with
exit zero; the UI bridge timed out and the same app recovered. The native C/Python
stacks show extensive Python startup work, but do not identify a particular
Python function. Receipt directory:
/private/tmp/carvera-startup-profile-20261005/.

A separate isolated source startup was profiled with cProfile. The measured
scene build spent 1.073 s in indexed geometry bounds (1.376 s total across two
scene builds). The full app build was 2.967 s; these are instrumentation- and
fixture-dependent source timings, not native presentation latency.
Source function attribution: source-cumulative.json and source-startup.pstats in
the receipt directory.

Loaded CAD groups now use immutable vertex/index snapshots with exact indexed
bounds validated once during background profile preparation. The group mapping
and snapshots cannot be modified through public attributes. Bounds lookup uses
the snapshot result; mutable generated stock, transformed workholding and other
editable geometry still validate their current vertices/indices on each call.
Malformed indices, nonfinite positions, input mutation and unreferenced vertices
remain covered. A frozen snapshot constructor computes its own bounds rather
than accepting externally supplied cached bounds.

Real c1-v9-saunders-vise asset comparison against source 29ed0d6 verified all
vertices/indices, canonical metadata and fingerprints exactly unchanged. The
complete scene bounds, including transformed workholding/stock, also matched.
In that data-only comparison, bounds lookup was 0.852 s before and 0.067 s after;
load time was 2.923 s before and 3.675 s after because validation moved into the
background preparation. Concurrent activity and cache state affect these timings;
no native speed claim is made. Receipt:
/private/tmp/carvera-startup-profile-20261005/real-asset-bounds-comparison.json.

34 validation/immutability checks and 49 affected geometry/interaction/history
engine checks passed. Receipts: /private/tmp/carvera-geometry-snapshot-final-tests.log
and /private/tmp/carvera-geometry-snapshot-engine-tests.log. Initial Python 3.9
annotation collection failure and the old list-versus-tuple assertion are retained
in the earlier snapshot logs. Rendered/native acceptance remains pending.

The rendered scene/profile/default-preparation/interaction suite passed 50 tests
(64.62 s, one existing SSL warning). Receipt:
/private/tmp/carvera-geometry-snapshot-rendered-tests.log. Ruff/format/diff passed.
All 18 post-incident operator-store entries matched. Native package acceptance
and comprehensive responsiveness remain open.


DESKTOP160 installed/native bounds checkpoint: frozen source
e3909b717090764055582a0a05b35f3b62b72e76, installed at
2026-10-05T15:44:40Z; 477 files without manifest mismatches and strict
signatures passed. DESKTOP159 recovery retained. Native profile selection
reported Loaded; saved machine, Saunders plate, Mod Vise and stock rendered.
Live/Scene displayed fresh reported Idle, T1/TLO 50.480 and zero RPM/feed.
Startup again timed out the UI bridge and recovered in the same launch;
no comprehensive responsiveness claim is made. All 18 post-incident operator
store entries matched, camera remains unavailable and original probe D remains
unknown. Current log contains no AttributeError or connection-loss event.
Receipt: /private/tmp/carvera-desktop160-20261005/native-bounds-acceptance.json.
No upload/motion/tool change/offset/calibration was issued. This closes bounded
installed immutable-CAD publication acceptance only; overall responsiveness
and every original complete requirement remain open.


DESKTOP164 native review retained additional evidence: connection loss/reconnect
coincided with local picker navigation, and a later Return to Live observation
took 23.55 seconds while rendered regression tests were also running. This is
end-to-end computer-use latency, not an isolated application phase measurement
or established root cause. The same process recovered; no restart was used as
timeout recovery. Log retained in /private/tmp/carvera-desktop164-20261005/native-controller.log.
Complete responsiveness remains open.


Filesystem replacement-request checkpoint: native DESKTOP165 multi-stock loading
exposed immediate rejection while cancelled Downloads helpers were still stopping.
The same local-folder retry later succeeded. Source now waits for a helper slot
on the existing desktop worker, polling retired-process exit and cancellation at
bounded intervals. Waiting and child execution share the original deadline; the
two-helper cap remains enforced, including kernel-blocked retired processes.
Active contention and retired-process exhaustion have distinct error messages.
No additional process is launched while capacity remains occupied.

The real-helper and rendered picker suites passed 23 tests (16.41 s, existing SSL
warning), including automatic recovery after retirement, waiting cancellation,
slot ownership, total deadline and the previously added accepted-folder reuse.
Receipt: /tmp/carvera-picker-helper-recovery-tests.log. Ruff/format/diff passed.
This corrects a source-level retry race; installed/native acceptance and the
broader intermittent tab freeze remain open.


Compact shared-header source checkpoint: the standard 530 dp workbench now fits
all nine navigation actions in one row and connection/hold/STOP beside status and
profile metadata. Below 500 dp controls retain their stacked fallback. Navigation
buttons retain at least 48 dp width, safety actions at least 64 dp, and the shared
setup strip retains 32 dp actions in a 38 dp surface. The setup count switches to
its concise form when its available width is below 150 dp. Shared spacing and
spindle-monitor caption height are reduced without changing command guards.
Rendered 530/360 dp reviews confirmed labels/actions fit, the count is visible,
and the task viewport remains usable. Final workspace/navigation/readiness suite:
50 passed (38.94 s, existing SSL warning). Receipt:
/tmp/carvera-compact-header-final-affected-tests.log. Ruff/format/diff passed.
The earlier suite's geometry assertion compared identical tuple/list values;
its value comparison was normalized and the failed log retained. This is source
layout evidence; installed/native layout acceptance and full responsiveness remain
open. No physical action is claimed.


DESKTOP167 responsiveness diagnosis: native diagnostics exported and independently
read at 2026-10-05T17:36:24Z. Setup callback was 1.17 ms, next clock turn 467.71 ms
and flip notification 455.51 ms; Monitor callback was 1.25 ms, clock turn 41.53 ms
and flip 37.35 ms. The retained 60 recent refreshes peaked at 5.74 ms, but 2,210
older refreshes had been evicted. Separately measured Scene native calls took
0.52 s input, 1.17 s accessibility and 0.81 s screenshot. This does not explain
previous combined minute-long calls or prove input dispatch/presentation latency.
The picker timed out on Downloads and initially on the owned folder; same-folder
retry recovered. A transient controller reconnect also recovered in the same
process. Native export receipt, JSON and process sample are retained in
/private/tmp/carvera-desktop167-20261005/; navigation-diagnosis-receipt.json
records the exact export digest and confirms all 18 operator stores matched.
No upload/motion/tool change/offset/calibration occurred.

Source follow-up preserves the slowest callback, clock-turn and flip observations
independently of recent-record eviction, plus the longest callback-start interval
with adjacent identities. Retention remains bounded; exports are independent
copies. Failed callbacks remain explicitly failed without invented render proof.
The Machine timing note now uses the session maximum refresh instead of the
recent ring maximum. Start intervals are cadence evidence, not causal evidence;
navigation intervals include operator idle time. Engine, rendered navigation and
async-export checks passed 17 tests (18.06 s, existing SSL warning), including a
five-second refresh exported after ring eviction. Ruff/format/diff checks passed.
Log: /tmp/carvera-retained-slow-timings-final-tests.log. This source change awaits
packaging/native acceptance; installed DESKTOP167 predates it. Overall freeze
resolution and all original complete requirements remain open.


DESKTOP168 native timing-retention checkpoint: source
`9dbc1fa4d67e2a7f4beaa202d364663595338088`, installed at
2026-10-05T17:40:33Z; all 482 manifest files matched and strict signatures passed.
DESKTOP167 recovery retained. The first native observation timed out during
startup; the same running process was subsequently observed without restart.
Native diagnostics export independently confirmed a 23.01 ms maximum refresh
(sequence 1) persisted after 553 records were evicted, outside the 60 recent
records. It also retained a 4.44 s startup refresh-start interval and 5.61 s
initial flip notification. These identify diagnostic intervals, not their cause
or screen presentation. Source-controlled slow-refresh export and failure
semantics passed the prior 17-test affected suite. Native Setup/Spindle switches
and export succeeded; folder navigation needed no retry in this run. Live showed
reported Idle, T1/TLO 50.480, zero RPM/feed and fresh camera/telemetry. All 18
operator-store entries matched. Receipts:
/private/tmp/carvera-desktop168-20261005/artifact-verification.json and
/private/tmp/carvera-desktop168-20261005/native-timing-acceptance.json.
This closes native session-maximum export acceptance only; root-cause diagnosis,
full responsiveness and all original complete requirements remain open.


UI stall-capture source checkpoint: an independent background monitor samples the
UI thread after a one-second missed heartbeat. It retains at most 20 episodes,
three samples per episode and 32 stack locations per sample, with recovery time,
heartbeat gap and last page context. Capture stores source basenames/functions/
line numbers only; no source reads, local values or full paths. Recovered-during-
sampling races are rejected; disposal cancels the heartbeat and signals worker
shutdown without joining on the UI thread. Signal diagnostics exports these
bounded observations. OS suspension, debugger pauses and GIL starvation remain
explicit alternative explanations; sampled locations do not prove root cause.
Engine/thread/export/rendered navigation checks passed 20 tests (14.84 s,
existing SSL warning); Ruff/format/diff passed. Log:
/tmp/carvera-ui-stall-capture-final-tests.log. Packaging/native capture acceptance
and overall freeze resolution remain open. DESKTOP168 remains installed.


DESKTOP169 native stall checkpoint: source
`48f2f819960ee8727076c44430b081dd6f1bd5cb`, installed at
2026-10-05T17:47:21Z; all 483 manifest files matched and strict signatures passed.
DESKTOP168 recovery retained. Existing Workshop Carvera profile was explicitly
connected; Live returned with fresh reported Idle, zero RPM and camera/telemetry.
Native diagnostics captured five recovered heartbeat episodes without artificial
machine actions. Startup samples were in Kivy drawing/buffer flipping (1.98,
1.26 and 1.14 s gaps). Two file-browser paste episodes were sampled in
clipboard_sdl2.get via TextInput.paste, with recovered heartbeat gaps 12.66 and
9.69 s. These locate a clipboard-related UI freeze; they do not establish the
cause of every prior tab delay. The background monitor may itself be delayed by
the GIL. Native export/readback verified bounded samples and recovery timestamps.
All 18 operator stores matched. Receipts and exact export digest:
/private/tmp/carvera-desktop169-20261005/native-stall-acceptance.json.
No upload/motion/tool change/offset/calibration occurred. Clipboard isolation and
native paste/cancellation/selection/undo acceptance are the next actionable fix;
startup rendering and overall responsiveness remain open. Native bounded stall
capture/export/recovery closes only this diagnostic checkpoint.


Loaded-program refresh checkpoint: periodic simulation input capture previously
traversed every resolved motion segment to collect required tool IDs. Program
preparation now publishes immutable motion plus an exact tool/source-line index
in one bundle. Whole-job queries reuse the indexed IDs; operation queries use
inclusive binary searches per tool. Unknown tool IDs remain unknown, declared
tool changes without resolved motion remain excluded, and replacing motion
rebuilds the index before publication. Context capture still reads current tool
and setup definitions; explicit actions still verify exact CAD bytes.

In a source-only synthetic 300,000-segment context/digest benchmark (30 rounds),
legacy median/max were 11.483/12.057 ms; indexed median/max were 0.094/0.112 ms.
Context records matched exactly. Index preparation took 37.425 ms and runs with
program preparation. This is neither native click-to-display latency nor machine
control latency, and does not explain every prior freeze. Receipt:
/private/tmp/carvera-indexed-job-benchmark-20261005.json.

Focused resolved-motion/range/replacement/context and rendered simulation/tab
checks passed 47 tests in 14.52s (existing SSL warning). The initial integration
fixture omitted shank diameter and correctly failed tool readiness; its log is
retained. Corrected broad unit plus geometry-change/tab integrations passed
1,684 tests in 44.39s. ProgramOperations passes focused strict typing with
imported diagnostics silent; full local strict remains failing with 1,264 errors
in 64 files, including addon diagnostics (84 checked). Ruff lint/format and diff
checks pass. Package/native loaded-job acceptance remains open; DESKTOP180
predates this source change. Logs: /private/tmp/carvera-indexed-job-
{refresh-corrected,broad,full-strict}-20261005.log.
Hosted source 8239ebf run 37373247394 passed baseline mypy, lint/format and
architecture checks but failed strict machine typing with 697 errors in 45 files
(84 checked). Hosted downstream tests did not run.


DESKTOP181 installed/native checkpoint: application source
`8033087bbd75c428a34a0aad8b81ffdafc65c55d`; built and installed independent
manifest/signature checks matched 489 files with zero mismatches. Installed
verification: 2026-10-05T21:16:11Z. DESKTOP180 is the immediate recovery build.
Native CUA at 2340x1608 loaded a SHA-recorded 6,000-move synthetic local preview
while disconnected from CNC transport. The picker reported its bounded quick
inspection limit and offered local preview; the full loader displayed three
operations (including setup). Selecting the rough operation retained 3,001
resolved motion lines and one unresolved initial approach. Simulation readiness
required explicit T1/T2 geometry. Program, Scene, Setup, Machine and Camera
screens were individually reviewed; camera remained live through navigation.
Native click-to-display latency was not instrumented. No upload, start, motion,
tool change, offset or adaptive actuation occurred. All 18 operator stores
matched the pre-review backup without needing restoration. Normal relaunch
returned to Live/Idle with saved-profile reconnect, fresh telemetry/camera,
reported T1/TLO 50.480, zero RPM/feed and no local or remote program selected.
This closes bounded loaded-job inspection/navigation acceptance, not complete
responsiveness or physical workflow qualification. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop181-20261005/
{built-verification,artifact-verification,native-acceptance,storage-recovery}.json.

The initial install staging copy failed with no space before replacing the
installed DESKTOP180 bundle. Failed staging and logs are preserved. The
DESKTOP179 recovery was moved to /Volumes/Wes Storage/CarveraBuilds/ and its
489-file manifest and strict signature were independently verified there.
The partial staging app is retained as failed-staging.app under the DESKTOP181
build root. The retry completed and passed installed verification. No unrelated
files were removed. System available space subsequently rose independently;
that change is not attributed to these small task-owned moves. Installer
capacity preflight remains an actionable tooling gap. Initial failure log:
/private/tmp/carvera-desktop181-install-20261005.log; retry:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop181-20261005/install-retry.log.


DESKTOP182 native declared-branch checkpoint (application source 8a1759c):
expanded/selected local results, unit inputs and valid/rejected declaration
imports were observed at 2340x1608; the workbench and stacked imagery remained
visible at 1864x1306. This is visual/functional review, not instrumented latency.
The narrower navigation leaves Profiles alone on a second row and needs more
compact treatment. Glyph, empty-results and initial-seed findings have
source-tested followups that are not yet installed. The original view size was
restored; final normal session is Live/Idle with fresh telemetry/camera and no
program selected. All 18 tracked operator-store hashes match. Receipts:
/Volumes/Wes Storage/CarveraBuilds/carvera-desktop182-20261005/native-acceptance.json.

Compact navigation source followup (2026-10-05): the workbench uses its section
choice plus a separate Profiles action below 464 dp of available navigation
width. Wider layouts retain the eight section buttons plus Profiles. Both modes
reserve one 32 dp row. Mode changes close an open choice, release outgoing
keyboard ownership, retain the selected section and update legacy connection
menu anchors to a visible control. A rendered 360 dp inspector was reviewed;
source integration checks cover 360/440/530 dp layout and all section choices,
including Setup evidence. This followup has not yet been packaged or reviewed
in the installed native application.
