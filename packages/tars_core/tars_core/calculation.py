"""One numerical owner for interactive calculations and background jobs."""
import math
import numpy as np
from . import SOLVER_VERSION,MODEL_VERSION,SOLVER_DIGEST
from .bodies import BODY_BY_ID,GM_SUN
from .mechanics.lambert import compute_transfer_dv
from .mechanics.multileg import _generate_leg_trajectory,compute_multileg_trajectory,multileg_result_to_dict
from .mechanics.kepler import compute_apsis_points,generate_full_orbit_points
from .mechanics.transforms import positions_to_scene,km_to_scene
from .time import iso_to_jd,jd_to_iso

def safe_value(value):
    if isinstance(value,dict):return {k:safe_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe_value(v) for v in value]
    if isinstance(value,np.ndarray):return safe_value(value.tolist())
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not math.isfinite(value):return None
    return value

def provenance(snapshot):
    import platform
    from importlib.metadata import version
    return {'dataset_id':snapshot.dataset_id,'solver_version':SOLVER_VERSION,'solver_digest':SOLVER_DIGEST,'model_version':MODEL_VERSION,'time_scale':'TDB','scene_scale_au':1000.0,'runtime':{'python':platform.python_version(),'architecture':platform.machine(),**{name:version(name) for name in ('numpy','scipy','numba','astropy')}}}

def lambert_result(request,snapshot):
    origin,target=int(request.origin),int(request.target)
    if origin==target:raise ValueError('Origin and target must differ')
    dep=iso_to_jd(request.departure_date);arr=dep+request.tof_days
    r1,v1=snapshot.get_state(origin,dep);r2,v2=snapshot.get_state(target,arr)
    result=compute_transfer_dv(r1,v1,r2,v2,request.tof_days*86400,GM_SUN)
    if not result['converged']:raise ValueError('No supported Lambert solution')
    points=_generate_leg_trajectory(r1,result['v1_transfer'],request.tof_days*86400,dep,GM_SUN,min(200,max(20,int(request.tof_days/2))))
    return safe_value({'origin':BODY_BY_ID[origin].name,'target':BODY_BY_ID[target].name,'departure_jd':dep,'arrival_jd':arr,'departure_iso':jd_to_iso(dep),'arrival_iso':jd_to_iso(arr),'tof_days':request.tof_days,'dv_departure_km_s':result['dv_departure'],'dv_arrival_km_s':result['dv_arrival'],'dv_total_km_s':result['dv_total'],'orbit_elements':result['orbit_elements'],'trajectory_points':points,'trajectory_epochs':[p['epoch_jd'] for p in points],**provenance(snapshot)})

def multileg_result(request,snapshot):
    result=compute_multileg_trajectory(request.body_sequence,iso_to_jd(request.departure_date),request.leg_tof_days,snapshot)
    if not all(leg.converged for leg in result.legs):raise ValueError('Infeasible trajectory leg')
    return safe_value({**multileg_result_to_dict(result),**provenance(snapshot)})

def orbit_result(request):
    i,raan,argp=map(math.radians,(request.i_deg,request.raan_deg,request.arg_p_deg))
    peri,apo=compute_apsis_points(request.a_km,request.e,i,raan,argp,request.mu)
    points=generate_full_orbit_points(request.a_km,request.e,i,raan,argp,request.mu)
    return safe_value({'periapsis_distance_km':request.a_km*(1-request.e),'apoapsis_distance_km':request.a_km*(1+request.e) if request.e<1 else None,'period_seconds':2*math.pi*math.sqrt(request.a_km**3/request.mu) if request.e<1 else None,'periapsis_point_km':peri,'apoapsis_point_km':apo if request.e<1 else None,'periapsis_point_scene':km_to_scene(peri),'apoapsis_point_scene':km_to_scene(apo) if request.e<1 else None,'full_orbit_points_scene':positions_to_scene(points),'solver_version':SOLVER_VERSION})
