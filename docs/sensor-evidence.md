# Sensor evidence, probing and recovery

The controller records the existing machine's observations with their source,
availability and timing. Firmware additions use the configured C1/CA1 pins;
they do not add an encoder, torque/current sensor or pressure sensor.

## Workflows

- Run evidence is collected during normal status reception. The bounded JSONL
  file lives under `KIVY_HOME/adaptive` (64 MiB per file). `evidence status`
  shows current context; `evidence export <path>` saves and reads back a bounded
  snapshot without replacing the live journal. Queued, durable and dropped records
  are reported separately. Disk IO uses a bounded worker so telemetry reception
  does not wait for journal fsync. `evidence restart` preserves unfinished records
  in a durable forensic sidecar before opening a new journal; it preserves the old
  file. Interrupted submitted probe sessions are retained on orderly application
  exit. `evidence replay <jsonl>` exercises the production parser and shadow
  monitor with recorded arrival times. Replay requires disconnected controllers
  and stopped receive threads and sends no machine commands.
- The adaptive popup has cutter/material recipe and outcome entry actions.
  `adaptive recipe <JSON>` accepts cutter, material, operation, rpm, flutes,
  programmed_feed_mm_min, chipload_min_mm and chipload_max_mm. No cutting values
  are supplied automatically. The executing operation, units, nominal feed and
  RPM must match. Minimum/maximum overrides derive from chip load, RPM, flute
  count and nominal feed. Proposals remain shadow-only. `adaptive outcome
  <JSON>` associates operator measurements/finish/tool observations with exact
  program and operation proposals; this does not establish safe active control.
- `adaptive baseline` requires five seconds of stationary spindle observations.
  Tool assembly/revision/seating/assignment, accessory commands, source boot,
  target RPM and temperature changes invalidate the baseline. Stationary motion
  and an operator declaration do not independently sense an unloaded spindle.
- The CMM workbench and `measurement evidence` action open measurement setup,
  durable receipts, tool-setter trends and directional map qualification.
  Declare the physical probe, seating/configuration, approach, reference and
  before/after-cut phase. Unknown context stays null. Maps require an independent
  held-out session with matching setup; maximum residual plus the sum of declared
  fit and held-out reference uncertainty must fit the selected limit and improve
  on the mean-tip baseline. Both reference uncertainties are required for
  qualification. Changed setup or overlapping commands after a failed receipt
  prevent correction; actual direction must match the selected inspected axis.
  Applying a correction creates one derived inspected-axis result and preserves
  its raw source. It sends no offset or motion commands.
- `recovery status <line>` reports blockers and an exact verification scope.
  `recovery verify <JSON>` records explicit program/position/origin/tool-offset/
  clearance checks, scope, clearance_machine_z_mm, start_line and operator_note.
  Verify the requested SD file matches the loaded local program. Local SHA-256
  alone does not establish SD bytes. Tool/WCS preparation must precede a fresh
  verification. Partial execution requires fresh idle telemetry, firmware boot
  identity, finite unit-qualified pose and identical program/line/file/pose/
  offsets/rotation/modes. The recovery review dialog requires an explicit preview,
  all five checks, finite clearance, a note and a durable verification before its
  Run action. Opening it bypasses normal pre-job hooks and origin application.
  The approach reconstructs the program boundary, retracts before XY motion and
  starts the spindle before descent, then restores supported modes and physical
  feed. It never repeats a tool change or relies on the viewer cache.
  Delayed callbacks are cancelled by stop, alarm, manual command, disconnect,
  timeout or changed scope. Current firmware rejects G20, so production recovery
  refuses imperial prefixes. The mathematical parser's inch conversion tests do
  not establish machine support. O-code, unresolved coordinate changes and
  unsupported motion remain explicit refusals.

## Firmware evidence

Additive numeric status fields identify source boot/sequence/clock/validity,
raw configured inputs, executing versus parsed motion, spindle transient
statistics, ATC stage timing and fault persistence. Clock domains remain distinct:
firmware snapshot time, cached measurement age, probe-contact latch time and
host arrival time do not imply synchronized clocks or one-way transport latency.

