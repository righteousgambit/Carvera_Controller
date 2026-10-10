# Headless supervisor runtime

`python -m carveracontroller.headless --host <private IPv4> --port 2222`
starts a private JSON-lines child. It does not connect until its supervisor
sends `connect`. It does not expose HTTP, accept credentials, decide operator
approval, or reconnect automatically. WaveForm's authenticated edge gateway is
responsible for those boundaries. This runtime remains GPL-2.0-only and must be
distributed with the controller's corresponding source and existing notices.

Each request has an opaque unique `id`, a closed `method` and a `params` object.
Supported methods are `connect`, `disconnect`, `snapshot`, `command`,
`realtime`, `upload`, `download`, `cancel_transfer`, `catalog`, `compile`,
`operation`, `reconcile`, `probe_profile_read` and `probe_profile_apply`. Responses retain that
identity and contain `ok` plus either `result` or a typed error. Unsolicited
observations and connection changes are `event` records. Stdout carries only
these JSON records; logging goes to stderr. Sixteen ordinary requests can wait
at once. Duplicate identities terminate the protocol rather than dispatching
again. The supervisor must persist receipts before dispatch and after receipt.

The runtime selects the legacy Smoothie protocol for the reviewed Community
2.1.0c profile. It reuses the controller's protocol and XMODEM implementations,
without importing Kivy, shared CNC globals, or a GUI controller. One reader owns
the socket. Ordinary commands are serialized, use `sendall`, and await their
own bounded receipt. Shell queries do not emit `ok` in this firmware, so their
wire plan includes a read-only `M105` acknowledgement barrier. This barrier
does not establish completed movement. A command timeout or disconnect after
dispatch latches `unknown_outcome` and closes the socket. No command replay or
automatic reconnect occurs.

`feed_hold` and `software_abort` are software controls, never a physical stop or
proof that movement has stopped. Their receipts are `sent_unacknowledged`.
They may interrupt an ordinary command. File transfer owns the complete byte
stream and excludes polling and realtime bytes; it has a separate cancellation
request. Only bounded file paths beneath `/sd/gcodes` are accepted. Transfer
success requires both XMODEM acknowledgement and Player's final success report.
The result includes hashes of the actual payload, not padded block counts.
Upload acknowledgement alone is not readback verification.

Status and diagnostics retain their raw numeric fields and distinct ages.
Missing coordinates, units and inputs remain unknown. The exact diagnostic
meanings come from firmware commit `feab653def96a959e695049a4f828aeddbcd5547`:
`E[5]` is the cover input, `P[0]` the probe input, `P[1]` the fixed setter,
and `I[0]` the reported stop input. `I` is not the tool-calibration flag.
These software observations are not a certified safety chain.

The GUI's Wi-Fi connection and its discovery busy check share a cooperative
per-user endpoint lock with this runtime. A second local controller refuses
the endpoint before opening a socket. The lock does not block a different
user, another host, or older unmodified controller software; deployment must
retire the old GUI connection and restrict network ownership separately.

Loopback socket tests cover receipt ordering, shell barriers, immediate hold,
disconnection ambiguity, errors followed by acknowledgements, bounded parsing,
actual XMODEM transfer, and cooperative ownership. They make no physical
motion, spindle, probe-accuracy or machining qualification claim.

### Original receive-byte custody (additive source contract)

Command receipts now include `controller_receive_evidence` version
`carvera.controller_receive_window.v1`. The socket owner captures complete
`recv` buffers before decoding, trimming or parsing. It retains base64 original
bytes, SHA-256 and byte count for at most 65,536 received bytes per pending
command. Above that budget the original is explicitly absent; the digest and
count cover all observed buffers, rather than returning a truncated original.
Acknowledged and rejected commands retain this evidence. Timeout, disconnect,
parser refusal and ambiguous writes return an `unknown_outcome` receipt with
whatever receive bytes were observed; no command is resent. Private operation
errors also retain earlier acknowledged command receipts.

