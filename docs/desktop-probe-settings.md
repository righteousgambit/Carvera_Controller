# Probe settings in the workbench

Open **Machine → Probe**, or use the command palette's **Open machine probe**.
The task lives in the existing workbench: both media panes retain their space.
It uses the selected private backend; there is no fallback to the job controller.

The local preset card accepts a name, a declared probe kind, tip diameter, ATC
TLO correction and a note. Dimensions accept millimetres, inches and expressions;
plain decimal millimetre tokens retain their exact spelling. Zero and a missing
SD setting remain distinct. Probe kind is local metadata; applying these values
does not configure probe pin polarity or establish calibration.

**Load saved presets**, **Save local preset**, and **Import/Export presets** run
local file work off the UI thread. Storage defaults to
`~/.carvera/probe-settings/presets.json`. Files have schema 1 and at most 256
uniquely named presets. Duplicate keys, nonfinite or oversized files, invalid
decimal tokens and malformed existing stores refuse rather than replacing them
with defaults. Creating the panel reads or writes no preset file. Existing export
files are not overwritten; choose a new destination.

For machine settings:

1. Select the connected backend as the workbench owner. **Read actual SD
   settings** sends only the fixed `probe_profile_read` request. Original IPC
   bytes and controller receive windows are retained, then independently checked.
2. Select or enter a preset and **Review preset application**. Review displays
   the exact before/after tokens and binds the preset, saved machine profile,
   child session and controller connection. It expires after 30 seconds.
3. **Apply reviewed SD settings** requires fresh matching model reports, Idle,
   no playing job, zero spindle reports and a disabled spindle diagnostic.
   The worker fsyncs an exclusive pending intent before submission. It refreshes
   the private cached state and returns to the UI thread for the final context
   and freshness check in the same callback that queues the fixed apply request.
   A timed-out or retired callback cannot later submit it.
4. The existing producer rereads both original values before writing either key,
   writes the two fixed keys, then reads both back. The workbench independently
   validates the original windows, exact tokens, chronological receipts and
   unchanged proof flags before reporting **reported SD values match**.

There is no automatic retry, rollback, restart or replay. A partial write, lost
acknowledgement, changed context or receipt-durability failure clears the review
and baseline. Read actual settings again and create a fresh review. A backend
with an unknown outcome additionally requires its existing explicit recovery
workflow; the Probe pane cannot bypass that state. If result journaling fails,
the original response remains in memory for **Export latest receipt**, while the
on-disk pending intent remains unresolved. Exporting it does not resolve the old
acknowledgement or durability gap.

Each read/application gets an exclusive file in
`~/.carvera/probe-settings/receipts/`. Rows are fsynced, read back and hash-linked.
The hashes detect inconsistencies; they do not authenticate the controller or
protect against replacement of the entire chain. **Inspect retained attempts**
checks at most 512 receipt files and shows recent results, including incomplete
or unresolved attempts. It never sends a request or replays an intent.

Matching SD text does not verify active ATC TLO, persistence after restart,
firmware identity, completed motion or physical accuracy. The pinned firmware
initializes ATC TLO at startup. This task leaves those claims unverified and
performs no restart. Source/native tests use a private child with loopback
fixtures only; installed and physical qualification remain separate gates.

The accompanying job-review fix takes one background private `snapshot` read
when a Start/Resume click encounters an outdated cache after building its review.
It then uses the original expiring run, setup/context checks and admission limits.
The existing intent journal and final post-journal state check still precede any
job command. No command is automatically retried or replayed.
