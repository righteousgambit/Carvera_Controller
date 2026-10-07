# Tool bending sensitivity comparison

Setup > Tools > Bending comparison opens a local assumed-load comparison for the
selected nominal tool. Its library diameter and nominal stickout are captured
at opening; neither is a measured beam section or physical assembly measurement.
The operator must supply force, elastic modulus and the alternative geometry.

Length fields accept the shared imperial/metric expressions. Force accepts N,
kN and lbf; modulus accepts MPa, GPa, Pa and psi. Reference and candidate share
one declared force and modulus. Equivalent diameter and unsupported length are
explicitly editable. There is no force inference from spindle RPM or feed.

The model is a uniform solid circular Euler-Bernoulli cantilever with a fixed
root and transverse point load at its tip. I = pi*d^4/64, displacement =
F*L^3/(3*E*I), root stress = F*L*d/(2*I), slope = F*L^2/(2*E*I).
Results expose compliance in micrometers/N, displacement in micrometers, stress
in MPa and slope in radians. The compliance ratio remains meaningful for zero
force. Negative forces and nonpositive geometry/modulus are rejected. Short
beams and large displacement explicitly flag omitted shear/small-deflection
assumptions. No material strength or tolerance pass/fail is invented.

Flutes, stepped sections, distributed engagement, holder/spindle compliance and
chatter are omitted. These local sensitivity results do not qualify actual
cutting load, deflection, dimensional acceptance, or machine execution. Changing
any input clears the previous result. Closing the bench saves no profile and
sends no controller command.

Source verification: 57 model/unit/bench checks and 16 neighboring quantity/tool
checks pass. Analytical scaling tests independently exercise L-cubed and
D-to-the-fourth sensitivity, zero force, dimensional conversion and invalid
inputs. Mounted Kivy tests verify the route, no command/store mutation,
invalidation and the narrow layout. The rendered 360-dp bench was inspected.
Changed-module typing, Ruff and both architecture contracts pass. The first
attempt exposed a missing shared quantity-field step for the new dimensions;
its failed log is retained, and the corrected UI run passes. Package/native
acceptance and physical model qualification remain separate OPEN gates.

This advances part/process requirement 16 and tool-choice comparison, without
closing those complete workflows or the broader implementation objective.
