"""Read-only readers for Altium library files (text is Windows ANSI, cp1252: an en-dash or a curly quote reads back as written): SchLib (symbols) and PcbLib (footprints with their 3D bodies).

What the library builder (bridge.build_library) checks after Altium has written the files: the files are read back
here, not trusted from Altium's log. Units: schematic coordinates are returned in mils, PCB coordinates in mils.
"""
import pathlib
import re
import struct

from .ole import AltiumReadError, kv, open_doc, stream

PIN_TYPES = {0: "Input", 1: "IO", 2: "Output", 3: "OpenCollector", 4: "Passive", 5: "HiZ", 6: "OpenEmitter", 7: "Power"}
MIL = 10000.0            # PCB internal unit per mil


def _pascal(blob, i):
    n = blob[i]
    return blob[i + 1:i + 1 + n].decode("cp1252", "replace"), i + 1 + n


def _records(blob):
    """[(flag, bytes)] of a SchLib component's Data stream (flag 1 = a binary record, a pin)."""
    out, i = [], 0
    while i + 4 <= len(blob):
        n = struct.unpack("<I", blob[i:i + 4])[0]
        flag, n = n >> 24, n & 0xFFFFFF
        out.append((flag, blob[i + 4:i + 4 + n]))
        i += 4 + n
    return out


def _binary_pin(body):
    """A binary pin record (RECORD 2): see the Altium file format notes; None if it is not one."""
    if len(body) < 24 or struct.unpack("<i", body[:4])[0] != 2:
        return None
    owner = struct.unpack("<h", body[5:7])[0]
    i = 12                                  # past: type(4) unknown(1) owner(2) display mode(1) 4 symbol bytes
    _, i = _pascal(body, i)                 # description
    formal, electrical, conglomerate = body[i], body[i + 1], body[i + 2]
    length, x, y = struct.unpack("<hhh", body[i + 3:i + 9])
    i += 13                                 # + colour (4)
    name, i = _pascal(body, i)
    number, i = _pascal(body, i)
    return {"number": number, "name": name, "electrical": PIN_TYPES.get(electrical, str(electrical)),
            "x": x * 10, "y": y * 10, "length": length * 10, "orientation": conglomerate & 3,
            "conglomerate": conglomerate, "show_name": bool(conglomerate & 0x08), "show_number": bool(conglomerate & 0x10),
            "part_id": owner, "formal": formal}


def read_schlib(path):
    """{"file", "symbols": [{name, description, designator, comment, params, pins, footprints, pinned_paths}]}"""
    p = pathlib.Path(path)
    symbols = []
    with open_doc(p) as ole:
        for entry in ole.listdir(streams=True, storages=False):
            if len(entry) != 2 or entry[1] != "Data":
                continue
            recs = _records(stream(ole, "/".join(entry)))
            text = [(i, kv(b.rstrip(b"\0").decode("cp1252", "replace"))) for i, (f, b) in enumerate(recs) if not f]
            comp = next((r for _, r in text if r.get("RECORD") == "1"), None)
            if comp is None:
                continue
            pins = [pn for f, b in recs if f and (pn := _binary_pin(b))]
            pins += [{"number": r.get("DESIGNATOR", ""), "name": r.get("NAME", ""), "electrical": PIN_TYPES.get(int(r.get("ELECTRICAL", "0")), "?"),
                      "x": int(r.get("LOCATION.X", "0")) * 10, "y": int(r.get("LOCATION.Y", "0")) * 10,
                      "length": int(r.get("PINLENGTH", "0")) * 10, "orientation": int(r.get("PINCONGLOMERATE", "0")) & 3,
                      "conglomerate": int(r.get("PINCONGLOMERATE", "0")), "show_name": bool(int(r.get("PINCONGLOMERATE", "0")) & 8),
                      "show_number": bool(int(r.get("PINCONGLOMERATE", "0")) & 16), "part_id": int(r.get("OWNERPARTID", "1"))}
                     for _, r in text if r.get("RECORD") == "2"]
            params = {r["NAME"]: r.get("TEXT", "") for _, r in text if r.get("RECORD") == "41" and r.get("NAME")}
            des = next((r.get("TEXT", "") for _, r in text if r.get("RECORD") == "34"), "")
            impls = [r for _, r in text if r.get("RECORD") == "45" and r.get("MODELTYPE", "").upper() == "PCBLIB"]
            symbols.append({
                "name": comp.get("LIBREFERENCE", entry[0]),
                "description": comp.get("COMPONENTDESCRIPTION", ""),
                "designator": des,
                "comment": params.get("Comment", ""),
                "params": params,
                "pins": pins,
                "footprints": [r.get("MODELNAME", "") for r in impls],
                "pinned_paths": [r["MODELDATAFILE0"] for r in impls if r.get("MODELDATAFILE0")],
                "graphics": sum(1 for _, r in text if r.get("RECORD") in ("3", "4", "5", "6", "7", "8", "10", "11", "12", "13", "14")),
            })
    return {"file": str(p), "symbols": sorted(symbols, key=lambda s: s["name"])}


