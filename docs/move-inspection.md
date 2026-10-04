# Program move inspection

The Program workbench provides one-based source-line inspection, previous/next
motion navigation, bounded operation/result lists, and asynchronous search.
Selecting a search result or source line seeks preview only. Preview playback
updates the inspector while Program is active, without overwriting a focused
line entry. Operation selection, selected row and explanation remain linked.

Search terms combine with AND. `rapid`, `cutting`, `unresolved` and `tool:T17`
filter parsed motion; other words match source text or operation name. Results
show the first 20 lines and ask for refinement when more match. Stale results
from an earlier search or a replaced program cannot populate the current view.

The explanation includes source context, before/after modal changes, active and
pending tools, units, distance/arc modes, plane, WCS, motion, spindle, coolant,
length-compensation command, feed semantics and canonical XYZ endpoints. Arcs
retain all parser subdivisions under the exact originating source line. G94
feeds convert to mm/min; G95 is mm/rev; G93 remains inverse minutes and missing
per-move feed is explicit. Comments do not produce motion from retained modal
state. Unknown initial position, G53, rotary/macro/unsupported commands and
inherited parser uncertainty remain visible.

The SHA identifies parsed UTF-8 text, not an independently verified transport
byte stream. Endpoints belong to program frames. This inspector does not apply
measured WCS transforms, actual tool offsets, backend dialect execution or TCP;
physical machine pose is explicitly unavailable. Playback source association is
preview evidence, not executed-line telemetry. Spatial search, scene picking,
registered physical-pose explanation and full macro/canned-cycle interpretation
remain open in the connected-workflow ledger.

## Inverse-time block and joint demand

Inspecting an applicable G93 feed block adds a compact motion card with the
requested whole-block duration, sampled program-path length and average path
rate. It uses the documented inverse-minute convention `seconds = 60 / F`:
[LinuxCNC G93/G94/G95 reference](https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g93-g94-g95).
One explicit positive finite F is required on every feed block. A retained modal
feed, comment feed or duplicate feed word cannot supply that duration. G0,
dwell, nonmotion source and other feed modes do not show the card. Arc chords
share one originating block duration; their lengths are summed, not their times.
Requested time is not observed completion time or acceleration-limited timing.
Entering G94 or G95 from another feed mode clears the prior numeric feed in the
parser. A new explicit F restores the appropriate quantity; an inverse-minute
value is never silently reused as mm/min or mm/rev.

The pure `machine.inverse_time.joint_velocity_demands` API accepts an explicit
joint path sampled at increasing fractions spanning the whole block, together
with named linear/rotary velocity limits and their sources. It reports the
maximum piecewise-linear sampled rate in mm/s or degrees/s and whether each
declared limit is exceeded. Missing/duplicate joints, incomplete fractions,
nonfinite coordinates and invalid limits are refused. Rotary coordinates are
already unwrapped: 350 to 10 is -340 degrees unless a caller explicitly supplies
a different physical trajectory. No shortest-angle solution is invented.

The current source inspector does not supply such a mapped joint trajectory or
actual machine configuration, and therefore leaves joint demand explicitly
unknown. Program XYZ endpoints are not substituted for machine joints or TCP
motion. Backend-specific interpretation, sampled kinematic trajectories,
acceleration/jerk, registered tool-tip motion, observed axis limits, installed
interaction and physical qualification remain open for advanced-machining
requirement 21. This checkpoint does not close that requirement.

## Installed checkpoint

DESKTOP38 was built and installed from `3e353d413121bf2787ee19ccfa4815d74ad470a8`.
All 392 non-generated package files matched source and the installed bundle;
strict ad-hoc signature verification passed. The final source suite passed
1,048 tests with 15 skipped. Native local-preview review confirmed the first
line-14 seek retains line 14, reveals the complete helical explanation, and
semantic search and result selection work. The camera was live and the
controller disconnected; no hardware commands were issued. Operator profile,
scene and setup-evidence stores matched their pre-update hashes.

Ordinary wheel/scrollbar behavior is still an open native interaction gate.
Receipts, logs, screenshot and DESKTOP37 recovery bundle are retained in
`/Users/wes/Downloads/carvera-desktop38-20261003/`.
