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
