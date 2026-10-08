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

## Calibration trend workbench (2026-10-06 UTC)

The bench opens in Trends, with Latest report and Receipt history as separate
views. Switching removes inactive content and releases its keyboard focus.
Applied TLO, raw mean, computed range, sample standard deviation and comparable
offset change have separate selectors. All-group and session-local views are
scatter only. A selected revision/source/tool group joins only original comparable
receipt links, never repaired timestamps or inferred baselines. Missing values are
amber points; selecting them preserves the original receipt locator and unknown
value. The horizontal axis is capture order, not elapsed time or machine motion.

Charts page through all reports in bounded windows of 60. Previous/Next receipt
buttons provide keyboard-accessible inspection alongside pointer point selection.
The inspector includes the exact selected metric, full receipt/revision IDs,
source/tool, measurement time and up to 20 raw samples with an explicit retained
count. Refresh keeps selected receipt and source group; duplicate session-local
timestamps retain their capture ordinal rather than aliasing another report.
No receipt is rewritten and no controller command is sent.

Narrow/wide mounted renders and source interaction checks cover grouping, clock
breaks, unknown samples, paging, point selection, pinned selection on append,
section focus release and read-only operation. The calibration model now passes
local strict typing without suppressions; the broader strict machine layer is a
separate CI gate. Installed/native and physical trend interpretation acceptance
remain separate until the frozen package is exercised.
