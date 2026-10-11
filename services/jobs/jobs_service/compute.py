"""CPU-only execution in a child process, using one pinned local snapshot."""
from dataclasses import asdict
import numpy as np
from tars_contracts.requests import REQUEST_MODELS,LambertRequest,MultiLegRequest
from tars_core.bodies import BODY_BY_ID
from tars_core.calculation import lambert_result,multileg_result,safe_value,provenance
from tars_core.time import iso_to_jd,jd_to_iso
from tars_core.optimizer.types import OptimizationRequest,MultiLegOptimizationRequest
from tars_core.optimizer.nsga2 import NSGA2Optimizer,MultiLegNSGA2Optimizer
from tars_core.optimizer.objective import porkchop_grid
from tars_core.planner.engine import plan_routes

def run_calculation(job,snapshot):
    request=REQUEST_MODELS[job['kind']].model_validate(job['payload'])
    if job['kind']=='plan':
        start=request.dep_start or jd_to_iso(snapshot.get_epoch_range(int(request.origin))[0]+.00001)
        end=request.dep_end or jd_to_iso(snapshot.get_epoch_range(int(request.target))[1]-.00001)
        routes=plan_routes(BODY_BY_ID[int(request.origin)].name.lower(),BODY_BY_ID[int(request.target)].name.lower(),request.mode,start,end,snapshot)
        result={'origin':request.origin,'target':request.target,'mode':request.mode,'count':len(routes),'routes':routes,**provenance(snapshot)}
    elif job['kind']=='porkchop':
        grid=porkchop_grid(int(request.origin),int(request.target),iso_to_jd(request.dep_start),iso_to_jd(request.dep_end),request.tof_min_days,request.tof_max_days,snapshot,request.dep_steps,request.tof_steps)
        result={'origin':request.origin,'target':request.target,**grid,'departure_isos':[jd_to_iso(float(x)) for x in grid['departure_jds']],'dep_steps':request.dep_steps,'tof_steps':request.tof_steps,**provenance(snapshot)}
    else:
        if job['kind']=='optimization_single':
            req=OptimizationRequest(int(request.origin),int(request.target),iso_to_jd(request.dep_start),iso_to_jd(request.dep_end),request.tof_min_days,request.tof_max_days,request.population_size,request.max_iterations,mode=request.mode,seed=job['seed'])
            optimizer=NSGA2Optimizer(req,snapshot)
        else:
            req=MultiLegOptimizationRequest(request.body_sequence,iso_to_jd(request.dep_start),iso_to_jd(request.dep_end),[tuple(v) for v in request.leg_tof_bounds],request.population_size,request.max_iterations,request.max_c3,request.mode,seed=job['seed'])
            optimizer=MultiLegNSGA2Optimizer(req,snapshot)
        last=None
        for progress in optimizer.run():
            last=progress
            payload=asdict(progress)
            payload.update({'best_dv_total':progress.best_dv_total,'best_departure_jd':progress.best_departure_jd,'best_tof_days':getattr(progress,'best_tof_days',None),'best_leg_tof_days':getattr(progress,'best_leg_tof_days',None),'best_total_tof_days':getattr(progress,'best_total_tof_days',None),'best_dv_departure':progress.best_dv_departure,'best_dv_arrival':progress.best_dv_arrival,'best_dv_flyby':getattr(progress,'best_dv_flyby',0.)})
            yield ('progress',safe_value(payload))
        if last is None or not last.converged or not np.isfinite(last.best_dv_total):raise ValueError('No feasible solution')
        if job['kind']=='optimization_single':
            result=lambert_result(LambertRequest(origin=request.origin,target=request.target,departure_date=jd_to_iso(last.best_departure_jd),tof_days=last.best_tof_days),snapshot)
        else:
            result=multileg_result(MultiLegRequest(body_sequence=request.body_sequence,departure_date=jd_to_iso(last.best_departure_jd),leg_tof_days=last.best_leg_tof_days),snapshot)
        result['optimization']=safe_value(payload)
    result.update({'seed':job['seed'],'request_fingerprint':job['fingerprint'],'schema_version':'1'})
    yield ('result',safe_value(result))

def calculate_child(job,snapshot,output):
    try:
        for message in run_calculation(job,snapshot):output.put(message)
    except (ValueError,KeyError):output.put(('permanent_error','INFEASIBLE_CALCULATION'))
    except Exception:output.put(('permanent_error','COMPUTE_FAILED'))
