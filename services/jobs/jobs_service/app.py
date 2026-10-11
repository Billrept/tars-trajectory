import hashlib,os,re,secrets,time,uuid
from contextlib import asynccontextmanager
import redis
from fastapi import FastAPI,HTTPException,Header,Query,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from tars_contracts.client import EphemerisClient
from tars_contracts.tls import redis_tls_kwargs
from tars_contracts.requests import JobSubmission,normalize_submission
from tars_core.time import iso_to_jd
from .config import repository,result_store
from .repository import GlobalCapReached,IdempotencyConflict,QuotaExceeded

COOKIE='tars_uid';COOKIE_PATH='/api/v1/jobs';MAX_AGE=2592000;SECURE=os.environ.get('COOKIE_SECURE')=='1'
PER_MIN=int(os.environ.get('RATE_LIMIT_PER_MIN') or 5);PER_DAY=int(os.environ.get('RATE_LIMIT_PER_DAY') or 30)

def create_app(repo=None,ephemeris=None,results=None,limits=None):
    repo=repo or repository();ephemeris=ephemeris or EphemerisClient(os.environ['EPHEMERIS_URL'],os.environ['SERVICE_TOKEN'])
    results=results or result_store();limits=limits or redis.Redis.from_url(os.environ['CACHE_REDIS_URL'],socket_timeout=.2,socket_connect_timeout=.2,**redis_tls_kwargs(os.environ['CACHE_REDIS_URL'],'CACHE_REDIS_CA_CERT'))
    origins=os.environ.get('CORS_ORIGINS','http://localhost:3000').split(',')
    @asynccontextmanager
    async def lifespan(app):
        yield
        ephemeris.close();limits.close();repo.engine.dispose()
    app=FastAPI(title='Tars jobs',version='1.0.0',lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type','Idempotency-Key'])
    @app.middleware('http')
    async def identity(request,call_next):
        uid=None
        if request.url.path.startswith(COOKIE_PATH):
            uid=request.cookies.get(COOKIE)
            if not re.fullmatch(r'[A-Za-z0-9_-]{22}',uid or ''):uid=secrets.token_urlsafe(16)
            request.state.owner='anon:'+hashlib.sha256(uid.encode()).hexdigest()[:32]
            request.state.reset=False
        response=await call_next(request)
        if uid is not None and not getattr(request.state,'reset',False):
            response.set_cookie(COOKIE,uid,max_age=MAX_AGE,path=COOKIE_PATH,httponly=True,samesite='lax',secure=SECURE)
        return response
    def owner(request):
        return request.state.owner
    def client_ip(request):
        hops=int(os.environ.get('TRUSTED_PROXY_HOPS','0'));forwarded=request.headers.get('X-Forwarded-For')
        if hops>0 and forwarded:
            parts=[p.strip() for p in forwarded.split(',') if p.strip()]
            if len(parts)>=hops:return parts[-hops]
        return request.client.host
    def lookup(subject,job_id):
        row=repo.get(subject,str(job_id))
        if row is None:raise HTTPException(404,'Job not found')
        return row
    def present(row):
        return {key:row[key] for key in ('job_id','status','attempt','sequence','progress','result_ref','error','dataset_id','solver_version','solver_digest','seed')}
    def admission(row):
        jid=row['job_id'];return {'job_id':jid,'status':'queued','status_url':f'/api/v1/jobs/{jid}'}
    def submit(submission,key,request):
        ident=owner(request)
        if not key:raise HTTPException(400,'Idempotency-Key required')
        try:
            normalized=normalize_submission(submission);kind,payload=normalized['kind'],normalized['payload']
            replay=repo.replay(ident,kind,key,payload)
            if replay:return admission(replay)
            base='tars:rl:'+hashlib.sha256((os.environ['SERVICE_TOKEN']+client_ip(request)).encode()).hexdigest()[:32]
            minute_key=f'{base}:m:{int(time.time()//60)}';day_key=f'{base}:d:{time.strftime("%Y%m%d",time.gmtime())}'
            try:
                minute,day=limits.mget(minute_key,day_key)
                if (minute is not None and int(minute)>=PER_MIN) or (day is not None and int(day)>=PER_DAY):
                    raise HTTPException(429,'Too many new jobs from this browser or network; try again later')
            except redis.RedisError as e:raise HTTPException(503,'The calculator is busy; try again shortly') from e
            manifest=ephemeris.active_manifest()
            ids=payload.get('body_sequence') or [payload['origin'],payload['target']]
            if any(str(bid) not in manifest['bodies'] for bid in ids):raise ValueError('Body unavailable')
            start=payload.get('dep_start');end=payload.get('dep_end')
            if start:
                first,last=iso_to_jd(start),iso_to_jd(end)
                bounds=payload.get('leg_tof_bounds')
                for i,bid in enumerate(ids):
                    minimum=sum(b[0] for b in bounds[:i]) if bounds else (payload.get('tof_min_days',0) if i else 0)
                    maximum=sum(b[1] for b in bounds[:i]) if bounds else (payload.get('tof_max_days',0) if i else 0)
                    interval=manifest['bodies'][str(bid)]
                    if first+minimum<interval['start_jd'] or last+maximum>interval['end_jd']:raise ValueError('Encounter outside dataset')
            row,created=repo.admit(ident,kind,key,payload,manifest['dataset_id'],seed=payload.get('seed'))
            if created:
                try:
                    pipe=limits.pipeline();pipe.incr(minute_key).expire(minute_key,120);pipe.incr(day_key).expire(day_key,90000);pipe.execute()
                except redis.RedisError:pass
            return admission(row)
        except IdempotencyConflict as e:raise HTTPException(409,'Idempotency key conflicts with prior request') from e
        except QuotaExceeded as e:raise HTTPException(429,'Too many new jobs from this browser or network; try again later') from e
        except GlobalCapReached as e:raise HTTPException(503,'The calculator is busy; try again shortly') from e
        except (ValueError,KeyError) as e:raise HTTPException(422,'Invalid job or unavailable encounter') from e
        except SQLAlchemyError as e:raise HTTPException(503,'Durable job storage unavailable') from e
    @app.get('/livez')
    @app.get('/health')
    def live():return {'status':'ok','service':'tars-jobs'}
    @app.get('/readyz')
    def ready():
        with repo.engine.connect() as c:c.exec_driver_sql('SELECT 1 FROM schema_migrations WHERE version=1')
        return {'status':'ok'}
    @app.post('/api/v1/jobs',status_code=202)
    def create(submission:JobSubmission,request:Request,idempotency_key:str|None=Header(default=None)):
        return submit(submission,idempotency_key,request)
    @app.get('/api/v1/jobs')
    def history(request:Request,limit:int=Query(20,ge=1,le=50)):
        fields=('origin','target','body_sequence','mode')
        return {'jobs':[{'job_id':row['job_id'],'kind':row['kind'],'status':row['status'],'created_at':row['created_at'],'summary':{f:row['payload'].get(f) for f in fields}} for row in repo.list(owner(request),limit)]}
    @app.delete('/api/v1/jobs/session',status_code=204)
    def session(request:Request,response:Response):
        request.state.reset=True;response.delete_cookie(COOKIE,path=COOKIE_PATH)
    @app.get('/api/v1/jobs/{job_id}')
    def status(job_id:uuid.UUID,request:Request):
        return present(lookup(owner(request),job_id))
    @app.get('/api/v1/jobs/{job_id}/result')
    def result(job_id:uuid.UUID,request:Request):
        row=lookup(owner(request),job_id)
        if row['status']!='succeeded':raise HTTPException(409,'Result is not available')
        return results.load(str(job_id),row['result_ref'])
    return app