`M964` reads bounded history only while idle or halted. `M964 L1` reads the last
validated persisted fault. Explicit idle/unhalted `M964 R1` rearms the frozen
ring. History/dump headers and completion receipts identify original boot and
record count; incomplete dumps are explicit. Firmware preserves a 16-event ring
and persists a frozen fault to alternating SD slots with integrity checks and
readback. Missing/unwritable SD storage is reported as unavailable/failure,
not successful preservation. Reset/power interruption before persistence remains
an unqualified case. Boot counters are scoped to their retained SD state;
replacing or restoring that state does not establish globally unique identity.
Boot issuance reserves and reads back mirrored counter records. Fault persistence
flushes the payload before writing its commit header; readers check exact file
length, CRC, sequence/timing and the final fault record. The filesystem has no
fsync API, so closed-file readback is not a power-interruption durability proof.

Raw `PRH` contact receipts retain source clock, step-derived position, approach
masks, planner feed and drop/availability information. A two-contact queue
reports overflow independently of later contacts through `SQ` source telemetry;
its rearm result must be read from a fresh post-request source sample. Compound cycles retain
individual contacts separately from their final interpreted measurements.
Position means issued-step accounting or a planner milestone as declared;
feed means planner/commanded velocity. PWM means a drive command. Binary driver
alarms do not identify a cause or provide encoder position. ATC retry counts
remain unknown when not measured.

RPM stall detection defaults disabled. Its spin-up, stopping, target-change,
low-speed, persistence and clock-wrap logic has host tests. Enabling it requires
on-machine false-alarm and detection qualification.

## Requirement coverage

| Item | Implementation |
| --- | --- |
| 1 Run recorder | Packet context, program hash/operation, tool/TLO, thermal/accessory/fault records |
| 2 Fault snapshot | Frozen pre-fault ring, original execution context, SD persistence/readback |
| 3 Missing values | Presence/validity masks and Unknown displays |
| 4 Source timing | Firmware clock, cached sample ages, contact latch and host arrival retained |
| 5 Identity/order | Persisted boot counter, sample/event sequences, gaps/reset/reordering detection |
| 6 Alarm inputs | Configured axis/spindle raw inputs; guidance separates observation from diagnosis |
| 7 Position/feed labels | Step/planner semantics and explicit units; PWM is not torque |
| 8 Execution attribution | Current block source line separate from player parsed progress/queue |
| 9 Background events | Firmware ring plus bounded diagnostics polling and automatic fault retrieval |
| 10 Setter trends | Physical assembly/revision/seat/settings groups, phase/temperature/spread |
| 11 Probe sessions | Submitted command, raw contacts/transcript, setup/reference/WCS context persisted |
| 12 Directional correction | Saved maps, held-out uncertainty guard, explicit derived-axis application |
| 13 Baseline conditions | Tool/custody/accessory/RPM/temperature/boot invalidation |
| 14 Recipe bounds | Chip-load-derived floor/ceiling with operation/feed/RPM/unit matching |
| 15 Outcome evaluation | Program/operation-scoped proposal and operator-outcome associations |
| 16 Spindle transients | Internal count/min/max/mean/variance/saturation/recovery statistics |
| 17 Stall qualification | Disabled-by-default detector, explicit startup/stop/low-speed test cases |
| 18 ATC events | Stage timing/transitions and tool/offset context; unmeasured retries unknown |
| 19 Recovery | Exact scoped operator checks, target tool/WCS consistency, unit-qualified approach |
| 20 Replay/regression | Actual production parser/advisory, recorded controls/declarations, reset/gap/fault tests |

Source tests, ARM compilation and UI inspection are separate from physical
qualification. Installation, interrupt timing, reset/SD durability, probe accuracy,
ATC repeatability, recovery clearance and cutting-result validation require
machine evidence before those gates can close.

## Machine qualification sequence

Retain the installed binary, effective SD configuration and current calibration
before installing a candidate. Record the candidate commit and binary hash in
each qualification session. The following gates need operator-observed results:

