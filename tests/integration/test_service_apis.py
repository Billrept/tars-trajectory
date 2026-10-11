import pytest,redis
from fastapi.testclient import TestClient
from tars_contracts.client import EphemerisClient
from ephemeris_service.app import create_app as ephemeris_app
from trajectory_service.app import create_app as trajectory_app
from jobs_service.app import create_app as jobs_app
from jobs_service.results import ResultStore

@pytest.fixture
def ephemeris(dataset_store,service_env):
    client=EphemerisClient('http://local-ephemeris','integration-test-only-service-token-000000')
    client.http.close();client.http=TestClient(ephemeris_app(dataset_store),headers={'X-Service-Token':'integration-test-only-service-token-000000'})
    yield client
    client.close()

def test_separated_ephemeris_and_trajectory_contracts(ephemeris):
    assert ephemeris.http.get('/bodies').status_code==200
    assert ephemeris.http.get('/internal/v1/active',headers={'X-Service-Token':'wrong'}).status_code==401
    with TestClient(trajectory_app(ephemeris)) as client:
        response=client.post('/api/v1/trajectory/lambert',json={'origin':'earth','target':'mars','departure_date':'2026-09-01','tof_days':200})
        assert response.status_code==200,response.text
        result=response.json();assert result['solver_digest'] and result['dataset_id']
        assert len(result['trajectory_points'])>20
        assert client.post('/multileg',json={'body_sequence':['earth','mars'],'departure_date':'2026-09-01','leg_tof_days':[-1]}).status_code==422
        response=client.post('/orbit-info',json={'a_km':-12000,'e':1.4,'i_deg':0,'raan_deg':0,'arg_p_deg':0,'mu':398600.4418})
        assert response.status_code==200,response.text
        assert response.json()['apoapsis_point_scene'] is None

def test_cookie_identity_idempotency_and_owner_isolation(repo,ephemeris,dataset_store,service_env):
    results=ResultStore(dataset_store.client,dataset_store.bucket)
    limits=redis.Redis.from_url('redis://127.0.0.1:63792/1');limits.flushdb()
    app=jobs_app(repo,ephemeris,results,limits)
    with TestClient(app) as client:
        payload={'kind':'optimization_single','payload':{'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','population_size':6,'max_iterations':10}}
        headers={'Idempotency-Key':'logical-submit-one'}
        admitted=client.post('/api/v1/jobs',json=payload,headers=headers)
        assert admitted.status_code==202,admitted.text
        job=admitted.json();assert set(job)=={'job_id','status','status_url'} and job['status']=='queued'
        assert client.post('/api/v1/jobs',json=payload,headers=headers).json()==job
        stranger=TestClient(app) # fresh cookie jar -> different anonymous owner
        assert stranger.get(job['status_url']).status_code==404
        assert stranger.get(f'/api/v1/jobs/{job["job_id"]}/result').status_code==404
        payload['payload']['max_iterations']=11
        assert client.post('/api/v1/jobs',json=payload,headers=headers).status_code==409
        lease=repo.claim(job['job_id'],'test-worker')
        ref=results.save(lease,{'validated':True,'dataset_id':lease['dataset_id']})
        assert repo.complete(lease,ref)
        assert client.get(f'/api/v1/jobs/{job["job_id"]}/result').json()['validated']
    limits.flushdb();limits.close()

def test_advertised_start_is_inside_dataset(ephemeris):
    from tars_core.time import iso_to_jd
    bounds=ephemeris.http.get('/epoch-range').json()
    assert abs(iso_to_jd(bounds['start_iso'])-bounds['start_jd'])<1e-9
    response=ephemeris.http.get('/bodies/earth/ephemeris',params={'start':bounds['start_iso'],'end':'2026-02-01'})
    assert response.status_code==200,response.text

def test_public_reads_are_cdn_cacheable_and_active_manifest_is_reused(ephemeris):
    for path in ('/api/v1/ephemeris/bodies','/api/v1/ephemeris/epoch-range','/api/v1/ephemeris/bodies/399/ephemeris?start=2026-01-01&end=2026-02-01'):
        assert ephemeris.http.get(path).headers['cache-control']=='public, max-age=60'
    calls=[];fetch=ephemeris._active.fetch
    ephemeris._active.fetch=lambda:calls.append(1) or fetch()
    ephemeris._active.expires=float('-inf')
    first=[ephemeris.active_manifest()['dataset_id'] for _ in range(5)]
    assert len(set(first))==1 and len(calls)==1 # one network call for five consumers' requests
