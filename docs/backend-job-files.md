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
hold/abort lane remains independent of the ordinary file request.

Changes to source selection or its stat revision, profile, geometry, operator
evidence, child or connection invalidate use of an earlier attempt. Old receipts
remain available. An unresolved transfer or mismatched readback is never replayed
automatically. A new frozen attempt is a distinct explicit action; it cannot
bypass the backend's unresolved connection state.

## Remaining execution gates

A compiled profile identifies the backend's command dialect, not the firmware
actually installed on the CNC. Measured setup receipts represent operator
reports, not independent physical qualification. The backend job start/resume
workflow still needs actual firmware identity, reviewed setup admission, exact
operation receipts and subsequent machine-state observations. File provenance
does not establish motion completion, installed application qualification or
physical machining results.
