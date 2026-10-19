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

Raw residual-grid assets in portable job packages still do not preserve the full
interpretation/geometry context. Their restoration path establishes a nominal
local context. Retaining and verifying portable interpretation provenance in
that path remains separate integration work; this change does not qualify those
imports, installed workflows, controller interpretation or physical execution.
