# Current tool evidence in the calibration bench and bank preparation

The calibration bench and tool-bank board now read one tooling observation from
the selected controller owner. A selected private backend uses its current
session, connection, and actual transport endpoint, including the port. A stale,
closed, replaced, or changed-profile backend stays unavailable; it cannot inherit
the legacy GUI controller's tool or offset.

Backend offsets are displayed as raw firmware values with unknown units and
reference. They are separate from saved calibration measurements in millimetres.
Numeric equality with a saved measurement does not qualify a conversion, identify
a physical cutter, or establish a calibrated current-spindle TLO. Receipt history
still retains its original endpoint and tool number; GUI endpoint strings are
not silently equated with private-backend endpoints.

The legacy GUI observation keeps fresh-packet numeric comparisons. An explicit
disconnect retires that packet. Standalone read-only consumers without a
connection flag retain their previous numeric-packet behavior while connection
availability is explicitly unknown. None of these observations grants command
admission or starts measurement, exchange, or playback.

Tool-bank refresh signatures include owner identity, endpoint, freshness,
connection availability, active tool, and offset. Equivalent fresh packets reuse
the cards. Evidence text wraps and cards grow to fit their longest content at
both narrow and wide widths. Pocket titles wrap, and the evidence, assembly, and
preview actions stack when their labels would otherwise compete for space.

Measurement launch and durable backend calibration capture remain a separate
workflow. The bench continues to distinguish historical attributed measurements,
raw current reports, declared pocket placements, and physical qualification.
