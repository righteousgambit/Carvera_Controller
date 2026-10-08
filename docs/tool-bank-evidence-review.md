# Tool-bank evidence review

The preparation board filters all pockets, pockets missing definition/declaration/
logical or mapped receipt evidence, and selected physical assemblies. Counts still
refer to the whole bank. Selecting a filter does not change assignments, saved
preparations or controller state.

Each pocket opens an inline evidence review. Assessment shows assembly identity,
revision, linked cutter, logical versus mapped controller receipts, current-spindle
TLO comparison, every preparation issue and the reload review sequence. The raw
receipt view distinguishes capture/report timestamps, endpoint, reported tool,
applied TLO and reported spread. Every raw sample remains reachable: one receipt
and up to 80 samples are rendered per page, with bounded previous/next navigation.
Report times are desktop receipt metadata, not independently verified firmware
measurement times; raw timestamps, reported spread and samples are displayed without general-format rounding.
A logical T7 receipt and mapped controller T1 receipt remain distinct.

New evidence pages start at the top after Kivy text relayout. Closing the review
cancels its pending scroll reset. Program/machine/bank changes close the previous
review; mismatched preparation records clear the prior row and disable navigation.
Shorter action captions fit narrow panes, and detailed reload guidance lives in
the pocket assessment rather than repeating beneath the preparation controls.

The engine has explicit validated record, binding, row and offset-comparison
contracts. Canonical records reconstruct known fields and reject malformed types,
nonfinite/overflowing timestamps, duplicate physical assemblies/pockets and duplicate
logical tools. The store reads at most MAX_BYTES + 1 before JSON decoding, retains
invalid originals and preserves stale-writer/atomic-save behavior. Invalid comparison
clocks or nonfinite arithmetic cannot produce a matched TLO state.

Source verification (2026-10-05 UTC): 69 bank/custody/mapped-program regressions
passed in 6.07 seconds, including 360/760 dp controls, filter selection, all raw
sample pages, stale-context rejection, atomic failure and command-free review.
A 360 dp source render was inspected after correcting initial cursor-to-end behavior.
The changed engine passes focused strict typing; repository Ruff lint/format (503
files), diff and both architecture checks pass. Full local strict checking remains
open at 980 errors in 55 files (88 checked), down by 36 from the prior local scope.
Package baseline remains 148 errors in 19 files. Local imported-addon scope differs
from hosted CI. No check configuration was weakened.

This source postdates installed DESKTOP186. Installed workflow acceptance, physical
assembly reconciliation, qualified offsets, reload/re-entry execution and advanced
machine backend acceptance remain open. Neither this review nor numeric TLO agreement
identifies the actual physical tool or dispatches a machine command.
