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
