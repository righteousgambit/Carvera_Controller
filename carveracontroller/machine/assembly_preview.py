"""Resolve declared physical assembly geometry without changing catalog records."""

import hashlib
import json

from carveracontroller.machine.desktop_profiles import to_tool_definition, validate_record


def design_fingerprint(profile):
    return hashlib.sha256(
        json.dumps(validate_record("tools", profile), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def assembly_definition(assembly, profile, number=None):
    if assembly["profile_id"] != profile["id"]:
        raise ValueError("Assembly references a different cutter design")
    resolved = dict(profile)
    # A catalog's example seating/holder is not the physical assembly's seating.
    resolved["stickout"] = assembly["stickout_mm"]
    resolved["holder_geometry_path"] = assembly.get("holder_geometry_path", "")
    definition = to_tool_definition(resolved, number=number, units="mm")
    definition.description = assembly["name"] + " · " + profile["name"]
    return definition
