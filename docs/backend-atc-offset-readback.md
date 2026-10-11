# Sourced current ATC offset readback

The installed-tool measurement pane offers **Read current ATC offset** after its
connection-specific model and firmware read. It sends only the existing admitted
read-only `M499` operation for the selected current T1–T6. A fresh Idle, stopped
spindle, exact owner/profile/tooling/setup context and durable read intent precede
the same-callback final admission. Pending job, probe, exchange or measurement
transactions refuse this action. No offset write, motion or retry is introduced.

The consumer validates the original private IPC bytes and original controller
command receive window, plan, connection, acknowledgement and exact bounded
`tool:N ref:... cur:... offset:...` grammar. It rejects partial, duplicated,
conflicting, different-tool and non-source reports. The reference, current tool
MZ and ATC offset remain separate values; their printed resolution is 0.001 mm.
No equality between `cur - ref` and `offset` is imposed: repeated calibration can
select a different sample, and the source provides independent fields.

The unit/reference interpretation is explicitly the pinned Community revision
`feab653def96a959e695049a4f828aeddbcd5547`, ATCHandler.cpp's M499 handler. This is
reported ATC state under that source contract, not signed firmware attestation,
physical cutter identification, nominal stickout or verified full Robot
compensation. Raw status offsets keep their separate unknown-unit semantics and
never populate a millimetre pose field. This query does not assign an `applied`
value to previous calibration samples or change tool passports automatically.

A fresh independent read appears alongside tooling observations for at most
0.8 seconds on its exact owner, profile and tool. It then remains visibly
historical in the measurement pane. Replacement, retirement, stale backend state
or a changed current tool removes its current comparison immediately. Each
report and failure attempt retains its original connection and durable history;
separate export saves and reads back the original offset receipt. Reading or
exporting offsets never replaces the measurement pane's latest calibration
attempt. Original receive windows can contain interleaved/unattributed output;
causal attribution and physical accuracy remain unverified.

T0/probe-specific corrections and unsupported models remain outside this
current cutter contract. Installed execution and physical offset qualification
remain separate acceptance gates.
