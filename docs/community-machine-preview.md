# Community Carvera CAD preview

The desktop viewer supports a locally installed, data-only CAD profile at
`~/.carvera/machine-profiles/c1-v9.json.gz`. The app reads it at startup; without
it, the original schematic remains available. The CAD files and derived mesh
are external assets, not included in this repository or the application bundle.

## Source

Repository: https://github.com/Carvera-Community/Carvera_Community_Profiles

Pinned revision: `10876843c78cebf307a1ddbdef3cc21c4dbabb33`

- `Machine_Design_Files/CarveraC1_3 Axis_MachineModel v9.step`
- Matching `Machine_Design_Files/CarveraC1_3 Axis_MachineModel v9.f3d`
- `MachineAsset/Machines/simulation.mch` inside that Fusion archive

The named STEP assemblies map as follows: Frame is fixed; Bed moves in negative
Y; Z-Axis carries the X slide; Spindle moves with both X and Z. Assembly and face
transforms are applied before tessellation. The matching Fusion definition
supplies the X->Z->head and Y->table chains and collet attachment point
`(6.0459434767, 18.4084109340, 118.4495196921)` mm.

The lightweight v9 STEP export contains 21,218 triangles across seven bodies.
Use `scripts/convert_carvera_profile.py` in an isolated environment with
`cadquery-ocp==8.0.1.0.0` to reproduce the mesh. The converter only reads CAD;
it does not execute postprocessor code. Copy its output to the profile path
above and restart the controller. Output metadata retains source revision, URL
and SHA-256. CAD dependencies are not required in the controller runtime.

## Registration and limits

CAD bed coordinates are translated by `(-360, -240, -140)` mm into the viewer's
nominal negative-travel frame. The spindle placement accounts for the length
of the tool mesh currently drawn. Stock and the toolpath translate with the
bed; their relative motion remains equal to the program coordinates.

This is a three-axis visual rehearsal. Program origin and stock must be entered
explicitly. Its registration is not a measured physical machine origin, does
not consume live head MCS or automatically apply TLO, and does not qualify a
cut. No collision engine, stock subtraction, ATC animation or rotary rehearsal
is implemented. Fusion collision-pair declarations are not runtime checks in
this controller.

The viewer lives in its own desktop layout slot with one set of view controls,
a single preview playback strip and a separate resizable camera pane. The legacy
overlay objects remain alive for existing callbacks, outside the desktop scene.
Navigation, camera viewing and preview playback do not send machine commands.

## ATC rack and six slots

`scripts/add_carvera_atc.py` adds the six tool holders, their CAD number plates,
tool-height sensor and touch-probe dock from `CarveraC1_MachineModel DETAILED.step`
to an existing converted v9 profile. Run it in the same conversion environment,
passing the existing `.json.gz` profile, detailed STEP file, pinned `--revision`
and a new `--output` path. It excludes the detailed model's duplicate
`ATC Holder (1)` assembly. The bed coordinates agree with the v9 bed; source
revision and detailed STEP SHA-256 are retained under `atc` metadata.

The independent **ATC / slots** visibility toggle leaves the chassis and
workholding unchanged. The rack follows Y table motion in full-machine and
work-area views. This is CAD geometry with nominal registration; tool occupancy,
physical rack alignment and tool-change motions are not established by it.

## Saunders imperial plate

The manufacturer's STEP master includes both INCH Plate and METRIC Plate.
Use `--saunders-inch /path/to/Makera_Carvera_Fixture_Plate.step` with the converter
to include only the imperial plate. This replaces WasteBoard and Anchor1 bodies;
the plate is part of the moving table group. It does not invent vise or clamp
placements. Source: https://saundersmachineworks.com/products/makera-carvera-fixture-tooling-plate

The plate is centred over the original MDF envelope and seated at its former
bottom plane. This is a draft registration, explicitly shown in the workspace,
not a measured mounting height. Fixture metadata retains the CAD hash, original
bounds and translation. Confirm the physical origin, stand-off height and
workholding before interpreting clearance. This asset does not provide collision
checks or confirm that the mounted plate matches the current manufacturer's CAD.

## Workholding inspection

The current converter can include the manufacturer's Gen3 Hobby imperial Mod
Vise assembly with `--mod-vise-inch` alongside `--saunders-inch`. The model keeps
fixed and adjustable bases and their top jaws as separate components. The plate
uses `fixture`, and vise components use `workholding`; both move with the Y table.
Older profiles containing `INCH Plate` in `table` are recognized automatically.

Work-area framing is the desktop default and hides the chassis and carriage to
expose the fixture. Full-machine framing restores them. Independent visibility
controls remain in Program & simulation. Vise placement controls store X/Y/Z
translation, Z rotation and adjustable-jaw displacement in the named machine
profile. Rotation uses the CAD assembly pivot; jaw displacement follows CAD Y
before rotation. These values are draft visual placement, not measured mounting
holes, stand-off, jaw gap or clamping qualification. The supplied top jaws are
shown; the separately purchased soft jaws and Castle Grips are not substituted
without a mounting registration.

## Current workshop preview placement

The October 3, 2026 camera estimate places the vise left-to-right on the imperial
plate. Relative to the converted profile's original plate-centred vise pivot,
the saved placement is X `-77.9376`, Y `-45`, Z `0` mm, Z rotation `90` degrees,
and movable-jaw displacement `-74.5953` mm. The jaw displacement produces an
approximately 127 mm visual opening. These are local preview settings only;
they do not change controller work offsets or move the machine.

The named stock **Current aluminum block - camera estimate** uses dimensions
`127 × 69.4182 × 50.8762` mm and minimum corner
`(-118.6, -94.7091, -0.36788)` mm in program preview coordinates, with preview
work offset `(-180, -120, -110)` mm. Keep the work offset with those coordinates
when recreating the scene. The stock is a rectangular outer envelope and does
not include the skimmed hat, steps or removed material.

Visible green fixture-hole plugs informed the estimate: the imperial CAD grid
has a 19.05 mm pitch, and the setup appears toward the front and left of the
plate. The final refinement moved both vise and stock 38.1 mm left and 45 mm
forward from the initial centred estimate. Hole correspondence was judged
visually, without calibrated camera registration, probe measurements or verified
mounting-hole identities. This is not a collision-qualified physical setup.

Vise placement persists in the named machine profile. Named stocks persist in
the scene library, but the active stock selection currently needs reselecting
after restarting the application. CAD assets and local connection preferences
remain external; do not copy a user's complete local settings into the repository.
