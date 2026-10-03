# Desktop profile library

The library separates named machine preferences, cutter geometry, and planned
six-slot ATC sets. These are local profiles, not measured offsets or a record of
which cutter is physically loaded.

- **Machines:** name, C1 or CA1 model, address, port, camera snapshot URL, and
  optional converted machine CAD profile path. Using one supplies workspace
  preferences; the user still connects through the connection control.
- **Cutters:** name, program tool number, supported tool shape, cutting/shank
  diameters, overall/flute lengths, corner radius, thread pitch, manufacturer,
  part number, and notes. All library dimensions are millimeters. A blank optional
  dimension means unknown. Overall cutter length is not measured spindle stickout
  or tool length offset.
- **ATC toolsets:** a name plus up to six slot-to-cutter references. Slots are
  numbered 1 through 6; the same cutter profile cannot occupy two slots in a set.
  A second physical cutter can have its own separately named profile. Loading a
  set produces preview `ToolDefinition` objects numbered by slot; no tool change,
  offset write, spindle command, or other CNC command is sent.

The initial cutter inventory contains only the three photographed quarter-inch
end mills. It assigns no ATC toolset and assumes no machine address. The workspace
may save its existing connection settings as the first named machine.

Profiles live at `~/.carvera/profiles.json`, schema 1. Save validates the complete
library, writes a temporary file in the destination directory, flushes it to disk,
and replaces the destination atomically. Failed saves leave the prior in-memory
and on-disk library intact. Invalid existing files are preserved and reported,
not silently replaced with defaults.

Import merges a complete schema-1 JSON library by stable record ID. An imported
record with an existing ID updates that record. New IDs create new records.
Toolsets must refer to tools included in that library. Validation completes before
any write. Export writes the entire local library. Files are limited to 2 MiB;
each category is limited to 1,000 records. Embedded camera URL credentials and
nonfinite, invalid, or out-of-range dimensions are rejected.

## Integration

`ProfileLibrary(workspace, store=None)` is a Kivy widget suitable for a focused
modal. It contains searchable categories, a scrollable editor, save/delete,
import/export, and an explicit apply action.

The workspace provides these read-only/local hooks:

```python
apply_machine_profile(profile_dict)
apply_tool_profile(profile_dict, slot=None)
apply_toolset_profile(toolset_dict, definitions_in_mm)
choose_profile_file(callback, save=False)  # optional native/modern JSON picker
```

`ProfileStore` exposes detached `.data` readbacks, `save_machine`, `save_tool`,
`save_toolset`, `delete`, `import_file`, `export_file`, and
`toolset_definitions(toolset, units="mm")`. `to_tool_definition(profile,
number=None, units="mm")` converts profile dimensions into a viewer's G-code
units without changing the saved record. Default toolset apply passes millimeter
objects; the workspace owns conversion to the active preview's units.

The library adapts to available width. On desktop widths the saved-profile list
is capped at 280 dp and related fields share two-column sections. Below 760 dp
the list moves above the editor; individual sections collapse to one column
when there is insufficient room. Category and file-action buttons wrap rather
than clipping, while save/use/delete actions remain outside the form scroll.
Resizing retains current unsaved field values. The selected category and saved
profile have visible active states.
