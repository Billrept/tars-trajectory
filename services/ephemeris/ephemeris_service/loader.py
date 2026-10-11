import argparse,asyncio,json,os
from pathlib import Path
import numpy as np
from tars_contracts.horizons import fetch_state_vectors
from tars_core.bodies import ALL_BODIES
from tars_core.ephemeris import EphemerisSnapshot
from .app import create_store

async def ingest(store,start,end,step,fixtures=None):
    if fixtures:
        folder=Path(fixtures);bodies={}
        for name,bid in [('earth',399),('mars',499)]:
            with np.load(folder/f'{name}_horizons.npz',allow_pickle=False) as arrays:bodies[bid]=dict(arrays)
        provenance=json.loads((folder/'horizons_provenance.json').read_text())
        provenance.update({'required_bodies':[399,499],'query_time_type':'TDB (original fixture query default)'})
    else:
        bodies={}
        for body in ALL_BODIES:
            center=f'500@{body.parent_id}' if body.parent_id else '500@10'
            arrays=await fetch_state_vectors(body.horizons_id,start,end,step,center)
            if body.parent_id:
                parent=EphemerisSnapshot('parent',{body.parent_id:bodies[body.parent_id]})
                arrays['positions']+=parent.get_positions_batch(body.parent_id,arrays['epochs'])
                arrays['velocities']+=np.array([parent.get_velocity(body.parent_id,float(jd)) for jd in arrays['epochs']])
            bodies[body.naif_id]=arrays
        provenance={'source':'NASA JPL Horizons','required_bodies':[b.naif_id for b in ALL_BODIES],'start':start,'end':end,'step_days':step,'query_time_type':'UT converted to TDB','parent_conversion':'heliocentric','time_scale':'TDB'}
    return await asyncio.to_thread(store.publish,bodies,provenance)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixtures');parser.add_argument('--start',default=os.environ.get('EPHEMERIS_START','2025-01-01'));parser.add_argument('--end',default=os.environ.get('EPHEMERIS_END','2060-01-01'));parser.add_argument('--step',type=int,default=1)
    args=parser.parse_args();store=create_store()
    print('Published dataset',asyncio.run(ingest(store,args.start,args.end,args.step,args.fixtures)))

if __name__=='__main__':main()
