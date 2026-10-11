# Local backend startup diagnostics

Settings → Backend → **Inspect startup timing** opens a scrollable local report.
The inspector reads the existing client snapshot without sending a private IPC
request or opening a CNC connection. **Copy diagnostic report** copies a bounded
JSON report for troubleshooting.

The report separates process creation, the interval from process creation to a
validated ready event, and completion of the blocking startup operation. The
configured readiness wait begins after the process and its pipe workers are
launched; it is not a bound on process creation or total startup time. Unknown,
nonfinite or regressing clock intervals remain unknown. The original five-second
default wait is unchanged.

A validated ready event retains the SHA-256 of its original JSON-line bytes.
Failed starts retain a fixed failure code: process launch failed, readiness wait
timed out, readiness protocol failed, child ended before ready, or readiness
unavailable. The process exit code is a separate runtime observation. Stderr is
drained and counted in bounded chunks; its contents are neither retained nor
copied. No argument list, environment or private log content is included.

The report remains available after a failed child is reaped or an explicitly
stopped child leaves the panel. A new start replaces that panel's previous report;
this is an in-memory diagnostic, not durable operation history. A successful
startup remains historical if the process later closes or loses its connection.
The report displays running/ready state at its own observation time separately.

These timings describe host-side startup. They establish neither CNC network
latency nor physical readiness, command acknowledgment, completed motion, firmware
interlocks, or hardware qualification. Inspecting, copying or closing the report
does not retry a start, connect the CNC, switch control ownership or alter any
command-admission deadline.
