# Reviewed fixed-rack tool exchange

Setup → Tools → **Review physical rack exchange** connects the loaded cutter
library to a physical exchange request through the selected private backend.
The collapsible workflow remains in the workbench; the camera and machine panes
keep their existing layout. Only declared T1–T6 entries are offered. Loading a
cutter or toolset preview still sends no controller command.

Read model and firmware reports on the selected connection, then select a rack
entry and review the exact `M6 Tn` request. The source adapter admits the reported
C1 / Community 2.1.0c dialect with an ATC feature report. CA1, other firmware,
manual/probe tool numbers and a tool already reported in the spindle are refused.
Reports are unsigned; they do not authenticate the controller or prove physical
rack contents.

The immutable review binds the private child, connection, complete selected
machine profile, local toolset, selected cutter geometry/metadata, nominal setup
and reported position, coordinate mode, tooling and overrides. It expires after
30 seconds. Request admission requires fresh Idle/no-job status, zero measured
and target spindle RPM, a recent spindle-disabled diagnostic, complete reported
XYZ and no active transfer or unresolved backend outcome. The original limits
remain in effect if constructing or reading the review takes time.

The workflow retains an exclusive durable intent before submission, refreshes
private cached state off the UI thread, then checks the current UI context and
queues the fixed operation in the same callback. An expired or abandoned final
callback cannot subsequently enqueue an exchange. Original IPC response bytes,
controller receive windows and exact reviewed plan are checked and retained.
Partial, refused or uncertain results are preserved without automatic repeat,
rollback or recovery motion. Result-retention failure leaves the on-disk attempt
unresolved and the in-memory result available for export.

The result has distinct phases:

- `exchange_pending`: retained intent; submission outcome may be unknown.
- `exchange_acknowledged`: the original command receipt acknowledges the reviewed
  request. Completed motion is unconfirmed.
- `target_tool_reported`: a later fresh status on the same connection reports
  Idle, stopped spindle and the requested tool number. A still-fresh packet
  received before acknowledgment cannot establish this transition.
- `not_submitted` or `exchange_unresolved`: admission, transport, receipt or
  durability failed. No automatic command is replayed.

The later report is retained asynchronously, even if the collapsible controls
are hidden. Another exchange through this panel is unavailable while the
acknowledged exchange awaits its matching later report. Export uses a new file
and reads it back; an existing receipt is preserved. Inspecting retained attempts
reads bounded historical chains and never resumes a command.

A reported tool number is not physical cutter/assembly identity, measured TLO,
collision clearance or machining qualification. The workflow does not change a
loaded preview assignment, calibrate tool length, write tool offsets or adopt a
status value as a dimension. Random magazines, arbitrary logical-tool/pocket
maps, manual collet changes and other machine adapters require separate supported
workflows and qualification. Installed and hardware acceptance remain open.

Opening a review performs one background private-state read, bound to the click's
selected cutter, identity and setup. This reads the child's cache rather than
sending a firmware command. A stale cache at an exchange click receives at most
one equivalent refresh before the unchanged expiring-review checks. Background
cache polling is independent of local receipt import/export and history reads.

The desktop job-start/resume, machine-file upload, probe-setting application and
tool-exchange flows use reciprocal idle-transaction admission. A pending exchange
or a submitted result with unresolved retention remains owned by its original
connection. A later matching Idle/tool report must also be retained before that
exchange ownership clears. A replacement control owner cannot inherit or replay
it; the old receipt remains historical and unconfirmed. Realtime hold/stop stay
separate. These UI checks do not implement firmware interlocks, physical
reconciliation or an execution adapter for another machine.

Machine-file transactions defer background private cache reads until the owned
UI finish. Their explicit post-transfer state read remains part of the worker,
after the retained transfer result. This preserves durable intent ordering;
incoming status events and urgent hold/stop requests remain independent. A retired
file panel keeps its active deferral until the worker finishes retaining the
outcome, and an old finish cannot release a replacement transaction's ownership.

The legacy GUI heartbeat watchdog also respects command ownership. While the
private backend is selected, that watchdog cannot close a dormant GUI transport
or initiate its reconnect UI. A lost selected backend remains selected until an
explicit eligible handoff; its own diagnostics report its connection health.
