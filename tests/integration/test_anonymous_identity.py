import hashlib,re,time
import pytest,redis
from fastapi.testclient import TestClient
from jobs_service.app import create_app
from jobs_service.results import ResultStore

PAYLOAD={'kind':'optimization_single','payload':{'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','population_size':6,'max_iterations':10}}
COOKIE='tars_uid'

def app(repo,ephemeris,dataset_store,limits=None):
    limits=limits if limits is not None else redis.Redis.from_url('redis://127.0.0.1:63792/1')
    limits.flushdb()
    return create_app(repo,ephemeris,ResultStore(dataset_store.client,dataset_store.bucket),limits)

@pytest.fixture
def limits():
    value=redis.Redis.from_url('redis://127.0.0.1:63792/1');value.flushdb();yield value;value.flushdb();value.close()

def test_cookie_minted_with_private_scoped_attributes(repo,ephemeris,dataset_store,service_env,limits):
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        response=client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'cookie-attr-one-0001'})
        assert response.status_code==202,response.text
        set_cookie=response.headers['set-cookie'];assert COOKIE+'=' in set_cookie
        assert 'HttpOnly' in set_cookie and 'SameSite=lax' in set_cookie and 'Path=/api/v1/jobs' in set_cookie
        assert 'Max-Age=2592000' in set_cookie and 'Secure' not in set_cookie
        uid=client.cookies.get(COOKIE);assert re.fullmatch(r'[A-Za-z0-9_-]{22}',uid)
        assert client.get('/api/v1/jobs').headers['set-cookie'].startswith(COOKIE+'='+uid) # refreshed on every response

def test_reused_cookie_replays_same_job_and_fresh_cookie_admits_new(repo,ephemeris,dataset_store,service_env,limits):
    application=app(repo,ephemeris,dataset_store,limits)
    first=TestClient(application) # entered without context so the shared ephemeris client is never torn down
    try:
        headers={'Idempotency-Key':'cookie-idem-one-0001'}
        assert first.post('/api/v1/jobs',json=PAYLOAD,headers=headers).status_code==202
        job_one=first.post('/api/v1/jobs',json=PAYLOAD,headers=headers).json()
        assert first.cookies[COOKIE] and first.post('/api/v1/jobs',json=PAYLOAD,headers=headers).json()['job_id']==job_one['job_id']
        second=TestClient(application) # fresh cookie jar -> distinct anonymous owner
        try:
            assert second.get(f'/api/v1/jobs/{job_one["job_id"]}').status_code==404
            job_two=second.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'cookie-idem-one-0001'}).json()
            assert job_two['job_id']!=job_one['job_id']
        finally:second.close()
    finally:first.close()

def test_history_lists_only_own_jobs_newest_first_with_summary(repo,ephemeris,dataset_store,service_env,limits):
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        for i in range(3):
            body=dict(PAYLOAD);body['payload']=dict(PAYLOAD['payload'],dep_start='2026-06-0'+str(i+1))
            response=client.post('/api/v1/jobs',json=body,headers={'Idempotency-Key':'history-entry-00'+str(i)})
            assert response.status_code==202,response.text
        with TestClient(create_app(repo,ephemeris,ResultStore(dataset_store.client,dataset_store.bucket),limits)) as other:
            other.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'history-stranger-01'})
        rows=client.get('/api/v1/jobs').json()['jobs']
        assert len(rows)==3
        created=[r['created_at'] for r in rows];assert created==sorted(created,reverse=True) # newest first
        assert all(set(r)=={'job_id','kind','status','created_at','summary'} for r in rows)
        summary=rows[0]['summary'];assert summary['origin']=='399' and summary['target']=='499' and summary['mode']=='pareto' # normalized NAIF ids

def test_session_delete_expires_cookie_with_matching_path(repo,ephemeris,dataset_store,service_env,limits):
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'session-reset-0001'})
        assert client.delete('/api/v1/jobs/session').status_code==204
        set_cookie=client.delete('/api/v1/jobs/session').headers['set-cookie']
        assert set_cookie.startswith(COOKIE+'="";') and 'Max-Age=0' in set_cookie and 'Path=/api/v1/jobs' in set_cookie
        assert client.cookies.get(COOKIE) is None and client.get('/api/v1/jobs').json()['jobs']==[]

