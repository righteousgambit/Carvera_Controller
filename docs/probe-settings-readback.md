# Fixed-key persisted probe settings readback

The private `probe_profile_read` method accepts no parameters and reads only
`zprobe.probe_tip_diameter` and `zprobe.three_axis_probe_tlo_correction` using
`config-get sd`. It uses the existing serialized command path and M105 read
barrier; it does not expose whole-controller configuration or write settings.

The reader preserves each original bounded socket receive window and numeric
token. It refuses unknown/mixed/error/duplicate/partial responses, changed
connections, active transfers and unresolved outcomes. Missing SD settings are
explicitly absent; they are never replaced by default zero. Earlier command
receipts survive a refused later read. Receive windows can contain interleaved
or unattributed bytes and do not prove complete firmware response custody.

The independently implemented grammar is grounded in Community firmware commit
`2fd69ee0542e75f1ad0561e93317308c32ebe863`, Configurator.cpp SHA256
`c23d9923f97e1ba34b25c21f4c9f6ce0e16c8f4fc491d69ebbb6dec0b405b6c1`.
That source updates the active probe tip diameter when `config-set` executes,
but the ATC handler loads its three-axis TLO correction at initialization.
Matching SD readback does not prove active TLO application or persistence across
restart. Firmware identity, active settings, persistence, physical accuracy and
execution authority therefore remain explicitly unverified.

This source must be separately pinned by its private supervisor before use.
It does not install or activate a new controller runtime, apply a retained
WaveForm profile, update work-zero or authorize a machine effect. Native/TLS
integration, supervised settings application/recovery and installed/physical
acceptance remain separate owning gates.
