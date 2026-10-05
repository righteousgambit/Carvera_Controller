# Spindle monitor validation and capture feedback

The shadow monitor rejects malformed runtime signals before publishing a sample.
RPM, feed, override and all three position coordinates must be finite numeric
values; booleans and numeric strings are not accepted. Position must be exactly
an XYZ tuple. PWM remains optional, but a present value must be numeric in [0, 1].
State must be a nonempty string. Desktop monotonic timestamps must be numeric in
[0, 1e12] seconds; invalid/regressed arrival timestamps do not refresh freshness.
This bound prevents unbounded interval arithmetic and is not a firmware clock.

Invalid readings latch the monitor fault and invalidate its baseline without
replacing the last good sample or adding invalid readings to the sample trace.
Quality diagnostics retain rejected timestamp/invalid packet counts. Invalid RPM
values do not enter the quality export. Invalid or regressed monitor clock reads
also latch a fault and cannot initiate feed recovery.

Explicit baseline recapture starts a new signal sequence and clears filter and
adjustment state. It requires a new five-second stationary collection; the first
new sample is not compared with the old pre-fault timestamp. Earlier sample
history and arrival gaps remain retained. Motion, speed changes or excessive RPM
variation restart collection. Snapshot baseline values are copied so a diagnostics
consumer cannot modify the monitor's internal baseline.

The signal panel shows elapsed/required capture time, stationary sample count,
clear-of-stock guidance, captured RPM/range and disconnected/off/fault states.
Its text wraps to the panel width. Stationarity and RPM do not independently prove
that the cutter is unloaded; the operator must keep it clear of stock.

Source verification (2026-10-05): 101 monitor/feed/quality/persistence/recovery/UI
regressions passed in 15.85 seconds. Both changed machine modules pass focused
strict typing. Repository Ruff lint/format (503 files), diff checks and both
architecture contracts pass. Full local strict typing still fails: 1,016 errors
in 56 files (88 checked), including imported addon diagnostics; the prior local
checkpoint had 1,042 errors in 58 files. Package baseline remains 148 errors in
19 files. No quality rules were weakened.

These changes postdate installed DESKTOP186 (99a22cf). Installed interaction,
full loaded-job responsiveness, firmware timing and actuator response remain
open. This work does not enable active control or dispatch machine commands.
