# Program identity through export, recording and upload

A successfully loaded textual preview has a SHA-256 over its UTF-8 program with
universal newline normalization. This identity belongs to the current selection
only when the loader's completed file key matches that selection. A newly chosen
file does not inherit the previous file's preview hash.

Later effects that use that reviewed selection read the source once and compare
the same bytes against the preview identity before consuming them. LF, CRLF and
CR line endings can describe the same preview; exports and recordings retain and
hash the exact raw bytes they actually read. A changed instruction, invalid UTF-8
or oversized reviewed program stops preparation with a reload/review message.
An explicitly selected file with no matching completed preview remains an
unreviewed file; no preview association is invented for it.

## Export and recording

Portable-job export captures detached local setup declarations on the UI thread.
Program reading, identity verification and archive writing run on the export
worker. The exported program comes from that verified byte buffer, with no later
source-path reopen. One export runs at a time; startup/preparation errors release
the action and report failure.

Residual-stock capture retains the published grid, frozen setup and detached
simulation context without hashing CAD, compressing occupancy or writing a JSON
asset on the UI thread. Simulation and stock-transfer workflows clone published
grids before editing them. The archive worker binds the stored program bytes to the residual context
(accepting the raw or newline-normalized program hash), verifies the captured CAD context,
validates residual placement/material, encodes the grid directly into an embedded
asset, and checks retained CAD payload bytes against their captured hashes. Later
UI replacement of the displayed result does not change the captured export.
Changed context, geometry, conflicting asset references or preparation failure
leave the existing destination intact. `save_package` remains synchronous; the
desktop exporter invokes it on its worker.

Direct `capture_job` callers retain its synchronous
API and apply the same optional preview check.

Recording workers check the same selected-preview identity before constructing
program context. Setup-bound recordings additionally compare the bytes retained
in the setup archive with their recording context, preserving the existing
archive readback checks. Context's program SHA-256 remains a raw-byte digest;
it is distinct from the normalized textual preview hash. These are local
selection/setup associations, not proof of machine execution.

## Upload preparation

An upload request captures the destination directory, firmware mode, compression
setting, connection generation and associated preview identity at the operator's
click. A worker prepares a private file snapshot. A reviewed source is validated
before the snapshot is written; an explicitly selected unreviewed file is copied
without claiming a preview identity. Compression reads and writes within the
private staging directory, so it does not fall back to a shared cache path.

The existing transfer method receives the prepared path and captured target. Its
MD5 input comes from the private raw snapshot; compressed transfers retain that
same raw input for the existing wire protocol. The retained local cache and
selection callback use the captured target even if the browser changes directory
or mode. Snapshot preparation, copying and compression precede transfer commands.

Only one upload preparation/transfer is admitted locally. Known file-transfer
ownership is checked again after preparation, after receiver parking and before
wire transmission. Known owner loss revokes the old request's pending UI effects
even if that owner later releases the transfer flag. Cancellation checks prevent a
prepared or compressed request from starting a transfer. A cancelled request, a
changed connection or a superseded ownership token cannot publish a deferred
selection callback. Decompression waiting retains its cancellation/ownership
state until the completion callback. A newer program selection suppresses the
older selection callback. Completion handlers check the captured session and request before resuming the
receiver, clearing transfer state, publishing cache results or opening reset prompts.
Firmware reset confirmation checks the captured request/connection again at the
operator's Confirm gesture.

Decompression is completed locally only from an observed valid nonzero block
count reaching the expected count. Eight seconds of inactivity ends waiting as
unconfirmed, drops the completion callback and offers a manual file refresh;
timeout is never converted into a synthetic completion count. Repeated, regressing
or invalid counts do not extend the inactivity wait. Stopping the wait
also makes no claim to stop machine-side decompression. Sender bool/FILE_CAN
outcomes do not supply an upload-cache-match receipt, so none is invented.
Reports still do not establish the remote file's exact bytes.

Private staging files are removed when their worker finishes; the existing local
cache remains the retained transfer result. Preparation, compression and worker
startup failures release local admission and show a diagnostic. Binary firmware
selection keeps its existing explicit confirmation flow and has no textual
preview association.

## Acceptance boundaries

Reviewed byte reads retain the existing 64 MiB portable-program budget; recording
archives retain their separate 16 MiB program budget. Unreviewed upload copying is
streamed rather than buffered in memory. File I/O may remain blocked until its
underlying filesystem read returns, even after cancellation is requested.

The desktop generation/ownership checks are not an atomic backend transport lease.
Backend execution ownership, exact bytes acknowledged or installed by a real
machine, installed-controller workflows and physical execution remain separate
qualification gates. Temporary-file tests with a fake transport can verify local
source selection, compression, MD5 inputs, targets and callbacks; they cannot
prove machine-side transfer, decompression or execution. No machine or installed
controller is needed to run those tests.

## Completed local-preview analysis

Ordinary local loading freezes its parser input on the loader worker. After the
matching preview completes, analysis and settings reanalysis consume that exact
text without reopening the source path. A file replaced or deleted after the
read cannot make analysis silently describe different instructions from the
completed preview. Portable-job publication uses its separately reviewed retained
source and transaction commit.

Completion checks the loader generation, selected local/remote paths and parser
identity before finalizing. Analysis publication additionally requires the
completed display hash and file key. A superseded completion cannot finalize or
publish its old preview. Reopening changed bytes under the same path requests new
analysis. Empty local programs clear the previous travel distance and retain a
valid empty-text identity. Failure of the analysis observer does not erase a
completed preview or lose its completion callback.

Initial standalone file inspection and remote-file analysis retain their existing
behavior; only a completed, matching local preview owns this retained association.
These local guarantees do not establish a remote file identity, backend execution
ownership, installed interaction latency or physical machining.

The ordinary loader also retains a display ownership token on the UI thread:
viewer identity, mesh-manager identity and a monotonic identity-publication epoch.
Every identity publication advances the epoch, including repeated hashes and
None. Accepted loader chunks advance the owned token after their renderer work;
a queued chunk or completion cannot adopt an independently cleared/replaced view.
Nonempty previews require the final geometry chunk before successful completion.
Empty previews retain their valid zero-geometry completion route. This ownership
check does not turn the existing shared-state incremental parser into a detached
numeric interpreter or establish an atomic backend lease.

Starting a new ordinary file also retires all exposed prior program arrays,
timing and rotary-preview metadata. Empty files have no final geometry batch,
so resetting only their distance is insufficient: raw line/position/angle data
and rotary mode must also be empty. The new manager owns the empty arrays;
previous retained managers remain unchanged for recovery. Clearing old rotary
metadata permits the schematic machine view again without changing observed
machine pose or declaring physical rotary configuration.

Loader rendering returns its own causal display receipt before publishing UI
progress. The receipt names the originating viewer/manager and the epoch written
by that operation; it is never reconstructed from whatever display an observer
leaves behind. Start, render and progress observers can therefore replace the
view without that replacement being adopted by the pending loader. Completion
rechecks the receipt after notifications. Regression fixtures establish the same
selected-path precondition as production callers and assert completed hash and
nonloading state, so a rejected worker cannot masquerade as successful loading.
