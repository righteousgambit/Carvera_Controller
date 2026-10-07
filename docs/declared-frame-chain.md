# Declared joint/frame chain inspector

Machine / Five-axis reachability & branches now offers **Inspect declared frame
chain**. It snapshots the selected calculated branch, or the first entered joint
row when no branch is selected. It cannot open while a calculation is running.

Separate tool and workpiece trees preserve ordered parent-local joint transforms.
A joint row shows its position and cumulative world origin. Selection explains its
axis, pivot, limits, local transform and cumulative `parent * local` transform,
including row-major rotation matrices. Declared limit violations remain visible
and do not authorize motion. Final tool/world and inverse-workpiece relationships
explain tool-tip positions and the dimensionless tool-axis direction. Origin-to-tip
length is applied once; no controller compensation is inferred or applied.

The snapshot carries capture time, state source and the complete declared-profile
hash. Editing the originating draft does not rewrite an already-open snapshot.
The scrollable tree/detail view retains a fixed Close action and wraps long values
at narrow widths. This supports declared head/head, head/table and table/table
models, including imported profiles; it does not establish connected hardware,
measured registration, TCP, collision clearance or backend execution.

Tests cover a nonzero rotary pivot followed by a parent-local translation,
noncommutative order, inverse workpiece rotation, single tool-length application,
all three illustrative topologies, limit diagnostics and invalid state rejection.
Actual-Kivy checks cover entered/selected-branch routing, read-only snapshot
retention, busy/invalid refusal, actual dismissal and a 500-pixel nine-joint view.
Package and installed/native acceptance require separate receipts. Requirement 22
and the complete overhaul remain OPEN.
