# Import a declared joint-motion study

In **Program → Operations**, inspect a feed block using `G93` with one explicit positive `F` word. The **Inverse-time motion** card provides **Copy block identity** and **Import joint study…**. Unknown block duration disables both controls.

1. Copy the selected block identity. It contains the program's parsed-content SHA-256, one-based source line and requested duration in seconds.
2. Prepare a schema-1 JSON study using that identity, your declared kinematic model, unwrapped joint samples and velocity limits. The model and trajectory source fields describe where those declarations came from.
3. Import the file through the controller's file picker. Background review can be cancelled. Changing the selected block or program cancels review and rejects late results.
4. Inspect joint velocity exceedances, position-limit violations, interior velocity changes, tool-tip paths in world and moving work frames, and model/source details. Content hashes identify the exact imported file and model.

An invalid replacement retains the previous accepted study and displays its import error. Imported studies remain in memory for the loaded program; unloading clears them. Importing or copying identity sends no controller commands.

The following geometry is an **illustrative rotary-table model**, not a Carvera configuration or a measured setup. Replace the identity and declarations before importing it:

```json
{
  "schema": 1,
  "program_sha256": "PASTE_THE_64_CHARACTER_HASH_FROM_COPY_BLOCK_IDENTITY",
  "line": 2,
  "seconds": 30,
  "model_source": "Declared table model; describe your actual source",
  "trajectory_source": "Entered unwrapped joint trajectory; describe your source",
  "machine": {
    "schema": 1,
    "name": "Illustrative rotary table",
    "tool_chain": [],
    "work_chain": [
      {
        "name": "table",
        "kind": "rotary",
        "axis": [0, 0, 1],
        "minimum": -720,
        "maximum": 720,
        "pivot": [0, 0, 0]
      }
    ],
    "tool_base": {"translation": [100, 0, 0]}
  },
  "tool_length_mm": 10,
  "velocity_limits": [
    {
      "name": "table",
      "kind": "rotary",
      "per_second": 2,
      "source": "Declared velocity limit; describe your actual configuration"
    }
  ],
  "samples": [
    {"fraction": 0, "positions": {"table": 0}},
    {"fraction": 1, "positions": {"table": 90}}
  ],
  "linear_step_mm": 1,
  "rotary_step_degrees": 1
}
```

Samples require strictly increasing fractions spanning exactly 0 to 1. Each contains exactly the model's configured joints. Linear coordinates and rates use mm and mm/s; rotary coordinates and rates use degrees and degrees/s. A 350-to-10 rotary transition remains a declared -340-degree motion. The review does not invent wrapping, joint mappings from XYZ/ABC program words, endpoint stops, acceleration or controller blending.

Files are bounded to 256 KiB, two to 2001 input samples, one to nine configured joints and 10000 subdivided poses. Missing/unknown fields, duplicate JSON keys, strings or Boolean numeric values, nonfinite numbers and incompatible revision/line/duration are rejected. Sampling steps limit joint increments; Cartesian error and between-sample clearance are not bounded.

This workflow reviews declarations. It does not establish backend TCP support, actual machine mapping, compensation, observed following error, physical clearance or qualified motion execution.

## Supplied feedback traces

An optional `observed_feedback` member associates a sourced trace with the same exact program/block identity. Supply two to 2001 samples, in strictly increasing block-relative seconds spanning zero through the selected block's duration. Every sample must contain all configured joints in `reported`; optional `commanded` coordinates must be present for every sample or absent throughout. Rotary positions remain unwrapped. Linear values use mm; rotary values use degrees.

For the illustrative 30-second table study above, the following is a **synthetic demonstration**, not measured machine feedback:

```json
{
  "observed_feedback": {
    "source": "Synthetic example; replace with the actual feedback capture source",
    "timing_source": "Block-relative example times; replace with capture and alignment method",
    "samples": [
      {"seconds": 0, "reported": {"table": 0}, "commanded": {"table": 0}},
      {"seconds": 5, "reported": {"table": 2.5}, "commanded": {"table": 2.4}},
      {"seconds": 15, "reported": {"table": 22.5}, "commanded": {"table": 22.4}},
      {"seconds": 30, "reported": {"table": 90}, "commanded": {"table": 89.9}}
    ]
  }
}
```

The inspector shows maximum absolute position secants as velocity, their midpoint-time differences as acceleration, and the next differences as jerk. Nonuniform intervals retain their actual durations. Acceleration requires at least three positions and jerk four; missing quantities remain unknown. Reversals count changes between nonzero signed interval rates, retaining a reversal through a sampled stop. The maximum supplied sample gap stays visible. These estimates do not bound peaks between samples and can amplify sensor noise; no filtering is silently applied.

Command/reported error is the maximum absolute paired-coordinate difference at a supplied timestamp. Without command samples it stays unknown. A source label and block-relative times do not prove exposure/servo clock alignment, coordinate compensation ownership, backend following-error semantics or actual capture identity. The model/source details retain the capture and timing declarations alongside the imported file hash. Supplied feedback remains separate from the declared kinematic trajectory; it does not silently replace simulation geometry or become controller commands.
