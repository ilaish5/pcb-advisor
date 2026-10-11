"""Feasibility: read Altium SchDoc / PcbDoc straight from disk, read-only."""
import sys, re, struct, olefile, collections, pathlib

P = pathlib.Path(r"C:\Users\Public\Documents\Altium\real-project")


def records(blob):
    """Altium text records: [len:4][|KEY=VAL|...]\0"""
    out, i = [], 0
    while i + 4 <= len(blob):
        n = struct.unpack("<I", blob[i:i + 4])[0]
        flag = n >> 24
        n &= 0xFFFFFF
        body = blob[i + 4:i + 4 + n]
        i += 4 + n
        if flag:            # binary record
            out.append(("BIN", body))
            continue
        txt = body.rstrip(b"\0").decode("latin-1", "replace")
        d = {}
        for part in txt.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                d[k.upper()] = v
        out.append(("TXT", d))
    return out


print("=== SchDoc")
for sch in sorted(P.glob("0*.SchDoc")):
    ole = olefile.OleFileIO(str(sch))
    recs = [d for t, d in records(ole.openstream("FileHeader").read()) if t == "TXT"]
    kinds = collections.Counter(d.get("RECORD") for d in recs)
    comps = [d for d in recs if d.get("RECORD") == "1"]
    pins = [d for d in recs if d.get("RECORD") == "2"]
    designators = [d for d in recs if d.get("RECORD") == "34"]
    wires = [d for d in recs if d.get("RECORD") == "27"]
    labels = [d for d in recs if d.get("RECORD") in ("25", "17")]   # net label, power port
    print(f"{sch.name}: records={len(recs)} components={len(comps)} pins={len(pins)} "
          f"designators={len(designators)} wires={len(wires)} netlabels/ports={len(labels)}")
    ex = [d.get("TEXT") for d in designators][:8]
    print("   designators e.g.", ex)
    params = [d for d in recs if d.get("RECORD") == "41" and d.get("NAME", "").lower() in ("comment", "mpn", "lcsc")]
    print("   params e.g.", [(d.get("NAME"), d.get("TEXT")) for d in params[:5]])
    ole.close()

print("\n=== PcbDoc")
ole = olefile.OleFileIO(str(P / "real-project.PcbDoc"))
streams = ["/".join(s) for s in ole.listdir()]
print("storages:", sorted({s.split("/")[0] for s in streams})[:60])

def txt(stream):
    return [d for t, d in records(ole.openstream(stream).read()) if t == "TXT"]

comps = txt("Components6/Data")
print("components:", len(comps), "e.g.", [(c.get("SOURCEDESIGNATOR"), c.get("X"), c.get("Y"), c.get("ROTATION"), c.get("LAYER"), c.get("PATTERN")) for c in comps[:3]])
nets = txt("Nets6/Data")
print("nets:", len(nets), "e.g.", [n.get("NAME") for n in nets[:6]])
rules = txt("Rules6/Data")
print("rules:", len(rules))
for r in rules[:3]:
    print("   ", {k: r[k] for k in list(r)[:12]})
kinds = collections.Counter(r.get("RULEKIND") for r in rules)
print("rule kinds:", dict(kinds))
cls = txt("Classes6/Data")
print("classes:", len(cls))
board = txt("Board6/Data")
print("board6 keys sample:", list(board[0])[:15] if board else None)
pads_blob = ole.openstream("Pads6/Data").read()
print("Pads6 bytes:", len(pads_blob))
ole.close()
