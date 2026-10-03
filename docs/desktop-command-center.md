# Desktop command center

The Job stage is always visible in the left half, with a tabbed Workbench in the right half. Machine/toolpath sits above the Ubuntu camera. The two media panes fit vertically with a 16:10 machine viewport and the camera’s actual frame ratio (normally 16:9). Imagery occupies more than 85 percent of each pane at normal desktop sizes. Workbench toggles the entire controls pane. Tabs retain the stage and live context while changing the controls. Preview, playback, geometry, and camera controls live in the Workbench.

Position & motion retains separate work and machine coordinates. Setup & tools exposes stock probing, offsets, facing, inspection, physical tool calibration, and preview geometry. Spindle & engagement contains live readings and the shadow monitor. Commands & program retains the existing controller console and program pagination. Machine & connection and Camera source contain connection preferences.

Profiles opens a local persistent library for named machines, cutters, and six-slot ATC toolsets. Create two named toolsets for roughing/features and finishing, and load the appropriate set for each program. Loading profiles affects preview metadata, never physical tool changes or measured tool offsets. Slot assignment does not establish that a cutter is actually installed.

Machine profiles hold name, model, network address/port, camera endpoint, and optional bounded CAD profile. Use profile selects the metadata; Connect profile is explicit and available only when disconnected. The connection header continues to identify the actual connection.

Cutter definitions use millimeters regardless of program units. Loaded library geometry is separate from CAM comments, persists across program loads, and restores a selected toolset on app restart. Save and load are explicit. Import/export JSON supports moving the library between computers. Unknown measured lengths remain blank. Three photographed quarter-inch cutters are seeded; no ATC slots are guessed.

Choose program opens the searchable local/machine browser. Preview locally, load from machine, and upload are separate actions; none starts a program. Review & start retains existing machine preflight.

The CAD preview uses nominal kinematics and draft fixture registration. Collision qualification, material removal, automatic ATC swaps, and adaptive feed actuation remain outside this implementation.
