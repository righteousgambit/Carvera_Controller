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
