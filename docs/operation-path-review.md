# Operation path review

Selecting an operation in Program > Operations seeks its first source line and
highlights the complete rendered operation in teal, with the surrounding program
dimmed. The preview marker retains its selected position. This is local geometry
review, not observed execution progress. The Operation highlight control restores
normal playback trimming and coloring when disabled. Existing tool, rapid, speed
and height visibility filters still apply.

The completed loader publishes the SHA-256 of its decoded, newline-normalized
program text. Highlighting requires the operation inspector's matching text hash.
Starting a load, clearing geometry or changing to Live clears the visual selection;
returning to Preview/Compare reconciles it against the current loaded identity.
Header-only operations without drawable motions remain unhighlighted. Arc samples
and move-type duplicate vertices retain their source-line association, including
the preceding vertex required to draw the first selected segment. Selection updates
shader uniforms using binary searches; it does not copy the complete geometry.

Lines emit their untextured color directly. The legacy viewer classifies motion
with an inactive programmed spindle as travel; hiding travel can therefore hide
spindle-off feed motion too. This classification is not changed by highlighting.

Program task tabs now measure full captions plus padding when choosing their
minimum width. Caption/font-size changes reflow the grid, retaining single-task
content and readable selectors at narrow widths.

Source acceptance: `/tmp/carvera-operation-highlight-complete-tests.log` reports
30 passes (55.17 s), including the real loader, revision replacement, operation
selection/toggle, Live/Preview behavior, preserved filters, selected-path pixels,
navigation history and narrow/enlarged-font caption fitting. The final render was
reviewed; earlier renders, the fixed-column failure and the strict antialias pixel
failure are preserved. Ruff lint/format and both import contracts passed; final
architecture receipt is `/tmp/carvera-operation-highlight-final-imports.log`.
Installed/native acceptance remains open. DESKTOP145 was frozen at `33de5ab`
before this source change and does not include it. No machine command, upload,
offset change or physical machining qualification is claimed by these tests.
