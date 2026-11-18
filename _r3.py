import sys,time
sys.path[:0]=["scripts","tests"]
import live_stm32_placed as pl
from altium import route
T=route.SAMPLING_TIGHT;S=route.SAMPLING
doc,box,rules=pl.load(sys.argv[1])
pn=route.pour_net_for(doc)
first=eval(sys.argv[2]) if len(sys.argv)>2 else ()
for (s,sl,ge) in [(T,True,True),(T,False,True),(S,True,True),(S,False,True),(S,True,False)]:
    t=time.time()
    r=route._plan_routes_once(doc,box,rules,0.1,120,None,None,pn,None,first=first,sampling=s,spans_last=sl,ground_early=ge)
    print(s,sl,ge,len(r["routed"]),r["failed"],round(time.time()-t,1),flush=True)
