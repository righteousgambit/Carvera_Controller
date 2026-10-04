# Bank program compilation and review

The Program workbench's bank board opens **Review mapped bank program**. Compilation
runs in the background; an older callback cannot replace a newer review or a
different program/machine/bank context. The review displays logical tools versus
controller tool numbers/pockets, inherited modes, omissions and a source/draft
comparison. Only the first 300 lines and 96,000 characters are rendered; export
retains the complete bank source and comparison.

The compiler implements the six-fixed-pocket Carvera candidate plan. It defers
source T preselection to each M6 and makes that M6's mapped tool explicit. This
handles a preselection in the preceding bank without moving intervening cutting
motion to the new bank. Every source line has a locator and original text; source
comments, collet S words and unrelated words survive the edit. An M6 combined
with motion or other M commands is rejected. Probe and empty-spindle tools need
separate classification. This adapter is not a random-pocket changer adapter.

Automatic-offset mode rejects H indexing. A separate explicit convention permits
G43 H values only when they match the active logical T number and maps them to
the controller index. Arbitrary H indexes are not assumed to be tool numbers.
Expressions, conditional blocks, macro/subroutine flow, rotary words, checksum
blocks, duplicate scalar words and unsupported modal commands are rejected. A
draft with compilation errors has no compiled body. Compiler acceptance covers
this transformation; it does not qualify every instruction for machine execution.

Later banks display their inherited units, plane, feed mode, WCS, arc-center mode,
feed, distance mode and original modal state. The modal restoration list excludes
motion, tool changes, tool offsets, accessories and spindle restart. Missing modes
and inherited motion/spindle/accessory state stay visible as review requirements.
No stop/retract, approach or re-entry trajectory is invented from program Z.

**Export review JSON** creates a new local file under `~/.carvera/bank-drafts`,
then compares the decoded destination with the reviewed document. The document
contains the program hash, bank/range, mapping, source/draft lines, inherited state,
errors, cautions and a deterministic content digest. It explicitly declares
`execution_available: false`; export produces no runnable `.nc` file and invokes
no controller, upload, calibration, configuration or playback method.

## Execution remains open

Complete bank execution still requires a supported backend transaction for verified
stop/retract, physical reload, identity reconciliation, measurement after seating,
offset readback, source-to-controller tool mapping and collision-qualified approach
and re-entry. A logical T7 receipt does not establish controller T1 calibration
after reloading pocket 1. Existing preparation counts remain logical-tool receipt
attribution, not mapped controller offset acceptance. Those gates and the overall
controller completion goal remain open.

Focused tests cover preselection across boundaries and during preceding-tool motion,
comment/collet preservation, explicit H conventions, inherited modal evidence,
unsupported source rejection, special tools, immutable source, exclusive exports,
destination readback and stale background UI results.
