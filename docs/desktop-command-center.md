# Desktop command center

The Job stage is always visible in the left half, with a tabbed Workbench in the right half. Machine/toolpath sits above the Ubuntu camera. The two media panes fit vertically with a 16:10 machine viewport and the camera’s actual frame ratio (normally 16:9). Imagery occupies more than 85 percent of each pane at normal desktop sizes. Connection state, connection controls, Feed hold, and STOP remain at the top of the Workbench. Tabs retain the stage and live context while changing the controls. Preview, playback, geometry, and camera controls live in the Workbench.

Position & motion retains separate work and machine coordinates. Setup & tools exposes stock probing, offsets, facing, inspection, physical tool calibration, and preview geometry. Spindle & engagement contains live readings and the shadow monitor. Commands & program retains the existing controller console and program pagination. Machine & connection and Camera source contain connection preferences.

Profiles opens a local persistent library for named machines, cutters, and six-slot ATC toolsets. Create two named toolsets for roughing/features and finishing, and load the appropriate set for each program. Loading profiles affects preview metadata, never physical tool changes or measured tool offsets. Slot assignment does not establish that a cutter is actually installed.

Machine profiles hold name, model, network address/port, camera endpoint, and optional bounded CAD profile. Use profile selects the metadata; Connect profile is explicit and available only when disconnected. The connection header continues to identify the actual connection.

Cutter definitions use millimeters regardless of program units. Loaded library geometry is separate from CAM comments, persists across program loads, and restores a selected toolset on app restart. Save and load are explicit. Import/export JSON supports moving the library between computers. Unknown measured lengths remain blank. Three photographed quarter-inch cutters are seeded; no ATC slots are guessed.

Choose program opens the searchable local/machine browser. Preview locally, load from machine, and upload are separate actions; none starts a program. Review & start retains existing machine preflight.

The CAD preview uses nominal kinematics and draft fixture registration. The
Program workbench includes approximate stock removal, residual-stock persistence
and assembly clearance analysis; see `clearance-traces.md` for their model bounds.
These local calculations do not qualify physical registration or authorize a run.
Qualified adaptive feed actuation and advanced-machine execution remain open.

Automatic configuration downloads expose Cancel through the existing transfer
cancellation mechanism. Cancellation keeps transfer ownership until the worker
returns, suppresses the startup retry budget until reconnection, and discards a
late successful response rather than applying configuration after cancellation.
Queued progress updates cannot re-enable the canceled action. This source
workflow also checks cancellation inside framed header/payload reception so
continuous status noise cannot trap the transfer before its next packet. The
receiver emits cancellation instead of retrying after cancellation. Rebuilt/native
connection acceptance remains separate from source checks.

Wi-Fi connection and protocol detection now run in a background worker, like
USB connection. The event loop remains available for the camera and controls
while the socket opens or an earlier stream shuts down. Wi-Fi and USB connection
attempts exclude each other until the worker completion is delivered to the UI.
Only a successful completion persists the target and preferred connection method;
failure releases the busy state without recording a successful connection.
Timer-triggered reconnect callbacks marshal dialog and connection selection work
onto Kivy's event loop. Initialized-app regressions exercise a deliberately
blocked transport, failure, overlapping requests and timer callback thread
ownership. Installed reconnect stability still requires native observation.

The Scene tab defaults to full-machine framing. Independent visibility controls cover outer machine (fixed chassis and carriage), bed, spindle, cutter, fixture plate, vise, and stock. Work-area framing hides the chassis and carriage while retaining the spindle and enabled workholding. Fixture and vise selections replace only their own geometry group, preserving the machine and other component. Dropdowns include local registered CAD profiles, with import accepting bounded `.json.gz` machine-profile assets that contain the desired component group. The existing Saunders quarter-inch plate and Gen3 Hobby Mod Vise are listed when present in the selected machine CAD. Additional raw fixture/vise STEP files still require registration and conversion.

The cutter dropdown selects a saved tool profile and can display it without a program loaded. This is an explicit manual preview override; Follow program restores program tool changes. Stock dropdown choices are reusable local cuboids with size and minimum corner in program coordinates, saved in `~/.carvera/scene-library.json`. Stock setup remains draft geometry, not simulated material removal. Component selection and visibility never send commands, measure offsets, or establish physical installation. Invalid local scene libraries remain untouched and surface an error while the rest of the UI remains available.

Shared desktop dropdown rows use the same text size and palette as their closed
controls. Long action and profile names wrap, with row height expanding to fit;
the closed control still shortens its label to keep the toolbar compact. This
addresses the installed DESKTOP64 review-menu clipping. Source regression checks
exercise actual menu children at both normal and narrow widths. Rebuilt installed
acceptance remains a separate gate from those initialized-app checks.
