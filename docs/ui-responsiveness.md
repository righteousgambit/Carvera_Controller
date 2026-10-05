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
