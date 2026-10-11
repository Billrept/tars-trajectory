import io,uuid
from pathlib import Path
import boto3,numpy as np,pytest,redis
from ephemeris_service.store import DatasetStore,decode_arrays

@pytest.fixture
def store():
    client=boto3.client('s3',endpoint_url='http://127.0.0.1:9009',aws_access_key_id='tars_test',aws_secret_access_key='test-only-password',region_name='us-east-1')
    bucket='tars-test-'+uuid.uuid4().hex
    client.create_bucket(Bucket=bucket)
    result=DatasetStore(client,bucket,redis.Redis.from_url('redis://127.0.0.1:63792/0',socket_timeout=.2),prefix=bucket)
    yield result
    objects=client.list_objects_v2(Bucket=bucket).get('Contents',[])
    if objects:client.delete_objects(Bucket=bucket,Delete={'Objects':[{'Key':o['Key']} for o in objects]})
    client.delete_bucket(Bucket=bucket)

def data():
    return {bid:dict(np.load(Path('tests/fixtures')/f'{name}_horizons.npz',allow_pickle=False)) for bid,name in [(399,'earth'),(499,'mars')]}

def test_duplicate_publication_and_cache_loss_preserve_pinned_snapshot(store):
    arrays=data();source={'source':'NASA JPL Horizons','required_bodies':[399,499],'time_scale':'TDB'}
    first=store.publish(arrays,source)
    second=store.publish(arrays,source)
    assert first==second
    before=store.snapshot(first).get_state(399,2461320.5)
    for key in store.cache.scan_iter(match=store.prefix+':*'):store.cache.delete(key)
    after=store.snapshot(first).get_state(399,2461320.5)
    np.testing.assert_array_equal(before[0],after[0])
    assert store.active_manifest()['dataset_id']==first

def test_incomplete_or_corrupt_dataset_does_not_replace_active_manifest(store):
    first=store.publish(data(),{'required_bodies':[399,499]})
    with pytest.raises(ValueError):store.publish({399:data()[399]},{'required_bodies':[399,499]})
    assert store.active_manifest()['dataset_id']==first
    manifest=store.manifest(first)
    key=store.cache_key(first,399)
    store.cache.set(key,b'invalid-array-data')
    snapshot=store.snapshot(first)
    assert np.isfinite(snapshot.get_position(399,2461320.5)).all()

def test_pickle_or_wrong_archive_shapes_are_rejected():
    buf=io.BytesIO();np.savez(buf,epochs=np.array([object()]),positions=np.zeros((1,3)),velocities=np.zeros((1,3)))
    with pytest.raises(ValueError):decode_arrays(buf.getvalue())

def test_partial_body_grid_cannot_replace_active(dataset_store):
    from astropy.time import Time
    original=dataset_store.active_manifest()['dataset_id']
    epochs=Time(np.arange(2461041.5,2461046.5),format='jd',scale='utc').tdb.jd
    body={'epochs':epochs[:-1],'positions':np.ones((4,3)),'velocities':np.zeros((4,3))}
    with pytest.raises(ValueError):
        dataset_store.publish({399:body},{'required_bodies':[399],'start':'2026-01-01','end':'2026-01-05','step_days':1,'query_time_type':'UT converted to TDB'})
    assert dataset_store.active_manifest()['dataset_id']==original