1. Compare telemetry validity, units and raw input transitions with the actual
   C1 sensors, including disconnected/unavailable measurements. Measure the
   longest interrupt-masked evidence capture against motion timing requirements.
2. Exercise an idle test halt and controlled restart. Retrieve `M964` and
   `M964 L1`, checking original boot, event count, execution context and SD
   readback. Test unwritable storage and interrupted persistence separately.
3. Run repeated TP06/reference contacts and setter measurements with declared
   assemblies, seats, approach settings and temperatures. Fit on one session and
   qualify directional corrections on independent held-out measurements.
4. Exercise ATC stages with observed pocket/tool identity and compare timing and
   setter spread across cycles. Unmeasured retries remain unavailable.
5. Verify recovery on a millimeter air-cut program with a cleared envelope, known
   origin, prepared tool/TLO and matching SD program/line boundary. Test absolute
   and anchored relative modes, G53 followed by work-coordinate anchors, changed
   verification scope and cancellation while waiting for pause or issuing commands.
   Recovery requires explicit G17/G18/G19 and G94 in the prefix, live G90 before
   verification, and stored physical lines of at most 128 UTF-8 bytes including
   line endings, without NULs. The local program
   hash does not prove on-machine line numbering, especially through legacy M28
   upload paths that split blocks. Do not use a partially cut part for this gate.
6. Collect unloaded baselines and shadow proposals against inspected cutting
   outcomes for each declared recipe. Active control remains unavailable until
   detection, transport delay, chip-load bounds and outcomes are qualified.
7. Qualify the optional stall detector's startup, commanded stop, low RPM and
   actual stall cases separately, recording false alarms before enabling it.

## Hardened source boundaries

Status records carry compact program metadata; full operation manifests are
recorded separately. The latest 4096 operations are retained with explicit dropped
counts. Source sequence rollover is valid; backwards time within a verified boot,
malformed/trailing frames, duplicate JSON keys, nonfinite values, reordered dump
records and incomplete journal tails are rejected. Rejected replay metadata does
not change the following valid packet's context. Receive threads retain custody
through disconnect so offline replay cannot overlap a lingering transport loop.

Durable journal IO is host-tested on macOS. Windows currently refuses that IO
explicitly because the tested locking/positional-read/directory-sync protocol is
POSIX; Linux runtime qualification is also open. Existing package-level mypy
failures are compared against the exact committed baseline separately from clean
strict checks of the new machine modules.

Firmware dispatch now normalizes balanced comments before classifying executable
lines, handles parser-accepted signed/spaced integer distance modes, and rejects
unsupported decimal G90/G91 variants before block effects. Text and file payloads
are classified by the same helper used for command splitting, including opaque
commands later in a block. Malformed comments halt before dispatch. These source
fixes and host tests do not replace an air-cut qualification of uploaded programs.

Recovery writes are serialized and owned by an attempt token. Operator controls
signal cancellation before waiting for the transport lock, preventing the next
approach or resume write. Cancellation requests `abort -R <nonce>` and blocks
motion, file transfer and new recovery until the matching `{RB:1,<nonce>}` and a
subsequent valid Idle pose arrive on the same connection generation. Firmware
clears deferred Player queues at abort entry, including the no-file path, and
emits the receipt only when abort handling returns. This proves queue disposal,
not physical stopping. A halted machine ignores Player commands: explicitly
Unlock if appropriate, then Abort to retry disposal. A missing receipt remains
blocked; reconnecting or clearing the local stop flag cannot erase that gate.

WiFi command writes require complete transmission; unavailable USB links or short
USB writes are failures. A send receipt never establishes firmware execution.
Recorder restart and parser admission share a lifecycle lock, so a received event
cannot be lost into a detached writer. Failed/pending records remain recoverable
through explicit restart or exit sidecars with separate durability receipts.

Overlapping probe commands preserve both session identities even before the first
reply. Subsequent contacts are marked ambiguous across receipts and restarts.
An operator must declare a completed boundary with fresh Idle, no active cycle,
and no pending commands before clean attribution resumes. Loaded qualifications
require exact Boolean flags and are recomputed from held-out observations before
correction; an edited or malformed passing flag cannot authorize a correction.
