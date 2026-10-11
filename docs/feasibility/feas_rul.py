"""Compare an exported .RUL with Rules6 inside the PcbDoc."""
import struct, sys, collections, olefile
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\Public\Documents\Altium\real-project"

def kv(txt):
    d = {}
    for part in txt.split("|"):
        if "=" in part:
            k, v = part.split("=", 1); d[k.upper()] = v
    return d

raw = open(ROOT + r"\real-project-RULES.RUL", "rb").read()
lines = raw.split(b"\r\n")
print("lines:", len(lines), "last line len:", len(lines[-1]))
print("line ending bytes:", sorted({l[-1:] for l in lines if l}))
rul = [kv(l.rstrip(b"\0\x00").decode("latin-1")) for l in lines if l.strip()]

ole = olefile.OleFileIO(ROOT + r"\real-project.PcbDoc")
blob = ole.openstream("Rules6/Data").read(); i, pcb = 0, []
while i + 6 <= len(blob):
    i += 2; n = struct.unpack("<I", blob[i:i + 4])[0]
    pcb.append(kv(blob[i + 4:i + 4 + n].rstrip(b"\0").decode("latin-1"))); i += 4 + n

print("rules in RUL:", len(rul), "in PcbDoc:", len(pcb))
A = {r["NAME"]: r for r in rul}; B = {r["NAME"]: r for r in pcb}
print("only in PcbDoc:", sorted(set(B) - set(A))); print("only in RUL:", sorted(set(A) - set(B)))
diffs = collections.Counter()
for n in set(A) & set(B):
    for k in set(A[n]) | set(B[n]):
        if A[n].get(k) != B[n].get(k):
            diffs[k] += 1
            if diffs[k] <= 2: print(f"  diff {n}.{k}: RUL={A[n].get(k)!r:.60} PCB={B[n].get(k)!r:.60}")
print("differing keys:", dict(diffs))
print("kinds:", dict(collections.Counter(r.get("RULEKIND") for r in rul)))
