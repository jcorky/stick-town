import time, numpy as np
from scipy import ndimage
from plandscape.terrain.heightfield import generate_tile
from plandscape.paths.desire import simulate, obstacle_cost
from plandscape.fauna.agents import World, spawn, run
hf=generate_tile(size_m=128, province='piedmont', seed=2)
r=np.random.default_rng(0)
trees=np.c_[r.uniform(5,123,(60,2)), r.uniform(8,25,60), r.uniform(0.15,0.5,60)]
cost=obstacle_cost(hf, trunks=[(x,y,rd) for x,y,_,rd in trees])
F,_=simulate(hf,[(10,10,1),(115,20,1),(64,118,2)], n_trips=150, seed=1, cost=cost)
canopy=np.zeros_like(hf.z)
for x,y,h,rd in trees: canopy[int(y),int(x)]+=1
cover=np.clip(ndimage.gaussian_filter(canopy,4)*40,0,1); mast=cover*0.8
forage=np.clip(1-cover,0,1)*hf.layers['moisture']
w=World(hf,F,cost,cover,forage,mast,trees); w.attractors=[(10,10),(115,20),(64,118)]
ag=spawn(w,{'white_tailed_deer':4,'gray_squirrel':4,'wild_turkey':5,'armadillo':1,'coyote':1,'human':1},seed=3)
t=time.time(); run(w, ag, seconds=240, dt=0.25, start_hour=6.5); print('sim', round(time.time()-t,1),'s')
from collections import Counter
for a in ag:
    d=sum(np.hypot(a.log[i+1][1]-a.log[i][1],a.log[i+1][2]-a.log[i][2]) for i in range(len(a.log)-1))
    st=Counter(l[5] for l in a.log)
    print(f'{a.spec.key:18s} dist={d:6.1f}m ev={len(a.events):3d} states={dict(st.most_common(4))}')
print(Counter(s['type'] for s in w.signs))
