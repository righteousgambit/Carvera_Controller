# Nominal surface inspections

Requirements 11 and 12 now share a retained nominal surface and a local receipt
workflow. Scene → Measure surface can retain a part/feature name, complete nominal
triangle/point/normal, ball-center approach plan, optional signed lower/upper normal
deviation limits, machine-profile identity and the declared setup snapshot.
Setup → Surface inspection records opens the retained inventory without requiring
a current surface pick. Saved definitions remain tied to their original setup;
changing the current scene does not reinterpret historical receipts.

The nominal hash identifies the saved plan/context bytes. It does not validate the
CAD model, actual mounting, machine registration or probe calibration. Loading
checks triangle winding and point containment, structured fields, finite quantities,
duplicate identities, explicit coordinate/evidence classes and the content hash.
Broken data is retained and writes are blocked until the file is repaired/reloaded.

## Measurement evidence

Each receipt retains its own UUID, XYZ, coordinate kind, explicit nominal-component
machine frame, operator-entered evidence class, source reference, registration and
compensation references, reported observation-time text and actual local record
time. Observation time remains unknown when the field is empty; record time does
not substitute for acquisition time.

Raw triggers and receipts missing either registration or compensation references
remain unevaluated. An explicitly declared compensated ball-center receipt with
both references can be compared to the retained nominal plane. Within/outside
declared limits is a numerical comparison of those inputs, not metrology
certification or independent verification of the entered references. Missing limits
produce an untoleranced result. Empty/single-sample groups do not invent repeat
statistics: mean/range need a sample, sample standard deviation needs two.

The view retains full samples, provides searchable paged receipt history and
computes repeat statistics over all evaluated samples. Switching features clears coordinate/reference inputs.
The form scrolls and its action row wraps at narrow widths. First-load, save and
reload disk work run in one serialized controller worker; duplicate gestures cannot
create duplicate in-flight features/receipts. Dismissal during load/save does not
reopen a closed view. Local JSON writes use flushed temporary files and atomic
replacement, and reject a changed baseline rather than overwriting externally
modified records. The default store is `.carvera/surface-inspections.json` (schema 1,
8 MiB bound, at most 1000 features and 1000 receipts per feature).

Probe transport, registered/compensated machine receipts, multi-feature geometric
fitting, uncertainty, tolerances beyond signed local-plane limits,
datum/offset transactions and physical qualification remain open. The new UI does
not issue machine commands or change offsets. No original numbered requirement
closes at this source checkpoint.

## Source verification

The final combined inspection/measurement/scene checks passed 34 tests (97.13s,
one existing locale warning): `/tmp/carvera-surface-inspection-render-final-tests.log`.
Earlier close/lifecycle checks passed 34 tests (22.13s), after correcting the
loading-popup dismissal race; the failed attempt remains in
`/tmp/carvera-surface-inspection-final-tests.log`. Reload/feature-switch checks
passed three tests (22.71s): `/tmp/carvera-surface-inspection-reload-final-tests.log`.
Final layout/lifecycle checks passed three tests (18.72s):
`/tmp/carvera-surface-inspection-layout-final-tests.log`. Wide/narrow source renders
`/private/tmp/carvera-surface-inspection-wide0003.png` and
`/private/tmp/carvera-surface-inspection-narrow0003.png` were reviewed. Ruff lint,
format, diff checks and both import contracts passed (220 files, 969 dependencies).
Installed/native acceptance remains open; no physical probe operation is claimed.

## Portable exchange and reports

The records view exports a selected feature or all features as a `.cvinspect`
portable JSON bundle, CSV or standalone HTML report. Bundle schema 1 retains exact
feature and receipt identities, nominal/setup declarations, limits, evidence class,
coordinate kind/frame, supplied source references and both time fields. The bundle
content hash is checked separately from each nominal/context hash. Public store
records now normalize to JSON types so persisted/bundle roundtrips compare exactly.

Import first reviews additions without changing local records. Applying the review
rechecks the exact source file hash. Identical records are idempotent; independent
receipts merge under an unchanged feature definition. Conflicting feature or
receipt identities fail before saving. A corrupt local store cannot accept even an
empty bundle, and closed views do not reopen when review work finishes. Import
never restores machine offsets, geometry or active setup.

CSV retains nominal point, outward normal, probe diameter, triangle identity, limits,
measured coordinates, evidence references, times and comparison state. Unevaluated
deviation is blank; features without receipts retain an explicit no-measurements
row. Text fields are escaped for spreadsheet use; JSON retains their original text.
HTML escapes entered content and includes receipt IDs, summary statistics, unknown
states, full nominal/setup details and its feature/receipt content hash. Print
styling uses a landscape receipt table, compact metrics and a nominal/setup appendix.

