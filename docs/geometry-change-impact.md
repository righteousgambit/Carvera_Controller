# Geometry change impact and residual-stock identity

The Program workbench's **Material removal & clearance** section now includes
**Review change impact**. It compares the current program, stock, preview work
offset, vise placement, selected component CAD, program-used tool geometry and
physical assembly revision with the inputs of the residual result.

When residual stock and a captured clearance study coexist, the review defaults
to residual stock rather than silently selecting an older clearance capture.
The result selector switches between both exact input histories. **Review
clearance inputs** opens the clearance history directly, including when there
is no residual result. Missing baselines remain explicit; reviewing or switching
never replaces either result or sends machine commands.

The review shows previous/current values, both complete context hashes and links
to affected operations. Tool changes identify operations using that tool;
program, stock, frame and workholding changes conservatively identify all
operations. These are dependency consequences, not computed collision regions.
Spatial clearance consequences, prospective edits, measurement/recipe
invalidation and a complete change-impact workflow remain open.

Setup/tool-definition changes automatically hide the older residual visualization
without deleting its stock/history. CAD byte checks happen on explicit calculation,
review, save, load and job-export actions, not in the telemetry refresh loop.
Replacing a CAD file at the same path, even with the same size and modification
time, changes its byte identity. The review explains when a selected asset needs
reloading; it never silently substitutes new geometry into an existing result.

Loaded tool definitions retain the SHA-256 of the converted cutter/holder bytes.
Mesh parsing verifies that exact identity against the bytes it consumes, so a file
change between fingerprinting and mesh construction rejects the load before
publishing the new library. Machine CAD retains a digest of the compressed bytes
used to parse it. This converted-asset identity is separate from the manufacturer's
source CAD hash. It does not prove physical geometry or installation.

Residual `.cvstock` schema 2 stores the simulation context and its digest alongside
the stock grid. Saving rechecks the context both before the file picker and at
the write. Loading requires matching program, stock, tools, assembly, workholding,
component CAD and byte identities. Schema 1 files lack these inputs and are
rejected with an instruction to recompute; the original file is retained. Existing
job-archive residual provenance/portability requires separate further work.

The current subtraction model still uses declared axial tool envelopes and voxel
centers. Fixture/vise checks use conservative bounds. Manufacturer cutter/holder
meshes are visual assets; swept holder and whole-machine collision qualification
remain open. No physical offsets or controller commands are changed by review.
