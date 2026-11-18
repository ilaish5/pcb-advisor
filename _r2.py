import sys,time
sys.path[:0]=["scripts","tests"]
import live_stm32_placed as pl
from altium import route
doc,box,rules=pl.load(sys.argv[1])
pn=route.pour_net_for(doc)
for i,(s,pr,sl,ge) in list(enumerate(route.STRATEGIES)):
    t=time.time()
    r=route._plan_routes_once(doc,box,rules,0.1,120,None,None,pn,None,first=(),sampling=s,spans_last=sl,ground_early=ge)
    print(i,len(r["routed"]),r["failed"],r["pairs"],round(time.time()-t,1),flush=True)
