(Spindle warm-up)
(Ramps the spindle through its range so it is thermally settled before)
(precision work. Nothing cuts: the tool never leaves clearance height.)
(Roughly 10 minutes. Safe to run with the table empty.)
G90 G94
G17
G21

(Park clear of the work area before spinning up.)
G53 G0 Z-5.000

M3 S3000
G4 S60
M3 S6000
G4 S90
M3 S9000
G4 S120
M3 S12000
G4 S150
M3 S14000
G4 S180

(Ramp back down rather than stopping hot.)
M3 S8000
G4 S60
M5

(Spindle warm. Check the temperature readout before starting precision work.)
M2
