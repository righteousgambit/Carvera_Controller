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

The view retains full samples, shows the latest 20 and computes repeat statistics
over all evaluated samples. Switching features clears coordinate/reference inputs.
The form scrolls and its action row wraps at narrow widths. First-load, save and
reload disk work run in one serialized controller worker; duplicate gestures cannot
create duplicate in-flight features/receipts. Dismissal during load/save does not
reopen a closed view. Local JSON writes use flushed temporary files and atomic
replacement, and reject a changed baseline rather than overwriting externally
modified records. The default store is `.carvera/surface-inspections.json` (schema 1,
8 MiB bound, at most 1000 features and 1000 receipts per feature).

Probe transport, registered/compensated machine receipts, multi-feature geometric
fitting, uncertainty, tolerances beyond signed local-plane limits, report export,
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
