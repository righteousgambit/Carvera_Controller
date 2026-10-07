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
