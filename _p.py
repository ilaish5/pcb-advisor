import sys
sys.path[:0]=["scripts","tests"]
import live_stm32_placed as pl
doc,box,rules=pl.load("live_stm32_rebuilt")
print(doc["pads"][0])
for p in doc["pads"]:
    d=p["ref"]+"-"+p["name"]
    if d.startswith(("J1","R4","R3")): print(p)
