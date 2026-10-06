# Further geometry, measurement and process workflows

The latest 25 recommendations extend the six existing acceptance ledgers under
the active implementation goal. Reused foundations do not close these workflows.
Source, installed interaction, backend execution and physical qualification remain
separate gates. This list does not authorize physical actuation.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Task-focused workbench lenses | Setup/machine/measure/diagnose arrangements use one shared state with contextual navigation |
| 2 | Selection disambiguator | Ranked overlapping-object selection, isolate and select-through with native interaction |
| 3 | Constraint-based setup | Typed geometric relationships, solving, conflict explanation and dependent updates |
| 4 | Batch editing | Tool/hole/offset/inspection tables support units, paste, multi-row validation and keyboard workflows |
| 5 | Applicable presets | Recipe applicability identifies actual assembly, process and machine assumptions and changed inputs |
| 6 | Comparison divider | Registered stock/nominal/measured/program comparisons with explicit source and resolution |
| 7 | Navigation trail | Setup/feature/operation/tool/source context links restore synchronized inspectors and views |
| 8 | Change-impact preview | Tool/setup changes identify dependent operations, checks, measurements and recipes before acceptance |
| 9 | Workstation interaction mode | Keyboard/pendant mapping and state feedback with motion-free configuration test mode |
| 10 | First-part rehearsal | Approach/engagement/tool-change/inspection stages expose expected state and required evidence |
| 11 | Fixture-placement solver | Actual hole grid, assets and tool access produce ranked placements with unknown clamping inputs |
| 12 | Material deviation map | Target CAD and residual geometry yield bounded above/below-target allowance visualization |
| 13 | Virtual inspection tools | Calipers/bores/sections/clearance measure simulation geometry with resolution and source classification |
| 14 | Measured datum construction | Feature-derived frame graph, residuals, alignment preview and supported offset transaction/readback |
| 15 | Bore shape inspection | Raw multi-direction contacts, fitted center and radial/diameter variation with sample coverage |
| 16 | Probe strategy optimization | Geometry/access/directional calibration inform explained approach and sampling proposals |
| 17 | Cutting/non-cutting assembly geometry | Flute/neck/shank/holder/extension reach and interference distinctions in simulation |
| 18 | Removal accounting | Removed volume, allowance, cutting/travel/tool-change time and predicted/observed run comparison |
| 19 | Cutting-force overlays | Explicit model inputs, vector/support association, uncertainty and measured validation |
| 20 | Axis demand inspector | Velocity/acceleration/reversals and available jerk/following error linked to path geometry |
| 21 | Five-axis orientation optimization | Candidate branch clearance/travel/speed/singularity tradeoffs and reviewed resulting path |
| 22 | Position-dependent thermal behavior | Position/runtime/temperature/reference evidence and validated bounded compensation |
| 23 | Compensation-stack debugger | Backend-specific intermediate work/rotation/geometry/wear/TCP poses and ownership |
| 24 | Reverse-path recovery | Actual capable backend, executed-path identity, process restrictions and qualified retrace |
| 25 | Milling-and-laser workflow | Shared measured part frame, marking/focus preview and supported process transitions |

All 25 remain OPEN. Backend mathematical models and capability declarations do
not establish Carvera support for advanced machine processes. The complete goal
retains the prior 150 requirements alongside these 25 extensions.


## Declared joint corner-demand checkpoint

The inverse-time joint study now retains signed velocity changes at each interior waypoint, including direction reversals and explicit stops/restarts. Unequal fraction intervals use their own declared block durations. Rotary coordinates remain unwrapped: a 350-to-10-degree transition remains minus 340 degrees. Numerically equal rates (relative 1e-9, absolute 1e-12) are omitted. Limits on input and output sizes and cancellation withhold partial reports.

The operation inspector shows the total changes and reversals, then pages through every retained corner with fraction, declared seconds, signed before/after rates, units and source provenance. Pages reset on source line or study replacement; paging neither seeks the toolpath nor sends controller commands. A discontinuity in piecewise-linear velocity requires an explicit blending/dynamics model; this calculation does not invent finite acceleration, endpoint rest, jerk or backend timing.

Validation: 39 inverse-time/corner/inspector checks pass, including nonuniform timing, unwrapped rotary travel, stops/restarts, cancellation, numerical overflow, bounded output, complete paging and replaced-study identity. The final paging checks and rendered panel were also inspected (`/private/tmp/carvera-joint-corners-render-20261006.log`). Receipt: `/private/tmp/carvera-joint-corners-accepted-20261006.log`. Strict machine typing, focused UI typing, Ruff across 572 files and both architecture contracts pass. This advances the axis-demand inspector (geometry/process requirement 20) and dynamics model (process/backend requirement 17). Acceleration/jerk modeling, observed motion feedback, installed/native acceptance and physical qualification remain OPEN. The source postdates frozen DESKTOP236; its original packaging process remains active at this checkpoint.

## DESKTOP236 installed inspection and ATC regression checkpoint

DESKTOP236 is now built, independently verified and installed from frozen `773945ff655f70a9f846572f40713a93bcc6a93a`: 527 packaged files match, zero mismatches, strict signature verified. DESKTOP235 remains the recovery app. Native gestures verified 25 mm exploded inspection, visible reassembly, and return to the Live Program workspace with Idle, zero spindle/feed, no selected program, fresh camera and telemetry. All nine operator JSON paths remain unchanged. Receipt: `/Users/wes/.codex/artifacts/carvera-desktop236-20261006/desktop236-native-inspection-receipt.json`. Native feature-plane and saved-layout workflows remain OPEN; newer palette routes and joint-corner review are source-only.

Hosted run 37534781305 at `2d933f9` completed with two failed ATC overlay tests, 2939 passed and 17 skipped. Both legacy fake viewers lacked the display-movement method introduced for exploded inspection. Fixtures now bind the real viewer movement methods, and additionally verify that ATC markers follow exploded displacement in Preview and return to assembled coordinates in Live. All three overlay checks pass (`/private/tmp/carvera-slot-overlay-accepted-20261006.log`). Hosted acceptance of the repaired final revision remains OPEN until its own run completes. No backend actuation or physical qualification is claimed.
