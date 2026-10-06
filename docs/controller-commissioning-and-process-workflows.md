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

## Named HAL capture and historical review

The optional read-only `LinuxCNCHalReader` opens the actual local HAL module and
calls only `get_info_pins()` / `get_info_signals()`. It retains backend names,
types, pin directions, signal driving-pin names and observed values. It creates
no component or writer. Invalid types/ranges/directions, duplicates, nonfinite
values and oversized groups reject the poll, clear the old observation and break
bit-transition continuity. Metadata/driver changes also break continuity.
No component graph, physical sensor units, servo effort or safety permissive is
inferred from a signal's name or value.

On a LinuxCNC host, `python -m scripts.capture_linuxcnc_status --machine-id NAME
--output NEW.jsonl --hal` adds HAL observations to the NML recording. HAL and NML
are separate sequential samples, not an atomic machine snapshot. Exclusive file
creation remains; a 20 MiB writer bound reserves space for a terminal failure and
keeps earlier samples. The importer validates HAL/NML machine, sequence,
configuration coverage and observation timing; imported HAL transition assertions
are ignored and recomputed. Legacy recordings remain importable.

Historical channel review now includes paged HAL pins/signals with reported type,
pin direction or signal driver. Legacy files explicitly say HAL was not captured,
not that the machine has no pins. Both 360/650-pixel panels were rendered and
inspected. All 66 HAL/status/capture/trace checks pass, with 18 final HAL checks
including mounted named-driver review and legacy absence messaging. Strict changed
machine-module typing, full Ruff/format and architecture contracts pass. Actual
LinuxCNC HAL runtime, installed review, full component/net association and physical
commissioning remain OPEN.

Exact historical-inspector source `c32544ccd0eb4160b5b0ecf40eea00f8405fc2ef`
passes hosted run 37447457507, job 112215611790: 2,666 passed, 15 skipped, one
warning in 835.85 seconds at 2026-10-06T10:20:40.1502433Z. The full raw job log
is retained. This receipt proves that earlier source; named HAL work is newer.

## Searchable HAL driver review

The historical HAL browser now filters reported names, types, pin directions and
signal driving-pin names with case-insensitive, all-word search. Only sixteen
matching rows and selection choices render at once. All 4,096 entries in a
bounded group remain reachable; no names or observed values are synthesized.
The selected item shows its value/type/direction and, for a signal, the exact
reported driver pin's captured type/direction/value. Missing drivers and type
mismatches remain explicit. Differing pin/signal values are retained with the
separate-read timing caveat. This is a historical association, not a full net
or physical component graph.

Search updates are coalesced over 120 ms, reset paging and enforce a visible
256-character bound. No-match, invalid query and legacy absence remain distinct.
HAL controls detach and release field/dropdown focus when another channel group
is selected; Clear resets search and cancels its scheduled redraw. Page/filter
changes close a stale item dropdown. The query and selection never change the
connected machine, saved setup or capability evidence.

All 68 HAL/status/capture/trace checks pass, followed by 20 final HAL checks
including mounted invalid-query recovery. Full 4,096-entry coverage, exact
reported-driver lookup, missing/mismatched metadata, filtering and focus release
are checked. Narrow/wide source renders were inspected. Strict changed-module
typing, full Ruff/format and both architecture contracts pass. Initial test
collection failed after a misplaced finally block in the test edit; the failed
output is retained and the test was corrected. Installed interaction, actual
HAL runtime and full component/net/physical association remain OPEN.

Exact channel-paging source `9ae619bb69641bb247b0be8d59681058ae58d5a8`
passes hosted run 37447923733, job 112217133809: 2,668 passed, 15 skipped, one
warning in 904.07 seconds at 2026-10-06T10:25:52.9790664Z. The raw log remains
retained. Named HAL source run 37449672996 passes quality hooks and continues
its full suite at this checkpoint. The original DESKTOP218 signing handle remains
live and has not been restarted; source work remains newer than that package.

## Scratch packaging and exact archive publication

Read-only diagnosis of the original frozen DESKTOP218 signing worker confirms
it remains alive and has progressed from lxml signing to later resource reads.
At 2026-10-06T10:32:34Z, sampling places its main thread in ResourceBuilder
resource scanning/read. The build volume is Secure Digital; kernel records show
multi-second APFS transaction flushes and repeated 15-second directory-iteration
delays on disk7/disk7s2. Free space is about 745 GB; the captured VM snapshot has
no swap-ins/outs. These establish slow storage activity, not a terminal signing
failure. No restart, disk reset or installed-controller replacement was issued.
The evidence logs and original operation handle remain retained.

