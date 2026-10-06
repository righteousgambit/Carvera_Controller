# Retained plane inspection review

Surface inspection records now separate Receipts, Record receipt and Plane review.
Entry drafts survive section changes, while hidden fields release keyboard focus.
The plane action runs in the serialized inspection worker; changing feature/policy
or closing the view discards a late result. New retained/imported/batch receipts
invalidate the preceding fit. No machine command or datum write is dispatched.

Select a retained nominal feature as the anchor. The review includes features with
the same part, component and exact declared setup/context, aligned outward normals
(dot product within 1e-10), and coplanar nominal points (within 1e-6 mm). Other nominal
or setup groups remain separate. Choose latest or earliest **retained** receipt per
feature: this is capture/storage order, not acquisition-time sorting. The selection
never falls back past a raw or incomplete receipt. Missing receipts, raw triggers and
missing registration/compensation references are listed explicitly; mixed reference
pairs reject the combined review. Unknown observation time remains unknown.

Each selected compensated ball center is projected by its own retained tip radius
along its nominal outward normal. This approximates a contact using declared geometry;
it is not measured contact-direction reconstruction. A deterministic orthonormal
basis fits heights along the anchor normal by centered, scaled least squares. The
result retains the centroid, fitted normal, tilt, anchor normal offset, signed
per-receipt orthogonal residuals, residual RMS/range and degrees of freedom. Fewer
than three receipts, spread below 1e-9 mm, or normalized covariance determinant at
most 1e-10 of trace squared cannot produce a fitted plane. These numerical guards
are not measurement uncertainty estimates.

The chart selects exact feature/receipt/source/registration/compensation identities;
adjacent controls reach every fitted receipt. Three points give zero residual degrees
of freedom. Residual range is over the selected samples around a least-squares plane;
it is **not minimum-zone flatness** or proof of unsampled surface form. An optional
mm/in residual-range limit produces a labeled numerical comparison.

Export `.cvplane` retains the complete input feature/receipt snapshot, exact input
hash, method, policy, selected/excluded receipts, derived values, evidence note and
entered comparison limit. Export recomputes the report before writing, rejects altered
derived values, bounds output to 16 MiB, writes atomically, and independently reads
back the bytes/hash. The chooser retains the reviewed snapshot and limit. It does
not restore geometry, offsets or machine state. Physical registration, compensation,
uncertainty, minimum-zone fitting, wider geometric tolerances and qualified machine
receipt transport remain open parts of original requirements 11/12 and supplemental
feature inspection requirements.

Source verification: 102 combined inspection/receipt/batch/exchange/focus checks
pass (22.50 s, one existing SSL warning). The final focused plane UI suite passes
eight checks after the optional-input/paging/detail-layout refinements. The changed
plane engine passes focused strict typing; full lint/format and both architecture
contracts pass. Narrow/wide source renders are reviewed. Native installed acceptance
and physical measurement qualification are separate gates.
