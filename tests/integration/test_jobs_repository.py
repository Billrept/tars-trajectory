import os,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from jobs_service.repository import JobRepository, IdempotencyConflict

@pytest.fixture
def repo():
    schema='tars_test_'+uuid.uuid4().hex
    repository=JobRepository(os.environ.get('TEST_DATABASE_URL','postgresql://tars_test:test-only-password@127.0.0.1:54329/tars_test'),schema=schema)
    repository.migrate()
    yield repository
    with repository.engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    repository.engine.dispose()

def submit(repo,key='same-logical-request',owner='alice',payload=None):
    row,created=repo.admit(owner,'optimization_single',key,payload or {'origin':'399','target':'499'},'dataset-one',seed=42)
    return row

def test_fifty_concurrent_retries_admit_one_durable_job_and_outbox(repo):
    with ThreadPoolExecutor(max_workers=10) as pool:
        rows=list(pool.map(lambda _:submit(repo),range(50)))
    assert len({r['job_id'] for r in rows})==1
    with repo.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM jobs')).scalar()==1
        assert c.execute(text('SELECT count(*) FROM outbox')).scalar()==1
    with pytest.raises(IdempotencyConflict):submit(repo,payload={'different':'payload'})
    assert repo.get('bob',rows[0]['job_id']) is None

def test_stale_worker_cannot_overwrite_reclaimed_job(repo):
    row=submit(repo);job_id=row['job_id']
    old=repo.claim(job_id,'worker-old')
    assert repo.write_progress(old,{'iteration':1})
    with repo.engine.begin() as c:c.execute(text('UPDATE jobs SET lease_until=now()-interval \'1 second\' WHERE id=:id'),{'id':job_id})
    repo.reconcile()
    new=repo.claim(job_id,'worker-new')
    assert new['fencing_token'] > old['fencing_token']
    assert not repo.write_progress(old,{'iteration':999})
    assert not repo.complete(old,{'key':'old'})
    assert repo.complete(new,{'key':'new'})
    assert not repo.complete(new,{'key':'duplicate'})
    assert repo.get('alice',job_id)['result_ref']=={'key':'new'}
    assert repo.claim(job_id,'worker-duplicate') is None

def test_replay_preserves_seed_and_dataset_when_server_defaults_change(repo):
    row=submit(repo)
    retry,_=repo.admit('alice','optimization_single','same-logical-request',{'origin':'399','target':'499'},'dataset-two',seed=9)
    assert retry['job_id']==row['job_id']
    assert retry['seed']==42 and retry['dataset_id']=='dataset-one'

def test_bounded_retries_become_terminal_and_retention_keeps_pending_work(repo):
    row=submit(repo)
    for i in range(3):
        lease=repo.claim(row['job_id'],f'worker-{i}')
        assert repo.fail(lease,'TEMPORARY_UNAVAILABLE',retry=True)
    assert repo.get('alice',row['job_id'])['status']=='failed'
    pending=submit(repo,key='another-logical-request')
    with repo.engine.begin() as c:c.execute(text('UPDATE jobs SET created_at=now()-interval \'40 days\' WHERE id=:id'),{'id':pending['job_id']})
    repo.cleanup()
    assert repo.get('alice',pending['job_id'])['status']=='queued'
