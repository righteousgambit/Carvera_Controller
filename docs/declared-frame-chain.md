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

## Linked spatial frame view

**Show spatial frame view** adds a collapsible diagram to the same snapshot.
World or Workpiece selects one reference for every displayed origin and axis;
Front, Top, Right and Isometric choose orthographic projections. Selecting a tree
row highlights its origin and local XYZ axes. Clicking co-located origins cycles
through their exact named identities, updating the same detail selection.
Tool and workpiece chain links use teal and amber; selected X/Y/Z axes use
red/green/blue. Glyph lengths are display aids, not physical geometry dimensions.

The dimensionless tool-axis row draws orientation at the spindle reference and
states that it is not an additional tip position. Both tip rows draw the same
physical tip in the chosen display reference; their existing text retains the
original world/workpiece calculation semantics. Changing projection or reference
does not change the immutable snapshot, declared geometry, selected branch,
operator stores or controller state. Collapsing preserves selection and releases
space to the calculation tree. The diagram is schematic frame geometry; it does
not supply machine bodies, collision checks or measured registration.

Snapshot source/time is a collapsible provenance section within the same scroll
area. This keeps narrow views from sacrificing the diagram to a wrapped header;
the exact capture and state source remain inspectable. The diagram's controls and
height follow the available viewport, while Close stays outside the scroll area.
