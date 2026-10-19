# Interpretation identity for simulation dependencies

Geometry context schema 2 identifies the program's interpretation as well as its
text, stock, workholding, tools and CAD. The interpretation record contains the
retained parser settings, active dialect, declared work offsets, indexed resolved
motion SHA-256 and unresolved-line SHA-256. Unknown parser settings remain absent
as `None`; they are never reconstructed from defaults.

The resolved-motion fingerprint encodes line, start/end coordinates, tool,
rapid/cutting flags, rotary data and named work frame. It is prepared in the same
worker indexing pass that publishes tool and spline indexes. Motion, indexes and
fingerprint are replaced together. Unresolved lines and their fingerprint are
also published together. Context refresh reads the cached identities and bounded
parser metadata; it does not traverse the motion or unresolved-line arrays.

A settings or derived-motion change can therefore invalidate a residual result
or clearance input even when the source text hash is unchanged. The dependency
explanation reports **Program interpretation**. Its operation dependencies remain
conservative: this is not a spatial-region dependency graph or permission to
change machine offsets.

Existing contexts without interpretation metadata remain readable and retain
that absence. Comparing a schema-1 context with a newly captured parsed-program
context reports the missing interpretation rather than assuming compatibility.
JSON round trips preserve the identity of each recorded context.

Index preparation checks cancellation periodically and again before publishing
the complete index. Parsing and playback/clearance preparation forward their
existing cancellation callbacks. Explicit assignments of large motion tuples
remain synchronous; callers own their scheduling. Normal desktop parsing and
preparation run on workers.

## Verification limits

Local tests exercise settings changes, exact derived-motion changes, legacy
context comparison, JSON identity, indexed reads and cancellation. A synthetic
100,000-segment measurement observed roughly 0.22 seconds for fingerprinted
indexing versus 0.006 seconds for the old index, and 0.04 milliseconds per metadata
refresh. This added preparation cost occurs on the worker; these measurements do
not establish installed UI frame times, camera performance or a spindle control
loop's latency.

Portable job exports now include a separate bounded provenance asset containing
this complete context, the normalized program identity and the exact grid asset
SHA-256. Export verifies the detached CAD context and archive program first.
Known CAD locations normalize to their loaded content hashes; identical assets
can move to a different extraction directory without changing the dependency
identity. Tool geometry and stock-source location fields normalize along with
their asset records. No geometry or parser setting is dropped from comparison.

Import decodes and verifies provenance against program/grid bytes and prepares
the bounded residual display mesh on its worker. Mesh budget failures therefore
reject preparation before Apply. The final refresh publishes the prepared mesh;
it never scans occupied grid cells or builds triangles. Legacy grids without
provenance do not spend time preparing a continuation mesh.
After the matching program load completes, current prepared interpretation,
tooling, placement, workholding, assembly and CAD identities must match before
any residual geometry, grid or current identity is published. This final check
uses cached CAD hashes; it does not hash files on the refresh thread. Changed
settings and mismatched setup require recomputation. It does not automatically
change parser preferences, machine offsets, tool measurements or inventory.

Legacy grids without provenance remain loadable for inspection, but are not
adopted as a current continuation baseline. Review labels that limitation and
the simulation panel explains the need to recompute. Corrupted, unsupported or
oversized provenance refuses preparation before local setup is applied.

These checks preserve software dependency identity. They do not prove physical
stock registration, fixture clearance, tool length, firmware interpretation or
installed runtime performance. Published-volume ownership still relies on the
existing worker clone/replace contract. GPU upload and rendering remain separate
UI performance concerns.
