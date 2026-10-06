# Fixed probe settings application producer

The private `probe_profile_apply` method adds a closed two-key SD update producer
to the existing serialized headless RPC executor. It accepts
`carvera.probe_settings_application.v1`, an exact connection identity, the
reviewed original settings, and proposed decimal tokens for
`zprobe.probe_tip_diameter` and `zprobe.three_axis_probe_tlo_correction`.
It accepts no arbitrary key or controller command.

The producer requires fresh stopped, settled controller observations. It rereads
both original SD settings and compares state, value and original numeric token
to the reviewed baseline before writing. Each fixed `config-set sd` command must
return the pinned firmware's exact success line. A subsequent original two-key
read must match both requested tokens. Duplicate JSON keys, nonfinite values,
changed connections, transfer/unknown state, stale observations, malformed
receive windows and contradictory command receipts refuse.

The grammar is independently implemented from Community firmware revision
`2fd69ee0542e75f1ad0561e93317308c32ebe863`. Configurator.cpp has SHA256
`c23d9923f97e1ba34b25c21f4c9f6ce0e16c8f4fc491d69ebbb6dec0b405b6c1`;
ConfigValue.h has SHA256
`cbe3c6a5e101622585a0c73badf006bfdf65d562d906722083a563483183b0b3`.
The latter bounds stored value tokens to 19 characters. Probe diameter must be
positive; both values are bounded to 500 mm in magnitude. Explicit missing/null
baselines and zero TLO remain distinct. No stock-diameter heuristic is used.

Completed command receipts remain chronological, including partial failures.
A refusal after the first write does not undo it or send the second write.
An uncertain command outcome does not trigger a retry or automatic rollback.
The external supervisor must durably retain the intent and original response,
reconcile the actual controller state, and obtain a fresh review before any
subsequent application. This private producer has no durable application journal.

Successful output means only `reported_sd_values_match`. It leaves active
settings, persistence, firmware identity, physical accuracy and execution
authority false. In the pinned firmware, changing the tip setting updates an
active value, while ATC TLO is initialized at startup; matching SD text cannot
prove active ATC TLO. The source pin does not authenticate a connected device.

This child source is not yet wired into WaveForm signed gateway/native
application admission, retained-profile binding or restart recovery. Tests use
synthetic links, local pipes and a loopback fake controller. No installed source
pin or real machine is changed. Historical settings readback remains unchanged.