Future builds may use `--scratch-root FRESH_FAST_PATH --output FRESH_ARCHIVE_PATH`
in `scripts/build_adaptive_macos.py`. Staging, packaging, signing, Kivy build
configuration and subprocess TMPDIR remain on the selected scratch workspace.
Scratch/archive paths must be fresh and non-nested; both storage locations are
preflighted. After signing, source, dist and source-manifest are copied with
symbolic links preserved. File bytes, directories, modes and link targets match
before publication, then the archived bundle receives strict signature verification.
A receipt binds the deliverable tree; scratch is retained. A failed archive stays
with a failure receipt and cannot overwrite a previous artifact. The builder
never installs or connects a controller.

All 27 build/installer checks pass, including CLI routing and temporary-file
isolation, source signature rejection, corrupted-copy retention and an actual
macOS ad-hoc signature copy/verification using a small fixture bundle. Full
Ruff/format checks pass. The first corruption test intercepted recursive copytree
calls with an incompatible test signature; failed output remains and the fixture
was corrected. This proves the archive primitive and source routing, not a full
controller build on scratch storage. Source-to-package verification, full-build
execution and installed/native qualification remain independent OPEN gates.
Frozen DESKTOP218 is still the original older build; this change affects future
builds only.

Exact receipt-only source `414e01c652204e92757e2f57dbb13e18a599a1b6`
passes hosted run 37448367017, job 112218580548: 2,668 passed, 15 skipped, one
warning in 977.75 seconds at 2026-10-06T10:31:11.2847315Z. Raw log retained.

## Installed DESKTOP218 vise comparison checkpoint

The original DESKTOP218 build completed once without restart. Frozen source
`1815f97856d6e1a8303ee82f0f20393058bdaee3`, version 2.1.0-DESKTOP218,
was independently verified at 2026-10-06T10:40:26.527807Z: 504 packaged files,
zero source/package mismatches and passing strict signature verification.
Installation completed at 2026-10-06T10:48:49.510161Z with the same verified
files and signature; DESKTOP217 remains a recovery app. These receipts live in
`/Volumes/Wes Storage/CarveraBuilds/carvera-desktop218-20261006/`.

Native CUA readback confirms saved-profile direct connection to C1, Idle, fresh
reported pose and camera imagery. Unsaved vise X -77.9376 to -77.8376 mm,
rotation 90 to 91 degrees and movable-jaw shift -74.5953 to -74.4953 mm
show +0.1 mm / +1 degree / +0.1 mm comparisons. XY/XZ diagrams show solid
draft and dashed previous envelopes; the jaw view retains an amber zero-shift
reference. Cancel/reopen restores all original values with Apply disabled.
All ten tracked operator JSON paths retain their exact pre-install hash/null
values; the archived native receipt and after-store receipt confirm readback.
The final modal is dismissed and Live reports telemetry age 0.16 s and camera
age 0.3 s. No Apply or actuation was issued. This bounded installed interaction
is CLOSED; measured mounting, physical clearance and full workflows remain OPEN.
The newer commissioning capture, traces, HAL and search UI are not in this build.

Completed owned build records 154, 155 and 157 were relocated with respectively
2,895 / 2,898 / 2,898 file hashes and 3,392 / 3,395 / 3,395 manifest members
matching; strict signatures pass and old paths remain resolving links. Existing
record 156 was already relocated and was not repeated. Installation preflight
passed without reducing the 1 GiB reserve. Slow SD-volume evidence remains
retained; future full controller scratch packaging remains OPEN.

Hosted full-suite receipts, with raw job logs retained:

| Exact source | Run / job | Result |
|---|---|---|
| `05647225f840d4dbab578578f521f62bf84b20f0` | 37448805899 / 112220020598 | 2,679 passed, 15 skipped, 1 warning; 793.52 s |
| `d79e948f874825c0a08d9448930bc4d7602ebbf4` | 37449672996 / 112222911733 | 2,697 passed, 15 skipped, 1 warning; 674.19 s |
| `63e00ff1172c8808d8e36a609013c20ef34f3514` | 37450258392 / 112224825623 | 2,699 passed, 15 skipped, 1 warning; 794.61 s |
| `7c901d18bbc950312004058822a277eb672d4ebc` | 37451159326 / 112227785447 | 2,704 passed, 16 skipped, 1 warning; 785.29 s |

The last hosted summary is timestamped 2026-10-06T10:53:03.9743523Z.
All 350 requirements remain in scope; these receipts do not close the full
implementation objective or actual LinuxCNC/backend/physical qualification.

## Historical HAL parameter review

