"""Feasibility: rules and pad->net map from a PcbDoc, read-only."""
import os, sys, struct, olefile, collections, pathlib

PROJECT = os.environ.get("PROJECT_DIR") or (sys.argv[1] if len(sys.argv) > 1 else None)
assert PROJECT, "usage: PROJECT_DIR=<folder with the .PcbDoc / .RUL> python this_script.py"
P = pathlib.Path(PROJECT)
ole = olefile.OleFileIO(str(P))


def kv(txt):
    d = {}
    for part in txt.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.upper()] = v
    return d


def text_records(blob, prefix=0):
    out, i = [], 0
    while i + prefix + 4 <= len(blob):
        i += prefix
        n = struct.unpack("<I", blob[i:i + 4])[0]
        out.append(kv(blob[i + 4:i + 4 + n].rstrip(b"\0").decode("latin-1")))
        i += 4 + n
    return out


comps = text_records(ole.openstream("Components6/Data").read())
nets = text_records(ole.openstream("Nets6/Data").read())
rules = text_records(ole.openstream("Rules6/Data").read(), prefix=2)
print("rules:", len(rules))
print("kinds:", dict(collections.Counter(r.get("RULEKIND") for r in rules)))
for r in rules:
    if r.get("RULEKIND") == "Width":
        print("  width", r.get("NAME"), r.get("MINLIMIT"), r.get("PREFEREDWIDTH") or r.get("PREFERREDWIDTH"), r.get("MAXLIMIT"), "|", r.get("SCOPE1EXPRESSION")[:60])

# pads: type byte 2, then subrecords [u32 len][data]
blob = ole.openstream("Pads6/Data").read()
i, pads = 0, []
while i < len(blob):
    assert blob[i] == 2, (i, blob[i])
    i += 1
    subs = []
    for _ in range(6):
        n = struct.unpack("<I", blob[i:i + 4])[0]
        subs.append(blob[i + 4:i + 4 + n])
        i += 4 + n
    name = subs[0][1:1 + subs[0][0]].decode("latin-1")
    s5 = subs[4]
    layer = s5[0]
    net = struct.unpack("<H", s5[3:5])[0]
    comp = struct.unpack("<H", s5[7:9])[0]
    x, y = struct.unpack("<ii", s5[13:21])
    sx, sy = struct.unpack("<ii", s5[21:29])
    pads.append(dict(name=name, layer=layer, net=nets[net]["NAME"] if net < len(nets) else None,
                     ref=comps[comp]["SOURCEDESIGNATOR"] if comp < len(comps) else None,
                     x=x / 10000 * 0.0254, y=y / 10000 * 0.0254, sx=sx / 10000 * 0.0254, sy=sy / 10000 * 0.0254))
print("pads:", len(pads), "with net:", sum(1 for p in pads if p["net"]))
for ref in ("U3", "J1"):
    print(ref, sorted((p["name"], p["net"]) for p in pads if p["ref"] == ref)[:14])
fault = sorted(f'{p["ref"]}-{p["name"]}' for p in pads if p["net"] == "TC_FAULT")
print("TC_FAULT:", fault)
u4 = [p for p in pads if p["ref"] == "U4" and p["name"] == "1"]
print("U4-1 size mm:", [(round(p["sx"], 3), round(p["sy"], 3)) for p in u4])
