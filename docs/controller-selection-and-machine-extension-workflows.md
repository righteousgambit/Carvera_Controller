# Selection and machine-extension workflows

These 25 requirements extend the active implementation objective. Earlier
workflow ledgers remain applicable. A source model or an inspector link alone
does not close an end-to-end requirement. All items remain OPEN.

| # | Requirement | Acceptance evidence still required |
|---|---|---|
| 1 | Selection-driven workbench | Scene picks route tool, stock, fixture and feature selections to linked geometry, settings, measurements and actions; native navigation preserves selection. |
| 2 | Direct manipulation with precise numeric editing | Constrained scene handles and unit-aware fields agree; snapping, undo and saved setup round trips are exercised. |
| 3 | Semantic zoom | Machine, workholding and feature scales reveal appropriate information without losing selected objects or view context. |
| 4 | Machining command palette | Searchable contextual actions, keyboard use and capability/state gating are exercised in the native app. |
| 5 | Operation-aware program browser | File previews show operations, tools, units, setup dependencies and unresolved interpretation before selection. |
| 6 | Visual setup comparison | Current versus saved geometry, origin, tooling and program differences identify affected derived checks and frame changed objects. |
| 7 | Persistent machining timeline | Operation, telemetry, override, probe and camera events retain timestamps and provenance; unknown executed-line association remains explicit. |
| 8 | Task-focused workspace presets | Setup, Inspect, Run, Diagnose and Review preserve camera/machine views and user layouts across relaunch. |
| 9 | Actionable problem navigator | Issues group by operation/tool/feature/setup and route to framed geometry plus applicable remedies. |
| 10 | Repeat-job preparation | Package restoration distinguishes saved declarations from today's measured/verified setup and completes an operator review. |
| 11 | Remaining-stock-driven planning | Residual stock carries between operations and transformed setups; inaccessible regions and candidate cutters are inspectable; generated paths are validated. |
| 12 | Surface-quality and gouge analysis | Target comparison and scallop estimates retain model resolution/assumptions and link deviations to producing moves. |
| 13 | Tool-assembly clearance optimization | Candidate holder/stickout choices show access and interference with complete, registered geometry; physical assembly changes remain explicit. |
| 14 | Magazine management | Pocket restrictions, adjacent exclusions, sister tools and bank swaps match backend rules and declared physical inventory. |
| 15 | Reusable probing workflows | Scene approaches, bounded travel, expected results and failure handling execute through supported probe backends with retained results. |
| 16 | Feature-linked inspection/correction | Measurements bind to features/tolerances and proposed bounded corrections show affected operations; backend writes receive readback. |
| 17 | Cutting-process experiments | Trials retain material, assembly, parameters and measured outcomes and support comparable, reusable process records. |
| 18 | Engagement-aware feed supervision | Predicted engagement and available telemetry produce explainable suggestions; bounded automatic control requires measured latency and qualified response. |
| 19 | Tool life and sister tools | Usage and inspection bind to physical assembly identity; replacement occurs at supported, verified operation boundaries. |
| 20 | Acceleration-aware cycle analysis | Declared dynamics, short segments, cornering, inverse-time blocks and tool changes contribute to estimates validated against observed runs. |
| 21 | Rotary setup/unwind planning | Equivalent joint solutions, limits and access are visible; generated unwind sequences retain registered clearance checks. |
| 22 | Five-axis orientation exploration | Alternative poses, joint margins and difficult configurations are inspectable; singularity handling and execution require a qualified TCP backend. |
| 23 | Controller-aware compensation | Work offsets, length/radius compensation, rotation and TCP effects are explained for a selected move using the actual supported dialect. |
| 24 | Tapping/threading/turning workflows | Thread milling, rigid tapping, synchronized threading and turning remain separate workflows with backend/hardware prerequisites and execution evidence. |
| 25 | Coordinated production | Pallets, fixtures, auxiliary equipment and multiple channels/spindles have explicit ownership, waits/interlocks and supported orchestration. |

## Current source contribution

The selected-move inspector links its parsed tool number to the existing
library/CAM/calibration comparison and refreshes that context when definitions
or reported pose freshness change. It preserves unavailable geometry and
physical-identity limitations. This advances item 1 but does not establish scene
picking, feature selection or the complete selection-driven workbench.

Planning and interface changes do not authorize machine motion, configuration
writes or automatic adaptive control. Source, installed interaction, backend
execution and appropriate physical acceptance remain separate gates.
