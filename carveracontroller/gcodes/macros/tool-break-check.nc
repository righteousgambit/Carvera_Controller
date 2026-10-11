(Tool break check)
(Re-measures the current tool and halts if its length has changed beyond)
(tolerance, which means it broke during the preceding operation.)
(Run after a tool's last cutting move, before the program continues.)
(
  Detects a tool that broke AFTER its initial calibration. It cannot
  detect one that was already broken when loaded.
)
G90 G94
G21

(The spindle must be stopped before measuring, or the check itself fails.)
M5

(H is the tolerance in mm. 0.1 is the firmware default; tighten it for)
(small tools where a broken flute is a smaller length change.)
M491.1 H0.100

(Reaching here means the tool is intact and the program may continue.)
