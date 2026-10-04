# Workbench tab responsiveness

Workbench selection history uses a compact setup identity for loaded immutable CAD profiles. The CAD loader computes a SHA-256 fingerprint once alongside its canonical geometry serialization in the background load. Tab clicks capture that fingerprint plus the current scene setup, cutter definitions, toolset, and preview overrides. Replacing geometry or changing setup still invalidates old navigation entries; mutable adapters are serialized freshly.

Saved simulation bookmarks retain their existing canonical geometry identity and compatibility. History is local and ephemeral, so its new compact identity does not migrate saved records. No controller commands are involved.

The accompanying regression rejects any access to the loaded geometry string on tab selection, exercises setup invalidation and back/forward navigation, and switches all eight tabs repeatedly with registered CAD. The benchmark distinguishes synchronous callback time from two event-loop frames; neither is a machine-control latency measurement.

The same release includes separate state and writer locks for profile snapshots: slow local disk saves must not block the UI's reads of the last committed profile state.

Native package acceptance and measured timings are recorded separately from source tests.

## DESKTOP129 acceptance

Application source: `40a3f5580e99bcd97fb360b16bc83c0b9c23fb9d`, branch `feat/simulator-and-spindle-load`. The installed window identified itself as `Carvera Controller Community v2.1.0-DESKTOP129`. All eight tabs were exercised in two native cycles with the registered Saunders/Mod Vise model, camera and controller telemetry open; screenshots were retained and the first cycle's individual page results visually reviewed. Native click-to-paint latency was not instrumented.

The source benchmark captured 24 switches with 25,320,679 bytes of registered geometry metadata. With the previous navigation capture, callback median/max were 33.71/44.81 ms; with compact geometry fingerprints, 0.63/12.52 ms. Two-frame median/max were 73.48/103.80 ms before and 52.88/86.07 ms after. These are event-loop test observations, not hardware control latency. The focused suite passed 28 tests; both architecture contracts passed.

Receipts and screenshots: `/Users/wes/Downloads/carvera-desktop129-20261004/`. The build's initial preflight failure is retained: the internal volume had less than the 1 GiB required reserve, so temporary packaging files were placed on the external build volume. Dependency reads subsequently stalled and resumed; low free storage has not been proven to be the cause of the reported tab pause.

This closes the bounded tab-navigation source/native workflow checkpoint. The full controller roadmap remains open, as does a separate native cutter-table divider-drag acceptance gap documented in `docs/cutter-table.md`.
