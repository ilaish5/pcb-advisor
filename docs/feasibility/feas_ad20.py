"""Run the read-only parsers on AD20 course exercise files (another Altium version)."""
import struct, sys, collections, pathlib, olefile
sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(sys.argv[1])

def kv(txt):
    d = {}
    for part in txt.split("|"):
        if "=" in part:
            k, v = part.split("=", 1); d[k.upper()] = v
    return d

def text_records(blob, prefix=0):
    out, i = [], 0
    while i + prefix + 4 <= len(blob):
        i += prefix
        n = struct.unpack("<I", blob[i:i + 4])[0] & 0xFFFFFF
        out.append(kv(blob[i + 4:i + 4 + n].rstrip(b"\0").decode("latin-1"))); i += 4 + n
    return out

def pads(ole, nets, comps):
    blob = ole.openstream("Pads6/Data").read(); i, out = 0, []
    while i < len(blob):
        if blob[i] != 2: return out, f"bad type byte at {i}"
        i += 1; subs = []
        for _ in range(6):
            n = struct.unpack("<I", blob[i:i + 4])[0]; subs.append(blob[i + 4:i + 4 + n]); i += 4 + n
        s5 = subs[4]; net = struct.unpack("<H", s5[3:5])[0]; comp = struct.unpack("<H", s5[7:9])[0]
        out.append((comps[comp].get("SOURCEDESIGNATOR") if comp < len(comps) else None,
                    subs[0][1:1 + subs[0][0]].decode("latin-1"), nets[net]["NAME"] if net < len(nets) else None))
    return out, "ok"

for f in sorted(root.rglob("*.PcbDoc")):
    try:
        ole = olefile.OleFileIO(str(f))
        comps = text_records(ole.openstream("Components6/Data").read())
        nets = text_records(ole.openstream("Nets6/Data").read())
        rules = text_records(ole.openstream("Rules6/Data").read(), prefix=2)
        p, st = pads(ole, nets, comps)
        withnet = sum(1 for x in p if x[2])
        print(f"PCB {f.parent.name[:28]:28} {f.name[:26]:26} comps={len(comps):3} nets={len(nets):3} rules={len(rules):3} "
              f"kinds_ok={all(r.get('RULEKIND') for r in rules)} pads={len(p)} net={withnet} {st}")
    except Exception as e:
        print("PCB FAIL", f.name, e)

seen = set()
for f in sorted(root.rglob("*.SchDoc")):
    try:
        ole = olefile.OleFileIO(str(f))
        recs = []
        blob = ole.openstream("FileHeader").read(); i = 0
        while i + 4 <= len(blob):
            n = struct.unpack("<I", blob[i:i + 4])[0]; flag = n >> 24; n &= 0xFFFFFF
            if not flag: recs.append(kv(blob[i + 4:i + 4 + n].rstrip(b"\0").decode("latin-1", "replace")))
            i += 4 + n
        c = collections.Counter(r.get("RECORD") for r in recs)
        key = (f.name, c["1"], c["2"])
        if key in seen: continue
        seen.add(key)
        print(f"SCH {f.parent.name[:28]:28} {f.name[:26]:26} comps={c['1']:3} pins={c['2']:4} wires={c['27']:4} labels={c['25']+c['17']:3} parse_end={i == len(blob)}")
    except Exception as e:
        print("SCH FAIL", f.name, e)
