# Held-out camera image checks

Camera → Fit & exchange now accepts separate measured X Y Z U V correspondences from the same frozen image. These points are excluded from pose fitting. The review reports ordered image errors, RMS, maximum error, entered image coverage, and whether the maximum meets an explicitly entered pixel limit. A blank limit produces no pass/fail conclusion.

Checks refuse coordinates reused from the fit or duplicated within the check set. Changing fit inputs withholds the result until refitting; capturing or loading another reference clears the check points. These checks remain session-local and are not part of the calibration-file export.

Disjoint entered points do not prove independently measured coordinates. Pixel agreement does not establish millimeter accuracy, lens calibration, raised-stock registration, spindle pose, exposure synchronization or cutting clearance. The existing fitted registration, overlay and save behavior are unchanged. No machine commands are sent.

Focused validation covers a zero-error fit with failing held-out points, exact limit boundaries, missing/invalid limits, point reuse, input replacement and actual Kivy panel callbacks.
