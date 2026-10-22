"""Read Altium SchDoc schematic files (Protel 5.0 binary format).

Coordinates are LOCATION.X / LOCATION.Y in Altium units of 10 mil. The *_FRAC
fields (1/100000 unit) are added: a value within 0.02 unit of a whole number
becomes an int (Altium writes 129 + 0.9921 for a point it means as 130), so
pins, wires and labels that meet on the grid share one coordinate; real
half-grid values stay floats. Records come from the FileHeader stream. The first
text record is the sheet header; OWNERINDEX of child records refers to the
0-based index of the owner among records after the sheet header.

What the picture needs to match Altium is read too: a pin's LOCATION is the end that
meets the symbol body and its connection point (hot spot) is PINLENGTH away from it,
in the pin's direction; PINCONGLOMERATE also says whether the name and the number are
shown. A component keeps its body drawing (rectangles, lines, polylines, polygons, arcs,
text) and where the designator and the comment sit (location, justification, font); the
sheet header's font table is returned as "fonts".
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


# Direction a pin points in from the body to its connection point, per rotation (0 right, 1 up, 2 left, 3 down)
PIN_DIRECTION = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}


def pin_tip(pin: dict):
    """The connection point (hot spot) of a pin: PINLENGTH from its location, in its direction."""
    dx, dy = PIN_DIRECTION[pin.get("orientation", 0) & 3]
    length = pin.get("length", 0)
    return (pin.get("x", 0) + dx * length, pin.get("y", 0) + dy * length)


def _points(r: dict) -> list:
    return [(_num(r, f"X{j}"), _num(r, f"Y{j}")) for j in range(1, int(r.get("LOCATIONCOUNT", "0")) + 1)]


def _text(r: dict) -> dict:
    """A text record (designator, parameter, label): the text, its anchor, justification (0 bottom-left, 1 bottom-centre,
    2 bottom-right, 3-5 the same on the centre line, 6-8 on the top line), rotation (quarter turns, anticlockwise), font id."""
    return {
        "text": r.get("TEXT", ""),
        "x": _num(r, "LOCATION.X"),
        "y": _num(r, "LOCATION.Y"),
        "justification": int(r.get("JUSTIFICATION", "0")) % 9,
        "orientation": int(r.get("ORIENTATION", "0")) & 3,
        "font": int(r.get("FONTID", "1")),
        "hidden": _flag(r, "ISHIDDEN"),
    }


def _graphic(r: dict):
    """One drawing primitive of a component body (rectangle, line, polyline, polygon, arc, text), or None."""
    kind = r.get("RECORD")
    g = {"part_id": int(r.get("OWNERPARTID", "1"))}
    if kind in ("14", "10"):
        g.update(kind="rect", x1=_num(r, "LOCATION.X"), y1=_num(r, "LOCATION.Y"), x2=_num(r, "CORNER.X"), y2=_num(r, "CORNER.Y"),
                 solid=_flag(r, "ISSOLID"))
    elif kind == "13":
        g.update(kind="polyline", points=[(_num(r, "LOCATION.X"), _num(r, "LOCATION.Y")), (_num(r, "CORNER.X"), _num(r, "CORNER.Y"))])
    elif kind == "6":
        g.update(kind="polyline", points=_points(r))
    elif kind == "7":
        g.update(kind="polygon", points=_points(r), solid=_flag(r, "ISSOLID"))
    elif kind == "12":
        g.update(kind="arc", x=_num(r, "LOCATION.X"), y=_num(r, "LOCATION.Y"), radius=_num(r, "RADIUS"),
                 start=float(r.get("STARTANGLE", "0")), end=float(r.get("ENDANGLE", "360")))
    elif kind == "4":
        g.update(kind="text", **_text(r))
    else:
        return None
    return g


def _fonts(sheet: dict) -> dict:
    """The sheet header's font table: id -> size, name, bold, italic."""
    out = {}
    for i in range(1, int(sheet.get("FONTIDCOUNT", "0")) + 1):
        out[i] = {"size": int(sheet.get(f"SIZE{i}", "10")), "name": sheet.get(f"FONTNAME{i}", ""),
                  "bold": _flag(sheet, f"BOLD{i}"), "italic": _flag(sheet, f"ITALIC{i}")}
    return out


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
            # the Comment parameter (RECORD=41), drawn where the designer put it unless ISHIDDEN
            comment_recs = [cr for _, cr in children if cr.get("RECORD") == "41" and cr.get("NAME") == "Comment"]

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
                    # bits 3 and 4: the name and the number are drawn
                    "show_name": bool(int(pin.get("PINCONGLOMERATE", "0")) & 8),
                    "show_number": bool(int(pin.get("PINCONGLOMERATE", "0")) & 16),
                    "part_id": int(pin.get("OWNERPARTID", "1")),
                })

            components.append({
                "ref": ref,
                "unique_id": r.get("UNIQUEID", ""),
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
                "graphics": [g for g in (_graphic(cr) for _, cr in children) if g],
                "designator_text": _text(des_recs[0]) if des_recs else None,
                "comment_text": _text(comment_recs[0]) if comment_recs else None,
            })

        elif rec_kind == "27":
            # Wire
            wires.append({"points": _points(r)})

        elif rec_kind == "25":
            # Net label
            text = r.get("TEXT", "")
            net_labels.append({
                "text": text,
                "name": text,
                "x": _num(r, "LOCATION.X"),
                "y": _num(r, "LOCATION.Y"),
                "orientation": int(r.get("ORIENTATION", "0")) & 3,
                "font": int(r.get("FONTID", "1")),
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
                # the way the symbol points from the connection point (0 right, 1 up, 2 left, 3 down)
                "orientation": int(r.get("ORIENTATION", "0")) & 3,
                "show_name": _flag(r, "SHOWNETNAME"),
                "font": int(r.get("FONTID", "1")),
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
        "fonts": _fonts(recs[1]) if len(recs) > 1 else {},
        "system_font": int(recs[1].get("SYSTEMFONT", "1")) if len(recs) > 1 else 1,
        "record_counts": record_counts,
    }