Exports encode/write off the UI thread through flushed temporary files and atomic
replacement. Completion receipts include exact saved-file SHA-256/byte count and
feature/receipt counts after independent file readback; JSON is parsed again.
The final combined exchange/store/UI suite passed 38 tests (23.64s); receipt:
`/tmp/carvera-inspection-exchange-layout-final-tests.log`. Later CSV/receipt-ID tests
passed 15 tests (0.11s), and selected/all-feature file-picker export plus reviewed
import passed separately (15.41s). Failed tuple/list attempts remain preserved.

The demonstration HTML at `/private/tmp/carvera-inspection-report-q0f3_waf/index.html`
was rendered offline using WeasyPrint 70.0 with external resource fetching disabled.
Both pages of its final landscape print rendering were inspected. The browser
blocked local-file navigation; browser rendering and installed/native acceptance
remain open. This is dummy input, not physical measurement evidence. The initial
three-page layout remains preserved alongside the corrected two-page print review.
Ruff lint/format, diff checks and both import contracts passed (221 files,
980 dependencies). Requirement 12 remains open despite closing this bounded source
exchange/report checkpoint.

## Searchable receipt history source checkpoint — 2026-10-05

The inspection workbench now retains access to every receipt through state filters,
provenance search and twelve-item pages. A bounded 240 dp receipt list brings the
selected item into view; selection details sit above the list. The signed-deviation
plot shows the declared limit band and selectable discrete comparisons. Raw trigger
coordinates and missing registration/compensation references remain unevaluated,
with separate marks below the plot. Points are never interpolated into a measurement
curve. A source-rendered 360 dp pane was inspected for wrapping and reachable paging.

The three inspection engine modules now have explicit feature, nominal, receipt,
result and exchange contracts and pass focused strict typing. Valid-digest malformed
inputs are rejected before changing retained records. File reads enforce byte bounds
while reading rather than relying on mutable size metadata. Series comparison restores
the nominal once, preserving individual receipt classification.

The final focused suite passed **64 tests** in **22.90 seconds**, including bounded
reads, valid-digest malformed bundles, receipt selection/filtering/paging, responsive
layout, portable exchange and command-free UI behavior. Receipt:
`/private/tmp/carvera-inspection-final-regressions-20261005.log`. Ruff lint/format and
both architecture contracts passed (251 files, 1,212 dependencies). Full local strict
typing still reports 1,042 errors in 58 files across 87 checked modules; there are no
diagnostics in these three inspection engines. This local scope includes imported
addon diagnostics and cannot be compared directly to the hosted count.

The installed DESKTOP185 build predates this checkpoint. Installed interaction,
registered machine receipt capture, accuracy and physical qualification remain open.
Requirement 12 and the full implementation goal remain open.

## Reviewed batch measurement entry — 2026-10-05

The inspection workbench accepts a pasted TSV spreadsheet table or explicitly
selected CSV. Required headers are `x`, `y`, `z`, `source_ref`; optional columns are
`kind`, `registration_ref`, `calibration_ref`, `observed_at`. Coordinates use the
retained nominal component machine frame. Unsuffixed quantities use mm; explicit
units/fractions use the same bounded quantity parser as individual entry. Unknown
columns, duplicate headers, malformed rows and over-capacity batches are rejected
before any prefix is retained. Per-row references stay explicit; blanks remain
unknown and raw triggers remain unevaluated. No current machine pose is substituted.

The review exposes every proposed entry through the paged history and signed
deviation plot. The table editor collapses after validation to give comparisons
space. Editing text, separator or coordinate kind invalidates the review. Worker
results from superseded or closed views cannot publish a preview. Parent dismissal
also closes the batch dialog. Before persistence, the exact reviewed feature and
receipt bytes are rechecked. A changed nominal, limits, retained receipt list or
external store prevents stale retention. Repeated application is rejected.

One atomic store transaction assigns distinct receipt identities and actual
retention time to every row. Observation time is separately supplied or unknown;
preview time is not acquisition/retention evidence. Failed writes publish no batch
in memory or on disk. These remain operator-entered receipts, not independently
registered machine measurements. The input hash identifies the exact reviewed table.

The combined batch/store/exchange/measurement/UI suite passed **80 tests** in
**20.55 seconds**. Receipt:
`/private/tmp/carvera-inspection-batch-final-regressions-20261005.log`. The subsequent
collapsible-layout/lifecycle pair passed **2 tests** in **17.24 seconds**; receipt:
`/private/tmp/carvera-inspection-batch-layout-final-20261005.log`. All four inspection engine
modules pass focused strict typing. Ruff lint/format and both architecture contracts
pass (253 files, 1,230 dependencies). A source-rendered narrow dialog was inspected.
Installed interaction, machine receipt acquisition, richer geometric fitting and
physical qualification remain open. The original requirement scope is unchanged.
