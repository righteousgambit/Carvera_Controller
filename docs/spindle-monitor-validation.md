# Spindle monitor validation and capture feedback

## Selected private backend

Selecting a backend uses its own monitor and status recording, independent of
the GUI controller's variables, baseline and buffer. Every accepted status
event has a client sequence, exact connection identity, host monotonic/UTC
receipt times and the IPC envelope digest. Reading the bounded queue does not
poll the child, drain other consumers, or count repeated snapshots as samples.
The queue retains 256 receipts; consumer overflow is reported explicitly as
lost **IPC queue receipts**, not an estimate of packets missing on the network.

The visible or selected backend requests private cached snapshots at a nominal
0.2-second cadence, leaving room for the child's reported status age within the
existing 0.8-second freshness budget. Snapshot does not send a firmware command.
This UI cadence is best effort; a delayed or stale report still invalidates the
baseline and requires explicit recapture. It is not a real-time control loop.

Normalized linear coordinates and feed are used for shadow calculations. RPM,
commanded RPM, overrides and XYZ must belong to the same complete packet. PWM
is optional; an invalid present value cannot become a low-load measurement.
Partial packets, receipt loss, stale reports, replaced ownership and model
mismatch invalidate the baseline. A new owner starts with its own empty monitor
and buffer; the previous buffer remains available for inspection. Recapture is
explicit and still requires five seconds of stationary, at-speed observations
with the cutter kept clear of stock. These observations do not prove unloading
or stock contact. This path continues to compute proposals only.

The workbench signal, baseline, decision and diagnostics sections use that
selected source. Diagnostics exports name the backend lease and queue losses;
they do not borrow GUI receiver measurements or claim firmware sampling,
one-way delay, camera exposure timing or actuator response. Backend recording
uses the bounded local run buffer and explicit Freeze/Export, rather than
claiming that the GUI controller's telemetry file is recording this source.

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