def _blocks(d, i, n):
    out = []
    for _ in range(n):
        size = struct.unpack("<I", d[i:i + 4])[0] & 0xFFFFFF
        out.append(d[i + 4:i + 4 + size])
        i += 4 + size
    return out, i


def _footprint_objects(d):
    """Walk a footprint's Data stream: {"pads", "tracks", "arcs", "regions", "texts", "fills", "vias", "bodies"}."""
    res = {"pads": [], "tracks": 0, "arcs": 0, "regions": 0, "texts": 0, "fills": 0, "vias": 0, "bodies": [], "layers": {}}
    n = struct.unpack("<I", d[:4])[0]
    i = 4 + n
    while i < len(d):
        kind = d[i]
        i += 1
        if kind == 2:                                   # pad: name, 0, "|&|0", 0, geometry, size and shape
            (name, _, _, _, geo, _), i = _blocks(d, i, 6)
            pad = {"name": name[1:1 + name[0]].decode("cp1252", "replace") if name else "", "layer": geo[0]}
            if len(geo) >= 60:
                x, y, xs, ys = struct.unpack("<iiii", geo[13:29])
                pad.update({"x": x / MIL, "y": y / MIL, "xsize": xs / MIL, "ysize": ys / MIL,
                            "hole": struct.unpack("<i", geo[45:49])[0] / MIL,
                            "rotation": round(struct.unpack("<d", geo[52:60])[0], 3)})
            res["pads"].append(pad)
        elif kind in (1, 3, 4, 6, 11, 12):
            (blk,), i = _blocks(d, i, 1)
            if kind in (1, 4, 6, 11) and blk:
                res["layers"][blk[0]] = res["layers"].get(blk[0], 0) + 1
            if kind == 4:
                res["tracks"] += 1
            elif kind == 1:
                res["arcs"] += 1
            elif kind == 11:
                res["regions"] += 1
            elif kind == 6:
                res["fills"] += 1
            elif kind == 3:
                res["vias"] += 1
            else:
                text = blk.decode("cp1252", "replace")
                props = kv(text[text.find("|"):].split("\0")[0] if "|" in text else "")
                res["bodies"].append({"model": props.get("MODEL.NAME", ""), "id": props.get("MODELID", ""),
                                      "standoff": props.get("STANDOFFHEIGHT", ""), "height": props.get("OVERALLHEIGHT", ""),
                                      "rot": [props.get("MODEL.3D.ROTX", ""), props.get("MODEL.3D.ROTY", ""), props.get("MODEL.3D.ROTZ", "")],
                                      "dz": props.get("MODEL.3D.DZ", "")})
        elif kind == 5:                                  # text: properties block + the string block
            _, i = _blocks(d, i, 2)
            res["texts"] += 1
        else:
            raise AltiumReadError("<pcblib>", f"unknown object type {kind} in a footprint")
    return res


def read_pcblib(path):
    """{"file", "footprints": [{name, description, pads, tracks, ..., bodies}], "models": [name]}"""
    p = pathlib.Path(path)
    fps, models = [], []
    with open_doc(p) as ole:
        for entry in ole.listdir(streams=True, storages=False):
            if len(entry) == 2 and entry[1] == "Parameters":
                par = kv(stream(ole, "/".join(entry)).decode("cp1252", "replace"))
                if "PATTERN" not in par:
                    continue
                data = stream(ole, f"{entry[0]}/Data") if ole.exists(f"{entry[0]}/Data") else b""
                try:
                    objs = _footprint_objects(data) if data else {}
                except (struct.error, IndexError, AltiumReadError) as exc:
                    raise AltiumReadError(str(p), f"footprint {par['PATTERN']} could not be read: {exc}") from exc
                fps.append({"name": par["PATTERN"], "description": par.get("DESCRIPTION", ""), **objs})
        if ole.exists("Library/Models/Data"):
            blob = stream(ole, "Library/Models/Data")
            i = 0
            while i + 4 <= len(blob):
                n = struct.unpack("<I", blob[i:i + 4])[0] & 0xFFFFFF
                m = re.search(r"\|NAME=([^|\0]*)", blob[i + 4:i + 4 + n].decode("cp1252", "replace"))
                models.append(m.group(1) if m else "")
                i += 4 + n
    return {"file": str(p), "footprints": sorted(fps, key=lambda f: f["name"]), "models": models}