def test_per_ip_limit_blocks_new_jobs_but_not_replays(repo,ephemeris,dataset_store,service_env,limits,monkeypatch):
    from jobs_service import app as app_module
    monkeypatch.setattr(app_module,'PER_MIN',2)
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        earlier={'Idempotency-Key':'rate-replay-000001'}
        original=client.post('/api/v1/jobs',json=PAYLOAD,headers=earlier).json()['job_id']
        assert client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'rate-second-000001'}).status_code==202
        blocked=client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'rate-third-000001'})
        assert blocked.status_code==429 and 'Too many new jobs' in blocked.json()['detail']
        replay=client.post('/api/v1/jobs',json=PAYLOAD,headers=earlier)
        assert replay.status_code==202 and replay.json()['job_id']==original

def test_global_queue_cap_returns_503(repo,ephemeris,dataset_store,service_env,limits,monkeypatch):
    monkeypatch.setenv('GLOBAL_QUEUE_CAP','1')
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        assert client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'cap-first-0000001'}).status_code==202
        full=client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'cap-second-000001'})
        assert full.status_code==503 and 'busy' in full.json()['detail']

def test_limiter_redis_unavailable_returns_503_at_admission(repo,ephemeris,dataset_store,service_env):
    dead=redis.Redis.from_url('redis://127.0.0.1:1/0',socket_timeout=.05,socket_connect_timeout=.05)
    with TestClient(create_app(repo,ephemeris,ResultStore(dataset_store.client,dataset_store.bucket),dead)) as client:
        response=client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'dead-limiter-00001'})
        assert response.status_code==503 and 'calculator is busy' in response.json()['detail']

def test_unauthenticated_client_ip_falls_back_to_socket_peer(repo,ephemeris,dataset_store,service_env,limits):
    with TestClient(app(repo,ephemeris,dataset_store,limits)) as client:
        assert client.post('/api/v1/jobs',json=PAYLOAD,headers={'Idempotency-Key':'ip-direct-0000001'}).status_code==202
        key=[k.decode() for k in limits.keys('tars:rl:*') if k.decode().endswith(':m:'+str(int(time.time()//60)))][0]
        digest=key.split(':')[2]
        expected=hashlib.sha256(('integration-test-only-service-token-000000'+'testclient').encode()).hexdigest()[:32]
        assert digest==expected # no X-Forwarded-For -> host 'testclient' is the rate-limit identity

def test_trusted_proxy_hops_select_forwarded_ip(repo,ephemeris,dataset_store,service_env,limits,monkeypatch):
    from jobs_service import app as app_module
    forwarded={'X-Forwarded-For':'spoofed, 1.1.1.1, 2.2.2.2'}
    expected={0:'testclient',1:'2.2.2.2',2:'1.1.1.1'}
    for hops,ip in expected.items():
        monkeypatch.setenv('TRUSTED_PROXY_HOPS',str(hops))
        value=redis.Redis.from_url('redis://127.0.0.1:63792/1');value.flushdb()
        client=TestClient(create_app(repo,ephemeris,ResultStore(dataset_store.client,dataset_store.bucket),value)) # no context manager: the jobs lifespan closes the shared ephemeris client
        try:
            client.cookies.set(COOKIE,'A'*22)
            response=client.post('/api/v1/jobs',json=PAYLOAD,headers={**forwarded,'Idempotency-Key':'ip-hops-'+str(hops)+'-00000001'})
            assert response.status_code==202,response.text
            keys=[k.decode() for k in value.keys('tars:rl:*') if ':m:' in k.decode()]
            assert len(keys)==1,keys
            assert value.get(keys[0])==b'1' # one admission counted against the selected IP
            expected_key_prefix=hashlib.sha256(('integration-test-only-service-token-000000'+ip).encode()).hexdigest()[:32]
            assert keys[0].split(':')[2]==expected_key_prefix,(hops,keys[0])
        finally:client.close();value.flushdb();value.close()
