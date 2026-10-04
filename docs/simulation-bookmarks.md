# Simulation bookmarks

In Program, inspect a source line and frame the machine view. Expand Bookmarks,
enter a name, and Save point. Selecting the saved row revisits that source line
and restores orbit, pan, zoom, look-at and projection. It only changes preview.
Bookmarks persist across app launches in `~/.carvera/simulation-bookmarks.json`.
Delete removes a bookmark from the local library.

Each point records the selected saved machine profile, parsed-program SHA,
one-based source line and text, parsed active tool, and setup identity. The setup
identity includes stock and workholding geometry, component choices and
visibility, loaded CAD triangles, tool definitions, loaded toolset, program tool
geometry, and preview tool override. It hashes the loaded geometry rather than
relying on an asset filename. A changed program, machine profile, or setup
refuses the jump and explains the mismatch. Restore the matching revision to
revisit an older point. It does not automatically replace stock, fixtures or
tool definitions to make an old bookmark compatible.

Bookmarks do not prove executed-line state, physical tool identity, measured
setup registration, or machine pose. Program hashes identify parsed UTF-8 text.
Storage validates revisions, identities and bounded finite view parameters;
atomic replacement preserves prior data on write failure. Invalid libraries
are left untouched, and detected external edits refuse a stale write.

The workbench, operation/result lists, and profile library now use content and
bar scrolling together, with wider visible drag targets. Source event tests
exercise wheel scrolling and captured scrollbar dragging. Installed native
acceptance is tracked separately from these tests.
