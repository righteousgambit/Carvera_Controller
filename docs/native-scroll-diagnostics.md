# Native wheel delivery diagnostics

Run `scripts/diagnose_desktop_scroll.py` with the controller's Python environment,
optionally passing `--output <directory>`. It creates a separate Kivy home before
importing UI modules and never imports the controller main application or a
hardware transport. Its synthetic program picker has no machine callbacks;
preview and upload actions are disabled. The diagnostic does not replace the
installed controller or modify its configuration or profiles.

The bounded trace records window button events, provider motion events,
viewport handling, normalized scroll position, window density and picker bounds.
It does not record keyboard input, operator programs or machine state. The
trace is rewritten atomically every quarter second and flushed on close.
Evidence directories remain available after exit. `Mark attempt`, reset,
wheel gestures and scrollbar dragging allow independently attributable trials.

## October 4 native observation

Evidence directory:
`/Users/wes/Downloads/carvera-native-scroll-trace-20261004`.
Native component trace: `native-component-trace.json`; actual picker trace:
`native-picker-trace.json`. Screenshots accompany the trace. The initial CLI
failure is retained separately. Both diagnostic bundles passed strict deep
signature verification after their builds completed.

The native component received both wheel directions and moved from 0.5 to
0.46865203761755486 and back to 0.5. Ordinary pointer movement targeted distinct
locations, but wheel events repeatedly arrived at window coordinates (773,443).
With density 2, the provider mapped these to approximately (1546.645,672.431).

In the isolated production picker, the detail viewport began at X=1598.345.
The wheel event was outside it: the viewport correctly returned false and
retained scroll_y=1.0. This identifies an event-location discrepancy before
viewport routing. It does not establish whether the cause is automated input,
SDL handling, or physical pointer behavior. It also does not qualify physical
mouse/trackpad scrolling in the installed operator application.

Do not route out-of-bounds wheel events into a pane to conceal this discrepancy.
Physical input confirmation or an input mechanism that delivers the intended
coordinates is required for the installed-app acceptance gate. The isolated
component result and source provider tests remain narrower evidence.
