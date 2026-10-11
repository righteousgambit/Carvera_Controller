# Docs: https://github.com/Carvera-Community/Carvera_Community_Firmware/blob/master/tests/TEST_ProbingM460toM465/TEST_ProbingM460toM465_readme.txt
from carveracontroller.addons.probing.operations.OperationsBase import ProbeSettingDefinition


class AngleParameterDefinitions:
    XAxisDistance = ProbeSettingDefinition("X", "X Distance", False, "X distance along the particular axis to probe.")

    YAxisDistance = ProbeSettingDefinition("Y", "Y Distance", False, "Y distance along the particular axis to probe.")

    PocketProbeDepth = ProbeSettingDefinition(
        "H",
        "Pocket Depth",
        False,
        "Optional parameter, if set the probe will probe down by "
        "this value to find the pocket bottom and then retract slightly "
        "before probing the sides of the Angle. Useful for shallow pockets",
    )

    FastFeedRate = ProbeSettingDefinition("F", "FF Rate", False, "optional fast feed rate override")

    RapidFeedRate = ProbeSettingDefinition("K", "Rapid", False, "optional rapid feed rate override")

    RepeatOperationCount = ProbeSettingDefinition(
        "L",
        "Repeat",
        False,
        "setting L to 1 will repeat the entire probing operation from the newly found center point",
    )

    EdgeRetractDistance = ProbeSettingDefinition(
        "R",
        "Edge Retract",
        False,
        "changes the retract distance from the edge of the pocket for the double tap probing",
    )

    QAngle = ProbeSettingDefinition("Q", "Angle", False, "TODO: need docs")

    BottomSurfaceRetract = ProbeSettingDefinition(
        "C",
        "Btm Retract",
        False,
        "optional parameter, if H is enabled and the probe happens, this is how far to retract off the bottom surface of the part. Defaults to 2mm",
    )

    # M465 uses S differently from the corner and bore cycles: it applies the
    # measured angle as the work coordinate system's rotation, so the job can
    # run on stock that is not square to the machine. The label was copied from
    # those other cycles and described zeroing X and Y, which is not what
    # happens here and hid the feature.
    SaveRotation = ProbeSettingDefinition(
        "S",
        "Set Rot",
        False,
        "apply the measured angle as the WCS rotation, so you can machine stock "
        "that is not square instead of re-fixturing it",
        "1",
    )

    ProbeTipDiameter = ProbeSettingDefinition("D", "Tip Dia", False, "Probe Tip Diameter, stored in config")

    ProbeDepth = ProbeSettingDefinition(
        "E",
        "Probe Depth",
        False,
        "how far below the top surface of the model to move down in order to probe on each side",
        "2",
    )

    UseProbeNormallyClosed = ProbeSettingDefinition("I", "NC", False, "Probe is normally closed")

    VisualizeDistance = ProbeSettingDefinition("V", "Visualize", False, "")
