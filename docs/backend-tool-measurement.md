# Reviewed setter measurement and calibration receipts

Setup's Tools section and the calibration bench open a measurement pane for the
current reported T0–T6 on the selected C1 private backend. The operator declares
the installed probe or cutter kind, chooses one to five setter repetitions,
reads the connection's model and firmware, and reviews the physical M491 action.
The supported reported identity remains C1 / Community 2.1.0c; it is not signed
firmware attestation or physical tool identification.

The review expires after 30 seconds and binds the session, connection, profile,
declared tooling, setup, selected assembly revision, passport-store identity and
generation, repeat count, and installed-kind assertion. A durable intent precedes
submission. The final UI callback rechecks that context and fresh Idle/stopped
spindle status before calling the existing operation API. A late callback,
changed context, missing durable intent, or overlapping job/probe/exchange blocks
submission. Existing startup and operation deadlines are preserved.

Acknowledgement is distinct from later output and later reported Idle status.
An acknowledgement alone, with no samples or observed activity, remains
unresolved and blocks other idle workflows on that connection. Failed, dropped,
retired, or uncertain attempts are retained without automatic replay. Real-time
stop controls remain independent.

## Original bytes and normalized late text

The client retains original private IPC responses for `tool.measure`. Its
independent bounded text cursor also retains original IPC events for normalized
unsolicited output, with session/connection, sequence, host times, original IPC
bytes and hash, loss counts, and explicit normalization/truncation/attribution
limits. Cursor reads never drain another consumer or send a command.

An M491 acknowledgement may precede its asynchronous calibration output. The
current fixed transport producer forwards that late output as normalized text;
it does not retain its original controller socket bytes. Such events are saved
and can be inspected/exported, but cannot become byte-qualified millimetre
calibration in the passport. Full late-output qualification requires the
transport owner's additive original-byte receipt contract. The producer files
`headless/link.py` and `headless/__main__.py` remain unchanged in this lane.

When a complete repeat block is present in the existing original command receive
window, the consumer validates original IPC and controller bytes, hashes,
connection, planned command, acknowledgement, exact bounded grammar, sequential
sample indexes, printed selection, spread and edge indexes. Samples use the
pinned source contract: probe machine Z minus configured `reference_tool_mz`, in
millimetres, independent of nominal stickout. The configured numerical reference
and physical accuracy are not inferred. Receive windows may contain interleaved
or unattributed output; causal command attribution remains unverified.

Community revision `feab653def96a959e695049a4f828aeddbcd5547`,
`src/modules/tools/atc/ATCHandler.cpp` lines 1869–1906, prints the highest sample in
the `Using TLO` sentence while saving the lowest sample to the robot offset.
Consequently the new receipt preserves the printed selection separately and
leaves `applied` unknown. It does not change the legacy parser's historical
contract. A single setter pass may emit no repeat block; no sample is invented
from the raw status offset.

After a later reported Idle/tool observation, byte-qualified sample blocks can
be saved as unassigned passport receipts. Import revalidates the original
response, retains its source evidence and reference, journals intent, and uses
the attempt identity to avoid duplicate capture. Neither a logical tool number
nor an assembly is assigned automatically. The passport's existing explicit
operator-attribution review links the samples to an assembly. Bench and passport
views display the source-reference limits, with applied TLO still unknown.

Installed execution, physical setter travel, actual offset application, tool
identity, collision clearance and metrological qualification remain separate
acceptance gates.
