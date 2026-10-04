# Further connected controller requirements

These 25 recommendations extend the five existing ledgers under the active goal.
Overlapping foundations are reused; this list does not replace previous scope.
A listed foundation does not close the complete native or machine workflow.

| # | Requirement | Required completion evidence |
|---|---|---|
| 1 | Selection history | Back/Forward restores object, inspector and framing across operations, tooling, fixtures and measurements |
| 2 | Selection-driven object workbench | Selected object exposes its relevant relationships, editable properties and measured/declared state |
| 3 | Linked parameter expressions | Typed references, dependency validation, visible evaluation and affected-plan recalculation review |
| 4 | Preview before apply | Proposed geometry/offset/tool edits shown before persistence or supported machine mutation and readback |
| 5 | Asset repair/relink | Missing/changed/unit-mismatched asset comparison, affected jobs and portable dependency repair |
| 6 | Desktop accessibility | Keyboard operation, focus, scaling, readable unavailable-state prerequisites and native review |
| 7 | Multi-monitor views | Detachable camera/model/control views with synchronized state and one command owner |
| 8 | Adaptive rendering detail | Scale-dependent details and bounded CAD/render workloads with responsive controls |
| 9 | Scene dimensional inspector | Face/axis/hole/tool/stock dimensions with explicit frame and source classification |
| 10 | First-contact collision explanation | Objects, source line, approach and clearance with broad/narrow phase distinction |
| 11 | Simulation accuracy budget | Resolution/subdivision/unknown geometry shown and feature-resolution checks |
| 12 | Controller-aware dry run | Backend dynamics, rotary limits, spindle transitions, tool changes and validated timing |
| 13 | Interpreter debugger | Dialect-specific parameters/subprograms/cycles/modal changes and resulting path/source trace |
| 14 | Lookahead/queue display | Received/queued/executed identities, starvation and communication gaps from actual backend |
| 15 | Distinct rapid/feed controls | Supported override scope, latency/readback and reviewed first-run policy |
| 16 | Adaptive commissioning bench | Unloaded baseline, telemetry age/filter/response model and qualified bounded actuation |
| 17 | Operation/region adaptive policies | Rough/finish/entry/thin-wall/thread policies with bounds and linked reasons |
| 18 | Process transition checkpoints | Required observed state, backend-supported completion and timeout before next operation |
| 19 | Physical ATC reconciliation | Slot model, expected/read-back/confirmed tools, bank changes and actual calibration workflow |
| 20 | Tool assembly consequences | Holder/stickout/extension reach/interference and bounded deflection model assumptions |
| 21 | TCP/frame audit | Work frames/pivots/tool tip, compensation ownership and supported-backend consistency |
| 22 | Rotary continuity inspector | Solution branches, limits/unwinds/singular regions and reviewed path configuration |
| 23 | Spindle synchronization workspace | Encoder phase/feed-per-revolution/reversal/fault states from capable backend |
| 24 | Mill-turn part ownership | Chuck/station/frame/clamp/transfer identity with continuous stock and inspection history |
| 25 | Inspect/correct/finish | Measured feature/tolerance, bounded correction, preview, supported execution and reinspection |

All requirements remain open unless their full acceptance evidence is recorded.
The current Carvera adapter does not provide a LinuxCNC execution transport or
qualify advanced spindle synchronization, TCP or mill-turn hardware.

## Program history source checkpoint

Requirement 1 has Program-local history shared by operation selection, inspected
source, search results and bookmarks, including departure framing and setup
revision checks. See `selection-history.md`. Scene/tool/fixture/measurement
selection history across workbench sections remains open.

The additional geometry, measurement and process recommendations are retained in
`controller-geometry-and-process-workflows.md`. They extend the goal without
replacing this ledger or its outstanding acceptance gates.
