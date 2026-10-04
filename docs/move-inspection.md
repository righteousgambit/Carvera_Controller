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
