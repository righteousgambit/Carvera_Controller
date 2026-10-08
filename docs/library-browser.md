# Saved profile browsing

The machine/tool library now searches saved names, vendors, product numbers,
notes, shapes and machine addresses using all supplied search terms. Cutter
filters combine shape, vendor substring, cutting-diameter range, exact nominal
shank size and attached CAD/drawing references. Dimensions accept the shared
bounded quantity syntax, including fractions and imperial units. The nominal
shank equality tolerance is 0.000001 mm; it does not infer collet compatibility.
Invalid ranges leave the previous applied filters intact. Clear and Cancel are
explicit actions, and entered filter expressions are retained when reopened.

Results sort by name, diameter or vendor. At most 30 profile rows are created
per page, with Previous/Next and a match count. Text search is coalesced over
120 ms. Browsing changes neither editor drafts nor saved/active profiles; the
selected editor can remain open outside the filtered result set. Rows expose
cutting/shank sizes and vendor/product metadata, and wrap to content height.

The filter dialog has bounded desktop dimensions, follows window resize, and
uses one or two columns with a scrollable form and pinned actions. CAD and
drawing filters only inspect attached references; they perform no disk/network
asset validation and establish neither manufacturer identity nor measured tools.
No machine commands, profile writes or physical tool changes are issued.

Source verification: 53 unit/profile/workspace checks passed in 60.14 seconds.
A final layout interaction includes a 95-cutter library, paging, combined filters,
invalid-range rejection, retained editor draft, no store writes or commands,
compact library controls and a truly narrow single-column filter. Wider and
narrower rendered dialogs were visually reviewed. Both import architecture
contracts passed. This advances the desktop library browser requirement while
physical instances, supplier catalog/CAD qualification and the complete workflow
ledgers remain OPEN. Installed acceptance is recorded separately.

Installed acceptance, 2026-10-04: DESKTOP126 was built from
`dbf672e3e3012e7878e4d9df7615ba325de2a3a4`. Source/staged/built/installed
application files match (441 repository files; 444 artifact files); built,
installed and recovery DESKTOP125 signatures pass strict verification. Native
checks used the operator's three saved cutters: Titan plus `1/4 in` shank
returned two; a reversed diameter range preserved those results with an explicit
error; clearing filters and searching `Helical 03182` returned the square mill.
The editor remained unchanged outside the result set, as intended. The 95-record
pagination and narrow single-column layout were source interaction checks, not
claims about the three-record native catalog. Native automation briefly timed
out during search; reconnection showed the completed result, so no native
latency claim is made from that interaction.

Eight operator-store states and the Kivy configuration were restored exactly
before normal relaunch. PID 68255 then displayed Live, Idle, physical T1,
TLO 50.480 mm, zero RPM/feed, no selected program, camera age 0.6 seconds and
telemetry age 0.16 seconds. These are reported runtime states, not machining
qualification. Receipts and screenshots are in
`/Users/wes/Downloads/carvera-desktop126-20261004/`. No machining, tool-change,
program-upload, offset or adaptive-control commands were issued.
