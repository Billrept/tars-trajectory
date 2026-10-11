import asyncio,hmac,json,os
from dataclasses import asdict
from functools import lru_cache
import boto3,numpy as np,redis
from fastapi import FastAPI,HTTPException,Header,Response,WebSocket,WebSocketDisconnect,Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,ConfigDict,Field
from tars_core.bodies import BODY_BY_ID
from tars_core.time import iso_to_jd,jd_to_iso,jds_to_iso
from tars_core.mechanics.transforms import positions_to_scene
from tars_contracts.ttl import TTLValue
from tars_contracts.tls import redis_tls_kwargs
from .store import DatasetStore

def create_store():
    client=boto3.client('s3',endpoint_url=os.environ.get('S3_ENDPOINT_URL'),region_name=os.environ.get('AWS_REGION','us-east-1'))
    return DatasetStore(client,os.environ['DATASET_BUCKET'],redis.Redis.from_url(os.environ['CACHE_REDIS_URL'],socket_timeout=.2,socket_connect_timeout=.2,**redis_tls_kwargs(os.environ['CACHE_REDIS_URL'],'CACHE_REDIS_CA_CERT')),os.environ.get('CACHE_PREFIX','tars:local'))

# Public reads only change when a new dataset is published; a CDN may reuse them briefly.
PUBLIC_CACHE='public, max-age=60'

