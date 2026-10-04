# Further controller usability and machine qualification requirements

These 25 requirements supplement the four existing ledgers. They remain under
Wes's active implementation goal. Foundations, source tests, native interaction,
backend transport and physical qualification are separate gates.

| # | Requirement | Required acceptance evidence |
|---|---|---|
| 1 | Discrepancy inbox | Program/profile/reported tool, fixture and offset conflicts; explicit resolution and readback |
| 2 | Linked precision views | Full machine plus selected cutter/feature close-up with synchronized selection |
| 3 | Semantic zoom | Scale-dependent operations, path, dimensions and clearance information |
| 4 | Simulation bookmarks | Revision-bound line/tool/scene bookmarks, persistence and seek |
| 5 | Shop interaction mode | Large controls, contrast, selected-axis feedback and native touch/desktop review |
| 6 | Visual pendant configuration | Device mappings, increments, connection and isolated test mode |
| 7 | Previewed jog destinations | Explicit frame, endpoint/vector, known travel and qualified obstacle information |
| 8 | Machining notebook | Operation/tool/feature-linked notes, photos and measured results with custody |
| 9 | Controlled process experiments | Labeled coupon variants and corresponding inspected outcomes |
| 10 | Exception-first run display | Normal operation summary and actionable telemetry/intervention changes |
| 11 | Machine qualification dashboard | Reference/homing/TLO/probe/rotary results, applicability and repeatability |
| 12 | Physical cutter identities | Catalog versus individual cutter identity, measurements and installed reconciliation |
| 13 | Tool seating diagnostics | Raw repeat measurements and reseating comparisons without invented damage diagnosis |
| 14 | Fixture-hole addressing | Stable Saunders row/column addresses, scene highlighting and qualified camera registration |
| 15 | Generated setup instructions | Fixture/jaw/stock/tool/location/photograph sheet matching exact setup revision |
| 16 | Stock lineage | Blank, prior machining, residual material, inspection and next orientation |
| 17 | Machine selection assistance | Job requirements versus actual backend travel/process/tool/workholding evidence |
| 18 | Usage-based maintenance | Observed usage, sensor readings, scheduled work and completion records |
| 19 | Joint-level diagnostics | Backend joint command/feedback/following error/limits/homing versus Cartesian pose |
| 20 | Animated homing/gantry squaring | Actual backend sequence, switch expectations and independent joint states |
| 21 | Geometric error-map workbench | Measured positioning/backlash/squareness/pivot inputs and bounded supported compensation |
| 22 | Spindle orientation state | Supported commanded/observed angle, completion and timeout |
| 23 | Servo/process signal recording | Time-bound backend signals and event-triggered diagnostic capture |
| 24 | Instrumented coolant/lubrication | Commands versus observed flow/pressure/level and operation requirements |
| 25 | Synchronized chatter investigation | Sensor custody, operation/location/process association, comparisons and qualified intervention |

This ledger does not authorize hardware actuation or claim support for advanced
machine processes in the existing Carvera adapter.
