"""Feasibility: JLC part fields (lifecycle signal?) + datasheet download."""
import json, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
U = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def q(k):
    r = urllib.request.Request(U, data=json.dumps({"keyword": k, "currentPage": 1, "pageSize": 3,
                                                    "searchSource": "search"}).encode(),
                               headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(r, timeout=30))["data"]["componentPageInfo"]["list"][0]


for k in sys.argv[1:] or ["C45889", "C94355"]:
    c = q(k)
    print("==", k, c.get("componentModelEn"))
    for key, v in sorted(c.items()):
        if key in ("attributes", "componentPrices"):
            continue
        s = str(v)
        if v not in (None, "", [], {}) and len(s) < 160:
            print(f"   {key} = {s}")
    print("   attributes:", [(a.get("attribute_name_en"), a.get("attribute_value_name")) for a in (c.get("attributes") or [])])

url = q("C45889")["dataManualUrl"]
try:
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
    b = r.read()
    print("datasheet download:", r.status, r.headers.get("Content-Type"), len(b), b[:5])
except Exception as e:
    print("datasheet download FAILED:", e)
