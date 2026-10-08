# Linked selection history

Program inspection now has Back, Forward and Operations together at the start of
the move explanation. Explicit operation selection, line inspection, next/previous move,
search-result selection and bookmark jumps share a bounded 100-entry session
history. Back/Forward seek the preview, update operation highlighting, restore
captured orbit/pan/zoom/projection and show the source explanation. Leaving a
point captures its latest framing, including changes made after selection.

Selecting another point after going back discards the abandoned forward branch.
Loading another program clears the history. Playback updates do not add entries.
Each entry identifies its program revision; complete views also identify the
saved machine profile and setup geometry using the bookmark context hash.
Changed setup/profile refuses restoration before seeking or moving the history
cursor. Source-only entries without a complete profile/view can still revisit
lines, but cannot restore geometry. No controller commands are issued.

This checkpoint covers Program inspection and bookmarks. Cross-tab history for
scene objects, tool passports, fixture and measurement inspectors remains OPEN.
It does not close the entire selection-history requirement. Source tests and
installed native interaction are independent acceptance gates.

DESKTOP42 installed checkpoint: source
`64ca62b1b5d9b9b94b08b5af3604361c4653e3db`, 396 non-generated source files
matched both staged and installed manifests; strict signature verification passed.
Native inspection of the local example verified line 8 -> line 14 -> Back to 8
-> Forward to 14 with operation highlights and explanations. Saved operator
profiles, scene and bookmarks remained unchanged. The controller was disconnected;
no machine motion commands were issued. Full source suite: 1,074 passed, 15 skipped.
Receipt: `/Users/wes/Downloads/carvera-desktop42-20261003/checkpoint-receipt.json`.
Framing restoration remains source-tested rather than independently exercised in
this native checkpoint. Native review found the navigation row partly clipped on
automatic explanation reveal. The next source revision groups controls, status
and explanation for reveal, with a controls-first anchor when the explanation
exceeds the viewport. Real layout tests cover ordinary and narrow/short viewports;
installed verification of that fix is a separate checkpoint.

DESKTOP42 follow-up native inspection also verified departure zoom capture:
two Zoom + clicks at line 14, Back to line 8 restored the original zoom, and
Forward restored the enlarged finishing view. The same receipt retains this
additional observation and `native-history-framing.png`.

DESKTOP43 installed checkpoint closes the observed clipping defect: inspecting
both lines automatically exposes complete history controls and explanation;
Back/Forward update the source, explanation and visible status together.
Source `fff4d4d` built and installed with 396 matching non-generated manifest
entries and strict signature verification. Full suite: 1,075 passed, 15 skipped,
7 warnings in 209.49 seconds. Operator profiles, scene and bookmarks stayed
unchanged; DESKTOP42 recovery signature verified. Controller disconnected,
camera live, no machine motion commands. Receipt:
`/Users/wes/Downloads/carvera-desktop43-20261003/checkpoint-receipt.json`.
Native narrow-window resizing and cross-tab selection remain open; narrow/short
layout checks are source-runtime evidence.

## Shared workspace navigation

Program inspection, Scene components and workbench tab navigation now use one
bounded session history. Compact Back/Forward controls remain available beneath
the workbench tabs. Local inspector controls delegate to the same owner. Entries
capture departure orbit/pan/zoom/projection and preview distance, selected source
or component, loaded program identity and setup context. Restoring a Program
entry updates its source/operation inspector; restoring a Scene entry selects
and highlights the relevant component. Tab entry alone does not invent physical
tool identity or measurement selection.

Changed program, setup or loaded tool geometry refuses restoration before
seeking or changing the history cursor. Loaded CAM dataclasses/enums are
serialized into the context hash, and local tool overrides are bound when
present. Empty tool tables preserve the previous context representation. Source
inspection ignores preview callbacks during explicit history restoration so
they cannot replace the restored source selection.

Scene/Program/section navigation is a foundation; tool-passport and measurement
object navigation, direct geometry picking, full view-state coverage, and native
qualification of every supported domain remain OPEN. History is session-local
and does not persist or apply setup geometry, offsets or controller state.

DESKTOP46 source `8b3475c` built and installed; its original full suite passed
1,094 tests, with 15 skips and 7 warnings. Native Back restored Program line 8
from Scene stock/vise inspection, but Forward exposed an off-viewport nested
scroll click defect in the compact layout: the clipped Program setup row could
capture a header click. Native and failing compact click-test evidence are
preserved under `/Users/wes/Downloads/carvera-desktop46-20261003/`.
The follow-up guards the parent viewport before nested scroll dispatch and sizes
history actions to their row. A real mouse-profile integration test uses a
multi-operation program at 1353 × 786 and checks Back/Forward across both tabs.
Its failing-before/fixed-after logs preserve the regression; subsequent package
and native validation remain a distinct checkpoint.
