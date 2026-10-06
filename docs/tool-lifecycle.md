# Physical cutter lifecycle evidence

Setup → Compare tools & calibration → Physical assemblies → Lifecycle connects
cutting-use intervals, inspections and replacements to a distinct physical
assembly identity. Creating or selecting a cutter design does not identify the
physical item. Create a new assembly when the physical cutter is replaced;
editing a definition retains that item's use and evidence.

Record cutting use accepts explicitly attributed cutting minutes, material,
unique run/interval reference, evidence source, observation time with timezone,
and outcome note. Spindle-on time and nominal CAM duration are not inferred as
cutting use. Duplicate interval references on one identity reject atomically.
The total is recorded usage only; unrecorded use and remaining life are unknown.

Record inspection accepts an operator condition (unknown/serviceable/monitor/
remove), method/source/note and optional measured cutting diameter with mm/in
entry. Latest means latest observation time, not latest entry time. Condition
labels are operator observations, not automatic wear diagnoses or execution gates.

Declare replacement links the reviewed old and new definition revisions. It
retires the old identity locally, preserves its calibration/use/inspection
history, and starts the new identity without transferring counters or evidence.
Cycles, duplicate replacement targets, stale revisions and contradictory dates
reject without changing the file. Existing location declarations are retained
as unresolved history: explicitly remove/replace them after physical work. New
location declarations and new bank preparations for the retired identity are rejected.
Existing bank reviews mark it replaced and retain raw receipts while withholding
current-applicability status until a replacement is reviewed. Late-entered old
use may be recorded only if its observation predates replacement. Postmortem
inspection remains available.

View lifecycle shows every receipt in bounded 20-record pages, newest observation
first, including exact receipt/definition IDs, original source, saved time and
observation time. Pages reset to the top. Overview shows use/inspection state,
while Lifecycle concentrates related actions and evidence. Compact panes fit
all four actions in two columns. The selected assembly caption stays synchronized
with programmatic selection and changes to its name.

Saving validates and snapshots inputs on the UI thread, then writes on a worker
with the existing cooperating-writer lock and atomic replacement. Repeated
submission is disabled while saving; a context change cannot redirect the
write or publish its completion into an unrelated machine's status. Errors retain
the draft and original file. No controller command, offset, tool change, run or
measurement transport is invoked.

New receipt kinds extend custody schema 1. Older builds reject unknown kinds and
preserve the original file; they cannot display the new lifecycle history. Keep
the preupdate operator-store snapshot alongside the recovery app. Do not replace
an operator file with a synthetic demonstration store.

Source acceptance covers restart persistence, attribution separation, chronological
inspection ordering, old/new replacement chains, stale/concurrent/duplicate
transactions, rejected-file preservation, every history page, UI cancellation,
mm/in measurement entry, background ownership and compact rendering. Native
installed workflow, actual run-receipt attribution, automatic execution binding,
physical identity/inspection qualification and the complete tool-wear requirement
remain separate open gates.

## Long-form navigation checkpoint (2026-10-06 UTC)

Custody forms retain their validation/save controls while explicit Scroll up/down
moves an overlapping viewport, stops at each boundary and clears inertial velocity.
The navigation strip disappears when content fits; a right gutter separates fields
from the scrollbar, horizontal scrolling is disabled, and empty validation space
collapses. Navigation preserves drafts and performs no persistence or CNC commands.

The prior DESKTOP190 native drag attempt did not move the long-form scrollbar.
A subsequent full-app pointer-routing regression reaches the bottom using the
existing scrollbar implementation, so that native discrepancy is still unresolved;
these explicit controls provide a separately testable pointer route rather than
claiming the original native drag behavior was fixed. Eight scrolling/lifecycle
checks and 37 related custody/process/passport/comparison/focus checks pass, with a
360 dp rendered inspection reviewed. Installed interaction remains a separate gate
until the next frozen update is exercised. Physical qualification and the complete
original and supplemental capability scopes remain open.

## Immediate scrollbar gesture checkpoint (2026-10-06 UTC)

A separate regression demonstrates that Kivy applies the content-pan threshold to
an explicitly grabbed scrollbar: a two-pixel handle move formerly left scroll_y
unchanged. DesktopScrollView now starts its own bar gesture in scroll mode while
content panning retains the normal threshold. Disabled views do not capture a bar
gesture. Twenty combined scrolling/lifecycle/focus checks pass, including full-app
pointer routing, nested wheel handoff and draft-preserving page controls. Compact
form validation now declares Window size to avoid order-dependent DPI/viewport
assumptions. The previously observed installed-popup discrepancy remains open until
this exact revision is exercised; the source regression alone does not close it.
