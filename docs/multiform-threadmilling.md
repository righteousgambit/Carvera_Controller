# Declared multi-form threadmill workflow

The hole planner accepts a pitch-specific loaded threadmill with explicit complete
teeth and a tip-to-lowest-tooth datum. Profile editing, recipe review/restoration,
physical-assembly recipe matching and nominal tool visualization retain those
fields. Legacy profiles without this metadata keep their previous fingerprints;
single-form recipe serialization retains its previous field set.

In Profiles, choose Thread mill and enter the pitch, complete tooth count (2–200),
and tip-to-lowest-tooth datum in mm. Zero datum is explicit; blank means unknown.
The complete tooth cells plus offset must fit the declared flute length. Count is
unitless when converting an imperial viewer; pitch and datum convert as lengths.
Then load the profile into the toolset and choose Pitch-specific multi-form in
Holes & threads. The wrapping summary identifies the axial motion and geometry.

The multi-form preview makes one full helical revolution with one pitch of axial
travel per radial pass, retaining the selected hand and climb/conventional sense.
The lowest declared tooth datum starts at the requested thread bottom for an
upward pass; a downward pass reverses this same interval. Cutter-tip Z includes
the declared tip offset. Requested depth must be at least one pitch and no larger
than count times pitch; tip offset must fit the bottom clearance and tip depth
must respect exposed reach and the declared floor. Each radial pass retracts to
the hole center before the next axial positioning move.

This is a nominal complete-cell model. Manufacturer reference conventions,
partial lead teeth, actual tooth profile/crest geometry, neck/holder clearance,
radial lead-in strategy, feeds, thread fit and physical execution remain to be
qualified. Teeth can emerge above the declared top face; the summary makes that
setup review explicit. The visualization draws the exact declared count and offset
using triangular cells, with unspecified radial tooth depth still a display
approximation. It is not a manufacturer drawing or a thread gauge. True thread
grooves in the stock-removal model remain open.

The one-pitch multi-form distinction is supported by the manufacturer's
[threadmill selection guide](https://www.harveyperformance.com/in-the-loupe/select-your-next-thread-mill/)
and [multi-form guide](https://harveyperformance.widen.net/content/uuc8pld9un/pdf/SF_70000_M100.pdf?u=d9orjt).
No manufacturer speed/feed recommendation is applied automatically.

## Verification

Source tests cover right/left hand and climb/conventional direction, tip Z,
one-turn-per-pass geometry, explicit stack/pitch/depth/clearance rejection, recipe
roundtrip and loaded-profile mismatch, physical assembly binding, unit conversion,
profile editor persistence, 360/760-pixel wrapping and stable label height, exact
nominal tooth-cell count and thumbnail cache invalidation. The earlier label sizing
loop and failed test logs are retained under `/private/tmp/carvera-multiform-*20261006*`.
The fixed source summary was rendered and inspected at
`/private/tmp/carvera-multiform-summary-source-20261006.png`.

This source change postdates installed DESKTOP188. Installed/native planner and
profile-editor acceptance, actual holder/stock collision qualification, thread
inspection and backend execution remain open. No machine command is dispatched
by profile editing, recipe restoration or generating the local preview.

Final guarded source batch: 255 tests passed in 35.35 seconds with one existing SSL warning. The subsequent tooltip typing check passed 124 tests in 0.66 seconds. Ruff lint/format/diff and both architecture contracts pass. Changed planning/profile engines pass strict typing with silent dependency traversal; full strict and package baseline remain open and are recorded separately.
Full local strict result: 883 errors in 54 files (88 checked); package baseline: 148 errors in 19 files (185 checked). Neither gate is green. No quality rule was weakened.
