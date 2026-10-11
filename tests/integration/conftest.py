import os,uuid
from pathlib import Path
import boto3,numpy as np,pytest,redis
from sqlalchemy import text
from jobs_service.repository import JobRepository
from ephemeris_service.store import DatasetStore

@pytest.fixture
def repo():
    schema='tars_test_'+uuid.uuid4().hex
    value=JobRepository(os.environ.get('TEST_DATABASE_URL','postgresql://tars_test:test-only-password@127.0.0.1:54329/tars_test'),schema=schema)
    value.migrate();yield value
    with value.engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    value.engine.dispose()

@pytest.fixture
def dataset_store():
    client=boto3.client('s3',endpoint_url='http://127.0.0.1:9009',aws_access_key_id='tars_test',aws_secret_access_key='test-only-password',region_name='us-east-1')
    bucket='tars-test-'+uuid.uuid4().hex;client.create_bucket(Bucket=bucket)
    value=DatasetStore(client,bucket,redis.Redis.from_url('redis://127.0.0.1:63792/0',socket_timeout=.2),prefix=bucket)
    arrays={}
    for name,bid in [('earth',399),('mars',499)]:
        with np.load(Path('tests/fixtures')/f'{name}_horizons.npz',allow_pickle=False) as data:arrays[bid]=dict(data)
    value.publish(arrays,{'required_bodies':[399,499],'source':'NASA JPL Horizons','time_scale':'TDB'})
    yield value
    objects=client.list_objects_v2(Bucket=bucket).get('Contents',[])
    if objects:client.delete_objects(Bucket=bucket,Delete={'Objects':[{'Key':o['Key']} for o in objects]})
    client.delete_bucket(Bucket=bucket)

@pytest.fixture
def service_env(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    monkeypatch.setenv('SERVICE_TOKEN','integration-test-only-service-token-000000')
    monkeypatch.setenv('QUEUE_REDIS_URL','redis://127.0.0.1:63791/0')

@pytest.fixture
def ephemeris(dataset_store,service_env):
    from fastapi.testclient import TestClient
    from tars_contracts.client import EphemerisClient
    from ephemeris_service.app import create_app
    client=EphemerisClient('http://local-ephemeris','integration-test-only-service-token-000000')
    client.http.close();client.http=TestClient(create_app(dataset_store),headers={'X-Service-Token':'integration-test-only-service-token-000000'})
    yield client
    client.close()
