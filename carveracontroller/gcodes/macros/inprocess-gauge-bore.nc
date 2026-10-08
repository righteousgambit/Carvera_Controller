(In-process gauging: bore to size)
(
  Semi-finish, measure, correct, finish. This is what moves achievable
  tolerance from roughly +/-50um to +/-15um without changing any hardware.

  Before running, set:
    #510  nominal bore diameter, mm
    #511  finishing tolerance, mm  (loop stops inside this)
    #512  probe travel per side, mm  (must clear the bore wall)

  Assumes the bore is already semi-finished and the probe is the current
  tool, positioned roughly at the bore centre at clearance height.
  Requires community firmware: uses M461 and O-code flow control.
)
G90 G94
G17
G21

(Guard against running with nothing configured, which would probe blind.)
O100 if [#510 le 0]
  M118 ERROR: set 510 to the nominal bore diameter before running.
  M2
O100 endif

(Measure. L1 repeats the cycle from the found centre, which probes)
(symmetrically and is the cheapest accuracy available here.)
M461 X[#512] Y[#512] L1 F100.0

(#151 and #152 are the measured X and Y diameters.)
#513 = [[#151 + #152] / 2]
#514 = [#510 - #513]

M118 Measured mean diameter is in 513. Error against nominal is in 514.

O200 if [#514 gt #511]
  M118 Bore is undersize by more than tolerance. Apply 514 as a radial
  M118 offset in CAM and run the finishing pass again.
O200 else
  M118 Bore is within tolerance. No correction needed.
O200 endif

M2
