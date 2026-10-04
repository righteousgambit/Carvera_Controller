# Linked selection history

Program inspection now has Back, Forward and Operations together below the move
explanation. Explicit operation selection, line inspection, next/previous move,
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