def create_app(store=None,active_ttl=None):
    store=store or create_store()
    # Reuse the active manifest instead of re-reading and re-hashing it on every request.
    current=TTLValue(store.active_manifest,float(os.environ.get('ACTIVE_MANIFEST_TTL_SECONDS','60') if active_ttl is None else active_ttl))
    token=os.environ['SERVICE_TOKEN']
    if len(token)<32:raise ValueError('SERVICE_TOKEN must have at least 32 characters')
    app=FastAPI(title='Tars ephemeris',version='1.0.0')
    app.add_middleware(CORSMiddleware,allow_origins=os.environ.get('CORS_ORIGINS','http://localhost:3000').split(','),allow_methods=['GET'],allow_headers=['Content-Type'])
    @lru_cache(maxsize=2)
    def snapshot(dataset_id):return store.snapshot(dataset_id)
    def active():
        try:return current.get()
        except Exception as e:raise HTTPException(503,'No validated dataset available') from e
    def private(value):
        if not value or not hmac.compare_digest(value,token):raise HTTPException(401,'Invalid workload credential')
    @app.get('/livez')
    @app.get('/health')
    def live():return {'status':'ok','service':'tars-ephemeris'}
    @app.get('/readyz')
    def ready():return {'status':'ok','dataset_id':active()['dataset_id']}
    @app.get('/bodies')
    @app.get('/api/v1/ephemeris/bodies')
    def bodies(response:Response):
        response.headers['Cache-Control']=PUBLIC_CACHE
        return [{k:v for k,v in asdict(BODY_BY_ID[int(bid)]).items() if k!='horizons_id'} for bid in active()['bodies']]
    @app.get('/epoch-range')
    @app.get('/api/v1/ephemeris/epoch-range')
    def epoch_range(response:Response):
        response.headers['Cache-Control']=PUBLIC_CACHE
        manifest=active();start=max(v['start_jd'] for v in manifest['bodies'].values());end=min(v['end_jd'] for v in manifest['bodies'].values())
        return {'start_jd':start,'end_jd':end,'start_iso':jd_to_iso(start),'end_iso':jd_to_iso(end),'dataset_id':manifest['dataset_id'],'time_scale':'TDB'}
    @app.get('/bodies/{identifier}/ephemeris')
    @app.get('/api/v1/ephemeris/bodies/{identifier}/ephemeris')
    def ephemeris(response:Response,identifier:str,start:str='2026-01-01',end:str='2027-01-01',step_days:int=Query(default=10,ge=1,le=365),scene_units:bool=True):
        response.headers['Cache-Control']=PUBLIC_CACHE
        from tars_core.bodies import BODY_BY_NAME
        body=BODY_BY_ID.get(int(identifier)) if identifier.isdigit() else BODY_BY_NAME.get(identifier.lower())
        if body is None:raise HTTPException(404,'Unknown body')
        data=snapshot(active()['dataset_id'])
        try:
            first,last=iso_to_jd(start),iso_to_jd(end);data.validate_epoch_range(body.naif_id,first,last)
            count=min(1000,max(2,int((last-first)/step_days)+1));epochs=np.linspace(first,last,count)
            positions=data.get_positions_batch(body.naif_id,epochs)
            if scene_units:positions=positions_to_scene(positions)
        except (ValueError,KeyError) as e:raise HTTPException(422,'Unavailable body or invalid epoch range') from e
        return {'body':body.name,'naif_id':body.naif_id,'n_points':count,'scene_units':scene_units,'dataset_id':data.dataset_id,'points':[{'epoch_jd':float(jd),'epoch_iso':iso,'x':float(p[0]),'y':float(p[1]),'z':float(p[2])} for jd,iso,p in zip(epochs,jds_to_iso(epochs),positions)]}
    @app.get('/internal/v1/active')
    def manifest(x_service_token:str|None=Header(default=None)):
        private(x_service_token);return active()
    @app.get('/internal/v1/datasets/{dataset_id}')
    def pinned_manifest(dataset_id:str,x_service_token:str|None=Header(default=None)):
        private(x_service_token)
        try:return store.manifest(dataset_id)
        except (ValueError,KeyError):raise HTTPException(404,'Dataset not found')
    @app.get('/internal/v1/datasets/{dataset_id}/bodies/{body_id}')
    def chunk(dataset_id:str,body_id:int,x_service_token:str|None=Header(default=None)):
        private(x_service_token)
        try:return Response(store.body_bytes(dataset_id,body_id),media_type='application/octet-stream')
        except (ValueError,KeyError):raise HTTPException(404,'Body dataset not found')
    @app.websocket('/ws/ephemeris/stream')
    @app.websocket('/api/v1/ephemeris/ws/stream')
    async def stream(ws:WebSocket):
        if ws.headers.get('origin') not in os.environ.get('CORS_ORIGINS','http://localhost:3000').split(','):
            await ws.close(code=1008);return
        class Config(BaseModel):
            model_config=ConfigDict(allow_inf_nan=False,extra='forbid')
            body_ids:list[int]|None=None
            start_jd:float|None=None
            start_iso:str|None=None
            speed:float=Field(default=10,ge=0,le=1000)
            fps:int=Field(default=30,ge=1,le=30)
            scene_units:bool=True
            binary:bool=False
        await ws.accept();paused=False
        try:
            data=snapshot(active()['dataset_id'])
            config=Config.model_validate_json(await asyncio.wait_for(ws.receive_text(),5))
            ids=config.body_ids or data.available_bodies()
            jd=iso_to_jd(config.start_iso) if config.start_iso else config.start_jd
            if jd is None:jd=max(data.get_epoch_range(b)[0] for b in ids)
            while True:
                try:
                    raw=await asyncio.wait_for(ws.receive_text(),.001)
                    if len(raw)>65536:raise ValueError('Oversized control frame')
                    if raw in ('pause','resume','stop'):
                        if raw=='stop':break
                        paused=raw=='pause'
                    else:
                        config=Config.model_validate({**config.model_dump(),**json.loads(raw)})
                        ids=config.body_ids or data.available_bodies()
                        update=json.loads(raw)
                        if 'start_iso' in update:jd=iso_to_jd(update['start_iso'])
                        elif 'start_jd' in update:jd=update['start_jd']
                except asyncio.TimeoutError:pass
                if not paused:
                    values=[]
                    for bid in ids:
                        if bid not in data:raise ValueError('Unavailable body')
                        p=data.get_position(bid,jd)
                        if config.scene_units:p=positions_to_scene(p)
                        values.append({'body_id':bid,'name':BODY_BY_ID[bid].name,'position':p.tolist()})
                    await ws.send_json({'epoch_jd':jd,'epoch_iso':jd_to_iso(jd),'dataset_id':data.dataset_id,'bodies':values})
                    jd+=config.speed/config.fps
                await asyncio.sleep(1/config.fps)
        except WebSocketDisconnect:pass
        except (ValueError,KeyError,asyncio.TimeoutError):
            await ws.close(code=1008)
    return app
