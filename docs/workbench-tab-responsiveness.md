# Workbench tab responsiveness

Workbench selection history uses a compact setup identity for loaded immutable CAD profiles. The CAD loader computes a SHA-256 fingerprint once alongside its canonical geometry serialization in the background load. Tab clicks capture that fingerprint plus the current scene setup, cutter definitions, toolset, and preview overrides. Replacing geometry or changing setup still invalidates old navigation entries; mutable adapters are serialized freshly.

Saved simulation bookmarks retain their existing canonical geometry identity and compatibility. History is local and ephemeral, so its new compact identity does not migrate saved records. No controller commands are involved.

The accompanying regression rejects any access to the loaded geometry string on tab selection, exercises setup invalidation and back/forward navigation, and switches all eight tabs repeatedly with registered CAD. The benchmark distinguishes synchronous callback time from two event-loop frames; neither is a machine-control latency measurement.

The same release includes separate state and writer locks for profile snapshots: slow local disk saves must not block the UI's reads of the last committed profile state.

Native package acceptance and measured timings are recorded separately from source tests.
