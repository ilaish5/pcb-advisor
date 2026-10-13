"""Read Altium SchDoc schematic files (Protel 5.0 binary format).

Coordinates are LOCATION.X / LOCATION.Y in Altium units of 10 mil. The *_FRAC
fields (1/100000 unit) are added: a value within 0.02 unit of a whole number
becomes an int (Altium writes 129 + 0.9921 for a point it means as 130), so
pins, wires and labels that meet on the grid share one coordinate; real
half-grid values stay floats. Records come from the FileHeader stream. The first
text record is the sheet header; OWNERINDEX of child records refers to the
0-based index of the owner among records after the sheet header.
"""
import collections
import pathlib

from .ole import AltiumReadError, open_doc, stream, text_records


def _num(r: dict, key: str, default: int = 0):
    """r[key] + r[key_FRAC] / 1e5, snapped to an int when within 0.02 of a whole number."""
    try:
        v = int(r.get(key, default))
        frac = r.get(key + "_FRAC")
        if frac:
            v += int(frac) / 100000.0
    except ValueError:
        return default
    nearest = round(v)
    return int(nearest) if abs(v - nearest) < 0.02 else round(v, 3)


def _flag(r: dict, key: str) -> bool:
    return r.get(key, "").upper() == "T"


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
    no_erc = []

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
                    "x": _num(pin, "LOCATION.X"),
                    "y": _num(pin, "LOCATION.Y"),
                    "length": _num(pin, "PINLENGTH"),
                    # PINCONGLOMERATE: bits 0-1 rotation (component rotation/mirror already
                    # applied, the pin's own X/Y are sheet coordinates), bit 2 = hidden pin
                    "orientation": int(pin.get("PINCONGLOMERATE", "0")) & 3,
                    "hidden": bool(int(pin.get("PINCONGLOMERATE", "0")) & 4),
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
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
                "orientation": int(r.get("ORIENTATION", "0")) & 3,
                "mirrored": _flag(r, "ISMIRRORED"),
                "pins": pins,
            })

        elif rec_kind == "27":
            # Wire
            n_pts = int(r.get("LOCATIONCOUNT", "0"))
            pts = [(_num(r, f"X{j}"), _num(r, f"Y{j}")) for j in range(1, n_pts + 1)]
            wires.append({"points": pts})

        elif rec_kind == "25":
            # Net label
            text = r.get("TEXT", "")
            net_labels.append({
                "text": text,
                "name": text,
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
            })

        elif rec_kind == "17":
            # Power port
            text = r.get("TEXT", "")
            power_ports.append({
                "text": text,
                "name": text,
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
                "style": int(r.get("STYLE", "0")),
            })

        elif rec_kind == "18":
            # Port
            name = r.get("NAME") or r.get("TEXT", "")
            ports.append({
                "name": name,
                "text": name,
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
                "width": _num(r, "WIDTH"),
                # STYLE 0-3 horizontal, 4-7 vertical (Altium port styles)
                "vertical": int(r.get("STYLE", "0")) >= 4,
                "io_type": int(r.get("IOTYPE", "0")),
            })

        elif rec_kind == "29":
            # Junction
            junctions.append({
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
            })

        elif rec_kind == "22":
            # No ERC marker: the object under it is intentionally left as it is (unconnected pin)
            no_erc.append({
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
                # Altium writes booleans only when true: no ISACTIVE=T means a disabled marker
                "active": _flag(r, "ISACTIVE"),
                "symbol": r.get("SYMBOL", ""),
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
        "no_erc": no_erc,
        "record_counts": record_counts,
    }