The window starts when the serialized command becomes pending and ends when
its acknowledgement is processed or its outcome becomes unknown. An entire
coalesced socket buffer belongs to the window, including any bytes following
an acknowledgement in that buffer. Pre-existing partial lines and interleaved
status/realtime replies may be present. This window is neither an exclusive
probe transcript nor authenticated firmware output. File-transfer and
realtime-only operations do not gain this evidence. Parsed `lines` retain
historical behavior alongside the original bytes.

The planned command payload is separately retained. `sendall_completed` means
only that the local socket call returned; delivery is never asserted. Firmware
identity, complete response, measurement interpretation, physical accuracy and
execution authority remain false. The separately pinned source must pass normal
review and deployment before this contract can be claimed inside an installed
WaveForm gateway. No endpoint, source pin or installed runtime is changed by
this source increment.

## Host transport diagnostics

Snapshots expose `transport_health`, scoped to the current connection ID. The
status and diagnostic arrival windows are separate and bounded to 300 samples
apiece. Status coverage requires reported spindle RPM and target RPM; absent
fields do not inherit a previous value. Arrival ages, mean/p95/max intervals,
gaps and observed RPM changes use the headless host's monotonic receive clock.
The nominal poll cadence (status 0.3 s, diagnostics approximately 1.3 s) can be
delayed by serialized commands, exclusive transfers and host scheduling. An
observed arrival interval is not a firmware sampling interval or network RTT.

Serialized command receipts add `host_timing` with raw monotonic timestamps and
phase durations. Timing begins after command validation/framing, before waiting
for the command owner. It separates command queue time, dispatch preparation and
wire-lock wait, `sendall` duration, send-start-to-parsed-acknowledgment duration,
and acknowledgment-to-host-return delay. An acknowledgment may be parsed before
`sendall` returns; the timestamps retain this overlap instead of clamping it.
The existing `elapsed_ms` remains compatible and keeps its original scope.

Missing acknowledgment or failed transmission leaves the applicable timestamps
and phases absent. Nonfinite, unsupported or inconsistent clock evidence keeps
the command outcome but publishes no timing intervals. The last 64 command timing
records retain connection, outcome and timestamps, without raw command text;
total counts and a retained-window outcome/mean/p95/max summary remain distinct.
Fresh connections reset all windows. A record bound to another connection is
refused by diagnostics without replacing the transport's original receipt.
Snapshots are detached copies. The link's existing condition lock owns updates;
no new worker, connection, polling command, retry or automatic action is added.

These are host observations of serialized command acknowledgments. Real-time
hold/abort/status bytes have no acknowledgment timing here. Firmware sample age,
one-way network latency, physical response and motion completion remain unknown.
No safety, readiness or adaptive-action acceptance is inferred from these fields.
The private JSON-lines `snapshot` method exposes the same diagnostics; existing
clients can continue reading their original fields.

## Closed request boundary

Every method uses the same typed request envelope and closed parameter contract.
Object keys must be unique at every depth, including objects within arrays and
escaped spellings of a key. JSON nonfinite constants and overflowing decimal
exponents are refused. Envelopes retain the 12 MiB line limit; excessive parser
nesting is refused rather than escaping the protocol error handler. Invalid
envelopes emit `protocol_error` and close the child and connection. A dispatched
command whose acknowledgment becomes unavailable retains its original
`unknown_outcome` receipt; protocol refusal does not replay it.

Valid envelopes with invalid method parameters receive an error under their
request ID before occupying the ordinary executor queue. The child can continue
servicing a later snapshot. Request IDs remain single-use even when refused.
Ordinary accepted commands still serialize, and urgent hold/snapshot/cancellation
routes retain their existing ownership behavior. This contract does not add an
automatic retry, connection or actuator action.

Command and transfer deadlines are finite numbers above zero and at most 300
seconds. Booleans and numeric strings are not deadlines. Command read-only
classification requires an actual boolean; strings and numeric flags are
refused. Commands remain a single printable ASCII line of at most 120 bytes.
The same argument validators run at the direct link boundary before ownership
or wire writes. Upload data must be bytes within the existing 8 MiB limit;
downloads take no outgoing payload. Paths, decoded payload bounds, XMODEM/final
Player completion and the pinned probe-application grammar keep their separate
checks. Schema validation is not execution authorization.