The optional HAL reader now also calls the documented read-only
`get_info_params()` API when available. It records each reported parameter name,
type, value and ro/rw metadata, with the same 4,096-item/name/numeric bounds used
for pins. No parameter writer, component creation or tuning command is added.
Missing API/legacy recording retains parameters=None; an observed empty list
retains an empty tuple. Parameter metadata/coverage changes break continuity.
A failed parameter read invalidates the observation and retains the capture's
failure behavior. Independent HAL group reads remain non-atomic.

The historical Machine workbench now has HAL parameters in its channel selector.
All-word search includes names, types and ro/rw metadata; pages and choices stay
bounded at 16 entries. Details retain exact raw values and explain that rw is
reported metadata, not permission to edit. Legacy unavailable coverage, observed
empty groups and no search matches remain distinct. Old capture imports still
work; new capture roundtrips retain parameters and reject forged access metadata.

All 76 HAL/status/capture/trace regression checks pass, followed by 29 final HAL
checks with the end-to-end capture/import case. Tests cover every one of 4,096
parameters, exact values/access, missing coverage, reader invalidation and mounted
360/650-pixel panels. Strict changed-module typing, full Ruff/format and both
architecture contracts pass. Initial legacy-test decoding omitted its JSON
transport conversion and an added test referenced a nonexistent parser helper;
failed logs are retained and both test errors were corrected. Narrow/wide source
renders are retained. Actual LinuxCNC parameter readback, installed/native review,
full tuning/experiment workflows and physical commissioning remain OPEN.
API reference: https://linuxcnc.org/docs/stable/html/config/python-hal-interface.html

## Pinned historical HAL reference comparison

The imported commissioning review can pin its selected sample as a reference
and switch HAL pins/signals/parameters between recorded values and changed items.
The reference sample number and UTC time stay visible while navigating; import
resets it to the first sample and Clear releases it. No capture or operator setup
is modified. Search and 16-entry pages apply to the changed-item list, retaining
all names across 4,096-entry groups.

Pure typed comparison identifies added, removed, value-changed and metadata-changed
items. Details retain both raw values, type, direction and driver. Numeric deltas
are limited to unchanged typed metadata, with overflow explicitly reported and no
physical units inferred. Missing group coverage and differing machine/reader
generation produce unavailable comparison, never invented additions/removals.
These independently sampled historical differences do not establish tuning
acceptance, current configuration or an atomic machine snapshot.

All 65 focused HAL/capture/trace/comparison checks pass, including mounted
360/650-pixel navigation, reverse comparisons, reference changes, invalid-search
recovery, shorter re-import and Clear. Strict typing, full Ruff/format and both
architecture contracts pass. Source renders were inspected; their unsupported
arrow glyph was replaced with plain text. Installed comparison, actual LinuxCNC
readback, saved before/after experiment receipts and physical commissioning
remain OPEN. The full 350-requirement program remains active.

## Frozen-archive package verifier and DESKTOP219 preparation

`scripts/verify_macos_build.py` independently reads controller source bytes from
the frozen Git tar archive, rather than trusting the mutable checkout or builder
manifest. The caller supplies exact revision and archive SHA256; both must agree
with the build request and actual archive bytes. The verifier rejects unsafe,
duplicate and nonregular controller members, regenerates gettext catalogs and
applies only the requested version override. Exact manifest membership/hashes,
packaged source, bundle identity/version and strict signature must pass before an
exclusive built-verification receipt is written. It never installs or launches.
This proves packaged source/signature, not embedded runtime or native workflows.

All 35 build/archive/installer/verifier checks pass; eight final verifier checks
include a real ad-hoc signed macOS fixture bundle with independently compiled
gettext. Full Ruff/format passes. The fixture is not the full controller package.

DESKTOP219 is frozen from `ad93f8acb825ff5c816fdec3fa96b57345bcb143`; source
archive SHA256 `e6bd6370bfc0fa5ec56e518d0e1525c0a063e9c4016b24f8ba94bdc5e21d07a6`.
The prepared request uses internal scratch and the retained CarveraBuilds archive.
One runner waits for 3.5 GiB scratch capacity before launching packaging once;
it times out without packaging after one hour if the reserve is unavailable.
It refuses an existing scratch/archive artifact. The original relocation handle
continues completed-record verification/copy before switching each old path.
DESKTOP158 relocation is CLOSED: 2,900 files / 3,397 members, zero mismatches,
strict signature passing, at 2026-10-06T11:10:48.868451Z. The old path resolves
to its retained archive. Later requested relocations and actual scratch packaging
remain WAITING/LIVE, with original handles and receipts retained. DESKTOP218
and all installed recovery apps remain untouched.

This verifier source follows the frozen DESKTOP219 application source. Full
controller build, independent package verification, installation, native
commissioning review and actual backend/physical gates remain OPEN.
