# Calibration evidence bench

Setup's tool comparison and the physical assembly passport's Measurements section
open a shared calibration bench. It can review the selected physical assembly's
persistent attributed receipts or the selected tool number's session-local reports.
Opening, refreshing, changing scope and closing do not send controller commands,
write offsets or mutate raw measurements. Closing cancels its periodic refresh.

The latest report has separate cards for sample count, mean, computed range,
sample standard deviation, controller-reported spread and applied TLO. One sample
has no sample standard deviation. Invalid/nonfinite samples produce unknown
statistics rather than a calculation on a silently filtered subset. A disagreement
between reported spread and raw range remains visible; the report is not rewritten.

The latest ten receipts retain source, measurement time, tool number, assembly
revision and raw samples. Display shows the first twenty samples per report with
an explicit remaining count; all samples remain in their original receipt.
Applied-offset changes are computed only within a versioned assembly revision,
endpoint and tool-number group with increasing measurement times. Missing offsets,
unknown timing or a reversed clock break that group's baseline. Unversioned links
and session-local tool-number history never gain inferred physical attribution.
These numeric changes are not a diagnosis of seating, damage or wear.

Fresh current-spindle TLO is shown separately from nominal geometry. Numeric
receipt comparison requires the selected machine's latest matching declared
placement and current assembly revision, exact connection source and tool number,
and measurement/capture timestamps at or after that placement. It reuses the
explicit 0.001 mm numeric comparison tolerance from bank preparation, not a part
tolerance or physical identity check. Stale/disconnected status, another machine
profile, missing placement or missing applied TLO leaves the comparison unknown.

Unchanged refreshes reuse metric cards and the cached assembly/history view.
Generation, source, profile and selection changes invalidate their contexts.
Cards reflow between one and two columns in source renders at 400/1200 pixels;
both were visually reviewed. The actual workbench popup open/close path and timer
cancellation were exercised in the isolated source app.

Final affected suite: 19 passed in 15.98 seconds, one existing locale deprecation
warning. Receipt: `/tmp/carvera-calibration-bench-complete-tests.log`. Ruff lint
and formatting passed. Both architecture contracts passed (214 files, 926
dependencies), receipt `/tmp/carvera-calibration-bench-imports.log`. The initial
close-animation assertion failure and prior renders remain preserved. Installed
native acceptance, measurement launch/transport integration, reference artifact
measurements and physical seating/offset qualification remain open for requirement
10. This source is later than the frozen DESKTOP143 build.
