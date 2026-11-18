import sys,time
sys.path[:0]=["scripts","tests"]
import live_stm32_placed as pl
from altium import route
T=route.SAMPLING_TIGHT;S=route.SAMPLING
doc,box,rules=pl.load(sys.argv[1])
pn=route.pour_net_for(doc)
route.STRATEGIES=route.STRATEGIES+((T,True,True,True),(S,True,True,True),(T,True,False,True),(S,True,False,True))
t=time.process_time()
orig=route._plan_routes_once
def wrap(*a,**k):
    t0=time.process_time(); r=orig(*a,**k); print(k["sampling"],k["spans_last"],k["ground_early"],k["first"],len(r["routed"]),[f[0] for f in r["failed"]],round(time.process_time()-t0,1),flush=True); return r
route._plan_routes_once=wrap
res=route.plan_routes(doc,box,rules,pitch=0.1,seconds=1000,pour_net=pn)
print(len(res["routed"]),res["failed"],time.process_time()-t)
