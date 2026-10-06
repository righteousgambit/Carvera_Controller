# Further desktop, commissioning and process requirements

These 25 recommendations extend the existing 325 requirements to 350. They
remain within the active implementation objective. Related mathematical engines,
source checks and preview controls do not establish installed interaction,
backend execution or physical qualification.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Constraint-driven workbench | Compact/normal/expanded layouts, meaningful table columns and preserved media proportions at native widths |
| 2 | Illustrated parameter editing | Live highlighted geometry, previous/draft values and precise dimension definitions |
| 3 | Offset consequences | Tool/WCS/wear correction displacement and affected features before supported application/readback |
| 4 | Setup canvas | Plate-hole snapping, jaw contacts, datum selection and reversible precise placement |
| 5 | Guided camera alignment | Reference selection/coverage, raised-stock distinction, measured calibration and residuals |
| 6 | Machining cursor | Frame-bound depth/allowance/fixture/source context with persistent inspection |
| 7 | Spatial problem navigator | Location/operation grouping, framed evidence and explained remedies |
| 8 | Practical tool substitution | Actual assembly reach/corners/depth/clearance/process differences and replacement reconciliation |
| 9 | Setup handoff | Revision-bound hole addresses/orientation/protrusion/assemblies/datum/checks, tablet/print review |
| 10 | Interruption-aware interface | Pause-specific information, retained drafts and return to normal context |
| 11 | Program-to-feature map | Model feature links producing operations/tools and actual inspection results |
| 12 | Commissioning signals | Backend named signals, component association, transitions and timestamped observations |
| 13 | Gantry squaring | Per-joint homing events, synchronized backend behavior and measured alignment |
| 14 | Servo commissioning | Command/feedback/error/velocity/effort capture, bounded experiments and before/after receipts |
| 15 | Volumetric errors | Measured position/straightness/squareness maps, configuration/date and qualified supported compensation |
| 16 | Five-axis calibration experiments | Informative measurement poses, parameter observability, raw measurements and fitted residuals |
| 17 | Kinematics switching | Actual joint/Cartesian/TCP modes, transition preview, position reconciliation and capable backend |
| 18 | Gravity/counterbalance | Head/tool/payload load model, documented restrictions and actual drive observations |
| 19 | Workpiece deformation | Before/clamped/released measurements distinguishing machining error and clamping/stress effects |
| 20 | Instrumented workholding | Required/observed pressure, operation association and actual machine-side permissives |
| 21 | Coolant process | Operation delivery/pressure/flow/nozzle requirements and actual observed delivery |
| 22 | Condition-based maintenance | Sensor/service history associated with affected operations and readiness |
| 23 | Polar/cylindrical machining | Backend interpolation semantics, programmed/rotary/surface geometry and qualified execution |
| 24 | Grinding/dressing | Wheel geometry/dress history/effective diameter/allowance, dedicated removal model and inspected outcomes |
| 25 | Robot/load coordination | Machine/gripper/pallet/part ownership, requests/completion and qualified backend coordination |

