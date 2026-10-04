# Machine viewport gestures

The viewer consumes wheel input inside its bounds and captures left/right drags
until release, including outside the pane. Left drag orbits when Orbit is active;
Pan mode and right drag pan. Disabled viewers and gestures owned by another
viewer are ignored. Normal and grabbed Kivy dispatches do not apply a move twice.
Wheel gestures do not leave a drag capture behind. Double tap restores framing.
These controls modify the preview view and issue no machine commands.

Source interaction tests exercise wheel boundaries, captured orbit, right-button
pan, disabled state and release. DESKTOP40 bookmark verification demonstrated
view restoration but left direct model routing open. A rebuilt native app must
verify that wheel/drag input over the model reaches it without scrolling the
workbench before this routing requirement closes.

## DESKTOP41 checkpoint

Installed source `6cd4136d7677110038ea4d7de4f79ffcf480c560` passed 967
unit tests and 31 full-workspace integration tests. The latter includes a wheel
event dispatched through the actual root: viewer zoom changes and workbench
scroll does not. Native orbit visibly rotates the model, Pan moves it across the
pane boundary, and Fit view restores framing. The app was disconnected during
these checks and the camera remained visible. No motion, probing, spindle or
ATC actions were taken. DESKTOP40 is preserved as recovery.

Native wheel input targeted over the model still scrolled the workbench; this
disagrees with the direct and full-workspace event tests. Wheel routing remains
OPEN pending native event-coordinate/provider diagnosis. Do not infer its
completion from source tests. Receipts and screenshot are in
`/Users/wes/Downloads/carvera-desktop41-20261003/`.

## Wheel-provider investigation

The installed environment uses Kivy 2.3.1. Its SDL window Python provider obtains
relative cursor coordinates before dispatching a wheel event; the pinned Cython
backend's `get_relative_mouse_pos()` reads `SDL_GetGlobalMouseState` and subtracts
the window position. Its wheel event tuple carries delta and direction, without
cursor coordinates. Primary source:
https://github.com/kivy/kivy/blob/2.3.1/kivy/core/window/_window_sdl2.pyx

A possible cause is disagreement between synthesized event location and the
actual global cursor location. This remains an inference until native event
coordinates are captured. The next diagnostic should compare raw window input,
SDL global cursor, density, transformed touch coordinates and receiving pane.
Do not change routing to the previously clicked pane without that evidence:
ordinary pointer-based wheel behavior must continue working.
