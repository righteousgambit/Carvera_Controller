# Threaded-hole preview context and recovery

The holes-and-threads planner captures its explicit recipe, loaded cutter
geometry, declared machine/stock/workholding setup and current program preview
when calculation begins. Before opening the result it checks that context again.
A later local or remote program choice, reload, setup edit or cutter edit wins
over the older calculation. Start a new recipe also supersedes pending work.
The discarded calculation does not create a generated job file or replace the
selected preview. Camera framing, zoom and component visibility remain free to
change while planning.

Pass generation and G-code encoding run on the calculation worker. A worker that
cannot start releases the busy state and reports a retryable error. Expected
validation failures and unexpected calculation/encoding exceptions also finish
with a nonempty error message; unexpected exceptions retain a diagnostic
traceback. A subsequent generation can retry using the current context.

These checks use local metadata and stage local previews only. They do not query
or command the CNC, establish physical mounting or tool identity, or qualify
clearance, thread fit or execution. Installed workflow verification remains a
separate gate.
