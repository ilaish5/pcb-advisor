"""Read Altium SchDoc schematic files (Protel 5.0 binary format).

Coordinates are integer LOCATION.X / LOCATION.Y as stored in Altium units
of 10 mil (ignoring *_FRAC fractional fields). Records come from the FileHeader
stream. The first text record is the sheet header; OWNERINDEX of child records
refers to the 0-based index of the owner among records after the sheet header.
"""
import collections
import pathlib

from .ole import AltiumReadError, open_doc, stream, text_records


def read_schdoc(path) -> dict:
    """Read an Altium .SchDoc file into a structured dictionary."""
    p = pathlib.Path(path)
    with open_doc(p) as ole:
        blob = stream(ole, "FileHeader")

    recs = text_records(blob, prefix=0)
    if not recs:
        raise AltiumReadError(str(p), "empty or unreadable FileHeader stream")

    # First record is the sheet header; records after it form the body
    body = recs[1:]

    # Index children by their string OWNERINDEX
    children_by_owner: dict[str, list[tuple[int, dict[str, str]]]] = collections.defaultdict(list)
    for idx, r in enumerate(body):
        owner = r.get("OWNERINDEX")
        if owner is not None:
            children_by_owner[owner].append((idx, r))

    components = []
    wires = []
    net_labels = []
    power_ports = []
    ports = []
    junctions = []

    for idx, r in enumerate(body):
        rec_kind = r.get("RECORD")
        if rec_kind == "1":
            # Component
            children = children_by_owner.get(str(idx), [])

            # Designator (RECORD=34)
            des_recs = [cr for _, cr in children if cr.get("RECORD") == "34"]
            ref = des_recs[0].get("TEXT", "") if des_recs else r.get("SOURCEDESIGNATOR", "")

            # Parameters (RECORD=41)
            params = {cr.get("NAME"): cr.get("TEXT", "") for _, cr in children if cr.get("RECORD") == "41" and cr.get("NAME")}

            comment = params.get("Comment") or r.get("COMMENT", "")
            description = r.get("COMPONENTDESCRIPTION") or r.get("DESCRIPTION") or params.get("Description", "")
            lib_ref = r.get("LIBREFERENCE") or r.get("DESIGNITEMID", "")

            # Footprint from RECORD=45 MODELNAME where MODELTYPE=PCBLIB, owned via RECORD=44
            rec44_indices = [c_idx for c_idx, cr in children if cr.get("RECORD") == "44"]
            cand_pcb = []
            for r44_i in rec44_indices:
                for _, sub in children_by_owner.get(str(r44_i), []):
                    if sub.get("RECORD") == "45" and sub.get("MODELTYPE") == "PCBLIB":
                        cand_pcb.append(sub)
            current_pcb = [c.get("MODELNAME", "") for c in cand_pcb if c.get("ISCURRENT") == "T"]
            footprint = current_pcb[0] if current_pcb else (cand_pcb[0].get("MODELNAME", "") if cand_pcb else "")

            # Pins owned by this component (RECORD=2)
            pin_recs = [cr for _, cr in children if cr.get("RECORD") == "2"]
            pins = []
            for pin in pin_recs:
                pins.append({
                    "number": pin.get("DESIGNATOR", ""),
                    "name": pin.get("NAME", ""),
                    "electrical": int(pin.get("ELECTRICAL", "0")),
                    "x": int(pin.get("LOCATION.X", "0")),
                    "y": int(pin.get("LOCATION.Y", "0")),
                    "length": int(pin.get("PINLENGTH", "0")),
                    "orientation": int(pin.get("PINCONGLOMERATE", "0")) & 3,
                    "part_id": int(pin.get("OWNERPARTID", "1")),
                })

            components.append({
                "ref": ref,
                "lib_ref": lib_ref,
                "comment": comment,
                "description": description,
                "footprint": footprint,
                "params": params,
                "part_count": int(r.get("PARTCOUNT", "1")),
                "current_part_id": int(r.get("CURRENTPARTID", "1")),
                "x": int(r.get("LOCATION.X", "0")),
                "y": int(r.get("LOCATION.Y", "0")),
                "pins": pins,
            })

        elif rec_kind == "27":
            # Wire
            n_pts = int(r.get("LOCATIONCOUNT", "0"))
            pts = [(int(r.get(f"X{j}", "0")), int(r.get(f"Y{j}", "0"))) for j in range(1, n_pts + 1)]
            wires.append({"points": pts})

        elif rec_kind == "25":
            # Net label
            text = r.get("TEXT", "")
            net_labels.append({
                "text": text,
                "name": text,
                "x": int(r.get("LOCATION.X", "0")),
                "y": int(r.get("LOCATION.Y", "0")),
            })

        elif rec_kind == "17":
            # Power port
            text = r.get("TEXT", "")
            power_ports.append({
                "text": text,
                "name": text,
                "x": int(r.get("LOCATION.X", "0")),
                "y": int(r.get("LOCATION.Y", "0")),
                "style": int(r.get("STYLE", "0")),
            })

        elif rec_kind == "18":
            # Port
            name = r.get("NAME") or r.get("TEXT", "")
            ports.append({
                "name": name,
                "text": name,
                "x": int(r.get("LOCATION.X", "0")),
                "y": int(r.get("LOCATION.Y", "0")),
                "io_type": int(r.get("IOTYPE", "0")),
            })

        elif rec_kind == "29":
            # Junction
            junctions.append({
                "x": int(r.get("LOCATION.X", "0")),
                "y": int(r.get("LOCATION.Y", "0")),
            })

    record_counts = {k: v for k, v in collections.Counter(r.get("RECORD") for r in body).items() if k is not None}

    return {
        "file": p.name,
        "components": components,
        "wires": wires,
        "net_labels": net_labels,
        "power_ports": power_ports,
        "ports": ports,
        "junctions": junctions,
        "record_counts": record_counts,
    }
