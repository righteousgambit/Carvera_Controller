# Headless supervisor runtime

`python -m carveracontroller.headless --host <private IPv4> --port 2222`
starts a private JSON-lines child. It does not connect until its supervisor
sends `connect`. It does not expose HTTP, accept credentials, decide operator
approval, or reconnect automatically. WaveForm's authenticated edge gateway is
responsible for those boundaries. This runtime remains GPL-2.0-only and must be
distributed with the controller's corresponding source and existing notices.

Each request has an opaque unique `id`, a closed `method` and a `params` object.
Supported methods are `connect`, `disconnect`, `snapshot`, `command`,
`realtime`, `upload`, `download` and `cancel_transfer`. Responses retain that
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
