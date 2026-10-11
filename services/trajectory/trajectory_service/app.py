import os,threading
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from tars_contracts.client import EphemerisClient
from tars_contracts.requests import LambertRequest,MultiLegRequest,AssessRequest,OrbitElementsRequest
from tars_core.calculation import lambert_result,multileg_result,orbit_result
from tars_core.optimizer.objective import delta_v_objective
from tars_core.time import iso_to_jd,jd_to_iso

def create_app(client=None):
    client=client or EphemerisClient(os.environ['EPHEMERIS_URL'],os.environ['SERVICE_TOKEN'])
    app=FastAPI(title='Tars trajectory',version='1.0.0')
    app.add_middleware(CORSMiddleware,allow_origins=os.environ.get('CORS_ORIGINS','http://localhost:3000').split(','),allow_methods=['POST','GET'],allow_headers=['Content-Type'])
    slots=threading.BoundedSemaphore(2)
    def calculate(function,request):
        if not slots.acquire(blocking=False):raise HTTPException(429,'Calculation capacity reached',headers={'Retry-After':'1'})
        try:
            data=client.snapshot(client.active_manifest()['dataset_id'])
            return function(request,data)
        except (ValueError,KeyError) as e:raise HTTPException(422,'Unsupported calculation or unavailable epoch/body') from e
        finally:slots.release()
    @app.get('/livez')
    @app.get('/health')
    def live():return {'status':'ok','service':'tars-trajectory'}
    @app.get('/readyz')
    def ready():return {'status':'ok','dataset_id':client.active_manifest()['dataset_id']}
    @app.post('/lambert')
    @app.post('/api/v1/trajectory/lambert')
    def lambert(request:LambertRequest):return calculate(lambert_result,request)
    @app.post('/multileg')
    @app.post('/api/v1/trajectory/multileg')
    def multileg(request:MultiLegRequest):return calculate(multileg_result,request)
    @app.post('/orbit-info')
    @app.post('/api/v1/trajectory/orbit-info')
    def orbit(request:OrbitElementsRequest):return orbit_result(request)
    @app.post('/assess')
    @app.post('/api/v1/trajectory/assess')
    def assess(request:AssessRequest):
        def evaluation(req,data):
            dep=iso_to_jd(req.departure_date)
            result=delta_v_objective(dep,req.tof_days,int(req.origin),int(req.target),data)
            if not result['converged']:raise ValueError('Infeasible transfer')
            rating=next((label for threshold,label in [(4,'excellent'),(6,'good'),(8,'moderate'),(12,'poor')] if result['dv_total']<threshold),'bad')
            return {'origin':req.origin,'target':req.target,'departure_jd':dep,'arrival_jd':dep+req.tof_days,'departure_date':req.departure_date,'arrival_date':jd_to_iso(dep+req.tof_days),'tof_days':req.tof_days,'dv_total_km_s':result['dv_total'],'dv_departure_km_s':result['dv_departure'],'dv_arrival_km_s':result['dv_arrival'],'converged':True,'rating':rating,'suggestion':None,'dataset_id':data.dataset_id}
        return calculate(evaluation,request)
    return app
