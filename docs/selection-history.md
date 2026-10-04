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