LinuxCNC references: [HAL](https://linuxcnc.org/docs/stable/html/hal/intro.html),
[homing](https://linuxcnc.org/docs/stable/html/config/ini-homing.html), and
[kinematics](https://linuxcnc.org/docs/stable/html/motion/kinematics.html).
The current LinuxCNC declaration is offline; it is not an execution transport.

## LinuxCNC status-channel implementation checkpoint

`machine/linuxcnc_status.py` now opens the actual optional `linuxcnc.stat()` NML
channel and polls raw Cartesian position, distinct linear/angular joint units,
commanded/actual joint positions, following error, velocity, homing/fault/limit
flags, digital/analog I/O and task/interpreter/motion state. Poll failures clear
the last observation and break transition continuity. Sample changes retain both
observation timestamps; these are intervals, not exact machine-side event times.
No joint-to-axis mapping, servo effort or HAL signal naming is invented.

On a LinuxCNC host, use its Python environment from the checkout:

```sh
python3 -m scripts.capture_linuxcnc_status --machine-id mill-1 --output capture.jsonl --samples 100 --interval 0.1
```

The bounded capture creates a new file exclusively, hashes the observed INI on
each sample, retains poll/configuration failure records and emits completion only
after every requested sample. An INI hash excludes included HAL/configuration
files and therefore is not a complete machine configuration fingerprint. Both
reader and capture open no command channel. Run capture off the desktop UI thread.

All 59 status/capability checks pass, including API entry, inch/angular unit
retention, immutable observations, stale/poll-failure invalidation, malformed
status rejection, homing/I/O sample transitions, topology/unit continuity, configuration change and
exclusive evidence writing. These use an injected status fixture, not a running
LinuxCNC simulator. Local live NML, simulator/physical qualification, integrated
commissioning UI, named HAL signals and LinuxCNC execution remain OPEN. The
existing declaration remains execution unavailable. This is a real status API
integration with source verification, not a completed industrial backend.

The first hosted status-source attempt (run 37445886161) failed both mypy hooks
on numeric object narrowing and reused transition loop variable types. The
correction explicitly narrows finite numeric values, rejects conversion overflow
and separates joint/I/O variables. Strict checking of the changed reader passes;
59 regression checks and full Ruff/format checks pass. Local broad mypy attempts
also traverse excluded dynamic addon imports and report existing addon issues;
those do not establish the hosted full-package gate. Full failed logs are retained.

## Historical commissioning inspector checkpoint

The Machine workbench now includes an expandable-by-import commissioning capture
review. Its shared file picker accepts JSONL; bounded parsing runs off the UI
thread and stale results are rejected. An existing review survives import failure.
First/previous/next/last sample navigation and joint selection retain raw units,
commanded/actual/following-error/velocity, home/drive/fault/limit state and sampled
I/O changes. Clear detaches the review, releases focus and rejects pending imports.
It does not change the connected Carvera, saved setup or capability evidence.

Import checks version/backend, identity and INI digest continuity, consecutive
samples, finite poses/joint data, units, UTC timestamps and terminal completion
counts. Capture parsing is bounded at 20 MiB / 10,000 samples with bounded strings
and channel arrays. Imported transition assertions are ignored and recomputed
from observations. Partial/failure records remain incomplete; loaded captures
are explicitly historical and their source is unverified. File/INI hashes bind
bytes, not actual machine provenance. I/O and transitions use a bounded overview;
full channel browsing and component/HAL signal association remain OPEN.

All 39 capture/status/capability-inspector checks pass, plus two workspace/panel
smoke checks. Both changed machine modules pass strict mypy; full Ruff/format
and both architecture contracts pass. Rendered 360- and 650-pixel panels were
inspected and retained. The first UI attempt had an incorrect Surface import;
failed output remains retained and the product import/layout were corrected.
Installed inspector interaction, live LinuxCNC runtime, full configuration
closure and physical commissioning remain OPEN. This source is newer than
frozen DESKTOP218, whose single existing signing operation remains active.

## Complete channel paging checkpoint

Commissioning review now selects digital inputs/outputs, analog inputs/outputs
and recomputed sample changes. Sixteen rows render per page; every retained
channel remains reachable, including digital index 1023 and partial final pages.
Page bounds clamp when the sample has fewer channels, and changing the group
resets paging. Clear closes both joint/channel dropdowns and releases focus.
The previous duplicate truncated I/O/transition summaries were removed.

All 37 capture/status checks pass, including exact coverage of every digital
channel, analog values and final partial page, high-index transitions, widget
button dispatch and group/sample changes. Narrow/wide renders were inspected.
Strict typing, full Ruff/format and both architecture contracts pass. Installed
interaction and actual backend commissioning remain OPEN. Exact prior source
`cb14b91ab955491a6679f6a26602cbfece8ccf57` passes hosted quality hooks in run
37446361637; its full tests remain active at this checkpoint.

Owned completed DESKTOP153 records were relocated with all 2,900 file hashes and
3,397 manifest entries matching, strict signature passing, and a resolving link
at the original path. Its receipt is retained in the destination. The original
DESKTOP218 signing process remains live; a read-only process sample shows nested
MachO signing/allocation in resource preparation. It has not been restarted.

## Hosted reader verification receipt

Exact reader correction `cb14b91ab955491a6679f6a26602cbfece8ccf57`
passes hosted run 37446361637, job 112212049193: quality hooks and full
tests are green. The raw job log reports 2,651 passed, 15 skipped, one
warning in 774.00 seconds at 2026-10-06T10:10:01.6888187Z. This closes
the hosted source gate for that revision. Inspector/channel source is newer;
its runs 37447457507 and 37447923733 pass quality hooks and continue their
full tests. Installed interaction and actual LinuxCNC runtime remain OPEN.
The independent channel render receipt binds both inspected images to
`9ae619bb69641bb247b0be8d59681058ae58d5a8`.

## Historical joint motion traces

Commissioning captures now have selectable command/feedback, following-error
and velocity traces, with raw linear/angular joint units retained. The chart
uses recorded elapsed time rather than equal sample spacing. Each 200-sample
page retains every point; earlier/later controls reach every page, including
partial final pages. Selecting a plotted time chooses the nearest recorded
sample and refreshes joint/I/O details. Commanded position is teal, actual is
amber, and the selected sample has a ring on each series. Page range, elapsed
time and actual observed value range remain visible beneath the chart.

Missing joints or incompatible kind/units leave gaps. Lines also break at
joint-topology, Cartesian mask/units, generation or INI identity changes and
non-increasing observation times. Raw values are not normalized into inferred
physical dimensions, servo effort is not invented and imported historical
samples never change current machine state. Clear releases plot data and closes
the metric dropdown.

All 48 trace/capture/status checks pass, covering irregular timestamps, exact
sample/page coverage, angular/linear units, missing/incompatible observations,
time-based pointer selection and mounted UI paging/metric/clear interaction.
The first mounted-widget test attempted to open a dropdown on a hidden panel;
its failed output is retained and the test now mounts the panel before opening.
360/650-pixel panels were rendered and inspected. Strict changed-module typing,
full Ruff/format and both architecture contracts pass. Installed trace interaction,
actual LinuxCNC runtime, servo effort capture and physical commissioning remain
OPEN. Frozen DESKTOP218 remains the existing pre-inspector signing operation.
