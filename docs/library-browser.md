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
