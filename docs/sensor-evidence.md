# Sensor evidence, probing and recovery

The controller records the existing machine's observations with their source,
availability and timing. Firmware additions use the configured C1/CA1 pins;
they do not add an encoder, torque/current sensor or pressure sensor.

## Workflows

- Run evidence is collected during normal status reception. The bounded JSONL
  file lives under `KIVY_HOME/adaptive` (64 MiB per file). `evidence status`
  shows current context; `evidence export <path>` saves and reads back a bounded
  snapshot. `evidence replay <jsonl>` exercises the production parser and shadow
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
  held-out session with matching setup; maximum residual plus declared reference
  uncertainty must fit the selected limit and improve on the mean-tip baseline.
  Applying a correction creates one derived inspected-axis result and preserves
  its raw source. It sends no offset or motion commands.
- `recovery status <line>` reports blockers and an exact verification scope.
  `recovery verify <JSON>` records explicit program/position/origin/tool-offset/
  clearance checks, scope, clearance_machine_z_mm, start_line and operator_note.
  Verify the requested SD file matches the loaded local program. Local SHA-256
  alone does not establish SD bytes. Tool/WCS preparation must precede a fresh
  verification. Partial execution requires fresh idle telemetry, firmware boot
  identity, finite unit-qualified pose and identical program/line/file/pose/
  offsets/rotation/modes. The approach uses absolute millimeters and restores
  verified file modes/native feed afterward. Preview remains available.

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

Raw `PRH` contact receipts retain source clock, step-derived position, approach
masks, planner feed and drop/availability information. Compound cycles retain
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
