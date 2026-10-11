# Capability overview and evidence inspector

The Machine workbench presents all twelve capability descriptions as selectable
status tiles. Search matches titles, workbench sections, states, prerequisites
and alternatives; a state filter narrows the overview. The selected capability
is explicit even when excluded by a filter. Related-workbench navigation remains
read-only. Evidence, prerequisites and alternatives expand on demand; collapsing
removes that content from the layout.

Tiles reflow between one and three columns at desktop density-aware widths.
Their identities persist across status changes to avoid replacing focus targets
on ordinary polling. Filtering a focused tile out releases its keyboard focus.
Freshness and session changes continue through the existing capability engine;
saved profiles cannot turn stale or disconnected observations into available
protocol support. Protocol availability does not prove installed hardware or
physical qualification. This overview issues no machine commands.

Source verification: 13 capability-model unit checks and four rendered interaction
checks passed. The latter cover narrow/wide layouts, real tile selection and
related-workbench routing, search by thread-milling alternative, simulation-only
filtering, empty results, explicit selection retention, stale/recovered observations,
focus release, stable tile identity and disclosure. One- and three-column renders
were visually reviewed. Ruff lint/format and both architecture contracts pass
(186 files, 755 dependencies). Initial fixture failures are retained: detached
widgets did not receive parent layout, and raw pixel width failed to account for
Retina density. Mounted density-aware interaction checks corrected the fixtures.

Installed/native acceptance is OPEN until the next package is exercised. Complete
commissioning, backend execution, hardware calibration and advanced-machine
workflow requirements remain OPEN in their existing ledgers.
