# Backend controller job files

The Program workbench has a **Machine file** task for the explicitly selected
backend connection. It retains a file transaction independently of the GUI
controller. Starting the private backend, connecting it and selecting it as the
workbench owner remain separate actions.

1. Choose a local program, then **Freeze selected program**. The task reads up to
   8 MiB off the UI thread, retaining the exact UTF-8 bytes, source revision,
   machine profile, setup geometry and operator evidence, child session and
   connection identity.
2. **Upload frozen file** writes a content-addressed file under `/sd/gcodes`.
   The action requires a recent backend Idle report, no playing job, zero actual
   and target spindle reports, and an unambiguous selected connection. An
   acknowledged transfer does not verify the controller copy.
3. **Read back & verify** downloads that file through the actual private child's
   XMODEM transfer API. Verification compares every returned byte against the
   frozen source, plus the transfer path, size, digests and completion receipt.
4. **Review start command** asks the child to compile `job.start` for the exact
   verified path. The compiled plan is checked against the closed operation
   contract and shown in **File identity & receipts**. This sends no `play`
   command and grants no execution permission.

The pending intent is durably journaled before submitting a machine file write.
Each attempt has its own append-only JSONL file in `~/.carvera/backend-jobs`.
File reads, base64/JSON request encoding, transfer waits, byte comparisons and
durable journal writes run off the Kivy thread. The selected owner's urgent
hold/abort request capacity remains independent of the ordinary file request.
The transport refuses realtime bytes while an XMODEM transfer owns framing.

Changes to source selection or its stat revision, profile, geometry, operator
evidence, child or connection invalidate use of an earlier attempt. Old receipts
remain available. An unresolved transfer or mismatched readback is never replayed
automatically. A new frozen attempt is a distinct explicit action; it cannot
bypass the backend's unresolved connection state.

## Reviewed backend job lifecycle

5. **Read machine identity** sends the closed read-only `model` and `version`
   queries to this connection. The app retains the original receive windows,
   exact query plans and RPC receipts before parsing. The supported dialect is
   C1 (numeric model code 1) reporting `2.1.0c`, with feature bits matching its
   fresh status. These are unsigned reports, not authenticated firmware attestation.
6. **Review machine run** binds the verified controller path to the selected
   profile and all four current operator measurement groups: stock, workholding,
   tools and offsets. The review shows the source/hash, reported WCS/tool/position,
   measurement methods and expandable setup values. Firmware WCS index 0 is G54;
   indexes 6–8 are G59.1–G59.3. A fresh Idle/no-playing/zero-spindle report is
   required, and the review expires after 30 seconds.
7. The explicit **Start reviewed program** gesture authorizes this single closed
   `job.start` plan. Its pending intent is durably saved off the UI thread. Before
   submission, the UI rechecks the retained child/connection, profile/setup,
   measurements, review age and reported position/tool/WCS/overrides. A changed
   or retired context prevents submission. There is no automatic retry or replay.
8. An original command ACK is retained separately from subsequent reports.
   **Pause job**, **Resume job**, and **Cancel job** use the retained Player job
   operations through the same owner. Resume rechecks setup/context/identity.
   A cached pre-transition report cannot erase a pause/resume/cancel ACK. A
   subsequent fresh Run/Pause report establishes only reported playing/paused
   state; Idle after observed playing establishes only reported settled state.
   It does not establish successful machining or completed motion.

The Program workbench's Pause and Abort actions route to these job operations
when this private backend is selected. Feed hold and STOP remain the backend's
existing realtime controls; hold-resume additionally checks the retained job
context and current evidence when a reviewed job is active. Retiring the source
panel never replays a pending job, and an unresolved result retains its evidence.
There is no GUI-controller fallback. The file's top-level `execution_admitted`
flag stays false because file provenance itself grants no permission; the nested
job run records the separate operator approval and exact command/report history.

## Remaining qualification gates

Source tests exercise the real private child and socket/XMODEM/Player workflow
against a loopback fixture. They do not prove the installed desktop package,
actual device firmware, physical tooling/setup, successful machining, or adaptive
execution. Those gates remain separate. During binary file transfer, the
transport owns framing and refuses realtime bytes; independent RPC capacity does
not imply a realtime command can interrupt an XMODEM frame safely.
