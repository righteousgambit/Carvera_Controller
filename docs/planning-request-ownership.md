# Shared preview ownership and cancellation

Facing and holes/threads share a single local preview intent. A valid Generate
request withdraws older results from either planner before starting its worker.
Only the newest request can open a result, regardless of worker completion order.
Invalid input does not take ownership away from a valid pending calculation.
If a newer worker fails to start, the older result remains withdrawn; the
operator can explicitly generate again.

Both planners expose Generate and Cancel preview controls. Generate is disabled
while that panel has a worker in flight. Cancel immediately withdraws permission
to open its result and shows that background work is finishing. It does not kill
the Python thread. The panel retains its one-worker limit until completion, then
re-enables Generate. Cancelling after calculation but before the UI completion
also prevents publication. Cancellation changes neither the selected program nor
previously generated files. It does not undo a result that has already opened.

A completion clears shared ownership only when it still owns that request.
Cancelled/superseded completions release their own panel's busy state without
clearing a newer owner's state or showing an obsolete error. Starting a new hole
recipe also withdraws its pending result while preserving the new-recipe notice.
The existing setup, cutter and program snapshot checks remain in force.

This is local preview lifecycle management. It sends no controller commands and
has no connection to CNC feed hold, stopping a running program or spindle stop.
Installed workflow and physical qualification remain separate gates.
