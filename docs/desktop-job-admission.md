# Reviewed job submission diagnostics

A reviewed start or resume saves its intent, refreshes the private child's cache,
and checks the current UI context before queuing the operation. The original
freshness, ownership, setup, review-expiry and callback deadlines still apply.

If the final check refuses admission, the run remains unresolved. Its retained
receipt distinguishes `not_submitted` from `backend_response_unknown` and names
the dispatch checkpoint. Known controller validation reasons appear in the
workbench and in the receipt: for example, changed setup or an unfinished
probe-settings transaction. Arbitrary exception text is replaced with a bounded
generic reason in the admission receipt.

The receipt also separates the client-cache age from the child's host-side
status-receipt age and records their combined age when both are known. These are
host observation ages, not firmware sample ages. Missing or invalid ages stay
unknown. Diagnostics neither admit a request nor cause retries, replay or GUI
controller fallback.

Observation policy is independent of cached connection state. A delayed snapshot
may update the displayed connection report, but cannot undo a polling choice made
while that read was pending. Explicit connect/disconnect responses still update
the policy. Polling a private cache is distinct from sending a machine command.

Verification uses the existing private child and loopback CNC fixtures. It does
not establish installed behavior, physical machine state or completed motion.
