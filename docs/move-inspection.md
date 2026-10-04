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

### Declared mapped joint studies

`analyze_mapped_joint_motion` now consumes an explicit joint trajectory, velocity
limits and `MachineKinematics` model with a supplied tool length. It subdivides
each piecewise-linear interval using declared maximum rotary and linear joint
increments. This retains full rotations and differentiates a stationary tool in
world space from a moving tool relative to a rotating workpiece. It reports both
sampled tool-tip lengths, maximum sampled work-frame chord rate, pose count,
declared joint velocity checks and sampled position-limit violations.

The caller must supply model and trajectory sources. Pose budgets are checked
before accepting an oversized input and while subdividing; cancellation and
budget exhaustion produce errors, not apparently complete partial results.
Joint increment bounds do not establish Cartesian chord-error bounds. Rates
and paths are nominal and sampled; acceleration, jerk, singularity handling and
continuous collision remain outside this calculation.

`OperationPanel.review_joint_motion(program_hash, line, report)` is a read-only
handoff for a supplied study. It requires the exact loaded program revision and
matching inverse-time block duration, then shows frame-specific tip paths, limit
exceedances and source metadata in the inspector. Exceedances have a separate
status line. Changing source lines restores the correct line's study or unknown
state; loading a program clears session studies. It neither seeks the preview
nor sends a machine command. This is not a joint-data import UI or a live backend
adapter: acquiring actual configured trajectories and limits, registering the
model and validating controller behavior remain open.

The primary card retains duration, frame-specific paths, joint-limit results
and the unverified physical-mapping statement. **Model & sources** expands the
declared model, trajectory and per-joint limit sources, sampling assumptions and
interpreter limitations. Collapsing that section changes only presentation.

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

## Selected-move summary

The inspector now presents a responsive summary of tool/motion, program frame,
programmed feed and programmed spindle, followed by program geometry and the
physical-pose limitation. Parser warnings remain visible when details are
collapsed. **Source & modal details** expands the complete existing source
context and before/after state; it retains its presentation choice across line
navigation and resets on program replacement or invalid-line entry. Short forms
use one fact column; wider forms use two. These values describe parsed program
state, not measured assemblies, observed spindle demand or executed machine pose.

Task routing follows the logical Operations owner of retained source controls.
Ancestor discovery stops at repeated identities, so a popup/window parent cycle
cannot hang source-detail actions. Native installed acceptance of this inspector
change remains open; DESKTOP104 contains the earlier compact-library repair.

Source checkpoint: 10 focused unit checks and 11 Program-task/inverse-time
integration checks passed. The narrow summary rendering was visually inspected.
Ruff lint/format and both architecture contracts passed. Unit stubs were updated
to the existing explicit preview contract; scrolling checks await complete nested
layout rather than assuming five frames. The wider loaded-program navigation
check is recorded separately and is not implied by these passes.

Loaded-program navigation checkpoint: all six integration checks passed in
127.63 seconds, covering shared program/scene history, framing restoration,
changed-setup rejection, branch history, tool geometry identity, generic workspace
navigation and canonical rotary preview pose. No machine command was sent.
