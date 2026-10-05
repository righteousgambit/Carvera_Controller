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
