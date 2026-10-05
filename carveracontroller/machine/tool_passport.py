"""Read-only, revision-aware physical tool passport projections.

Paths are declared references, never filesystem or hardware verification.
"""

SECTIONS = ("Overview", "Geometry", "Assets", "Measurements", "Locations", "Revisions")


def passport_sections(store, assembly_id, profiles):
    assembly = store.assembly(assembly_id)
    if assembly is None:
        return {section: ["Select a physical assembly to inspect its passport."] for section in SECTIONS}
    design = next((p for p in profiles.get("tools", []) if p["id"] == assembly["profile_id"]), None)
    names = {p["id"]: p["name"] for p in profiles.get("machines", [])}
    result = {section: [] for section in SECTIONS}
    result["Overview"] = [
        assembly["name"],
        f"Physical identity: {assembly['id']}",
        f"Definition revision {assembly['revision_count']}: {assembly['revision_id']}",
        "Cutter design: " + (design["name"] if design else "Missing or unlinked"),
        "Holder: " + (assembly["holder"] or "Unknown"),
        "Locations are operator declarations. Measurements retain their original attribution.",
    ]

    def dimension(value):
        return "Unknown" if value is None else f"{value:.6g} mm"

    result["Geometry"] = [
        "Physical assembly · declared dimensions",
        "Stickout: " + dimension(assembly["stickout_mm"]),
        "Holder gauge length: Unknown",
    ]
    if design:
        result["Geometry"] += ["Linked cutter design · nominal dimensions", "Shape: " + design["shape"]]
        for title, key in (
            ("Cutting diameter", "diameter"),
            ("Shank diameter", "shank_diameter"),
            ("Overall length", "length"),
            ("Cutting length", "flute_length"),
            ("Corner radius", "corner_radius"),
            ("Thread pitch", "thread_pitch"),
        ):
            result["Geometry"].append(title + ": " + dimension(design.get(key)))
        length, stickout = design.get("length"), assembly["stickout_mm"]
        inserted = length - stickout if length is not None and stickout is not None and length >= stickout else None
        result["Geometry"].append("Inserted cutter length · derived from declarations: " + dimension(inserted))
    else:
        result["Geometry"].append("Cutter geometry unavailable; relink the saved design.")
    result["Geometry"].append("Qualified reach and clearance: Unknown; dimensions alone do not establish them.")
    result["Assets"] = [
        "Declared references · existence and content have not been checked by this view",
        "Physical holder CAD: " + (assembly.get("holder_geometry_path") or "Not supplied"),
    ]
    for title, key in (
        ("Cutter CAD", "geometry_path"),
        ("Manufacturer drawing", "drawing_path"),
        ("Manufacturer source", "source_url"),
        ("Vendor", "vendor"),
        ("Part number", "product_id"),
    ):
        result["Assets"].append(title + ": " + ((design or {}).get(key) or "Not supplied"))
    result["Assets"].append("Catalog holder/stickout examples are not inherited by the physical assembly.")
    links = {e["report_id"]: e for e in store.events if e["kind"] == "link" and e["assembly_id"] == assembly_id}
    reports = store.assembly_reports(assembly_id)
    result["Measurements"] = [f"{len(reports)} attributed calibration receipts · latest 10 shown"]
    for event in reversed(reports[-10:]):
        link, report = links[event["id"]], event["report"]
        revision = link.get("revision_id")
        association = (
            "Current definition"
            if revision == assembly["revision_id"]
            else "Older definition"
            if revision
            else "Unversioned"
        )
        result["Measurements"] += [
            f"{association} · receipt {event['id']} · revision {revision or 'Unknown'}",
            f"Source: {event['endpoint'] or 'Unknown'} · T{event['tool_number']} · timestamp {report['timestamp']}",
            "Raw samples: " + ", ".join(dimension(v) for v in report["measurements"]),
            "Spread: " + dimension(report["max_delta"]) + " · reported applied TLO: " + dimension(report["applied"]),
            "Attribution: " + link["note"],
        ]
    result["Measurements"].append(
        "Receipt attribution does not prove current seating, wear or applied controller offsets."
    )
    for (machine, slot), event in store.locations().items():
        if event["assembly_id"] == assembly_id:
            current = event.get("revision_id") == assembly["revision_id"]
            result["Locations"].append(
                f"{names.get(machine, machine)} / T{slot} · "
                + ("Current definition" if current else "Older or unversioned; reconcile")
            )
    if not result["Locations"]:
        result["Locations"].append("No declared location.")
    result["Locations"].append("Actual pocket and spindle identity: Unverified")
    result["Revisions"] = [f"{assembly['revision_count']} definitions · latest 10 shown"]
    for event in reversed(store.revisions(assembly_id)[-10:]):
        result["Revisions"] += [
            f"{event['id']} · timestamp {event['at']} · {event['name']}",
            f"Holder: {event['holder'] or 'Unknown'} · stickout: {dimension(event['stickout_mm'])}",
            "Reason: " + event.get("note", "Initial definition"),
        ]
    return result
