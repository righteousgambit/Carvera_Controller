(Backlash check)
(Probes one face from both directions and reports the difference, which is)
(lost motion on that axis. Diagnostic only: nothing is compensated.)
(
  Setup: mount a parallel or gauge block with a face square to X, then
  jog the 3D probe close to that face, roughly centred on it.
  Run from that position. Results print to the console.
)
G90 G94
G17
G21

(Approach from the negative side, then retract well clear of any backlash.)
M466 X10.000 F100.0
#501 = #154
G0 X-5.000

(Approach the same face from the positive side.)
M466 X-10.000 F100.0
#502 = #154

(Difference between the two touch positions is the lost motion.)
#503 = [#501 - #502]

M118 Backlash check complete. Approach positions stored in 501 and 502.
M118 Difference is in 503, in mm. Values are persistent across power cycles.
M2
