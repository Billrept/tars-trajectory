import asyncio
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job,JobStatus

def test_lost_queue_and_enqueue_replay_recover_from_database(repo,service_env):
    from jobs_service.outbox import dispatch_pending
    from jobs_service.config import queue_for
    row,_=repo.admit('alice','optimization_single','queue-recovery-key',{'origin':'399','target':'499'},'fixture',seed=1)
    async def run():
        pool=await create_pool(RedisSettings(host='127.0.0.1',port=63791))
        try:
            await dispatch_pending(repo,pool)
            assert await Job(row['job_id']+':0',pool,_queue_name=queue_for(row)).status()==JobStatus.queued
            await pool.flushdb() # Dedicated tars-test Redis, never the application instance.
            assert repo.get('alice',row['job_id'])['status']=='queued'
            repo.reconcile();await dispatch_pending(repo,pool)
            assert await Job(row['job_id']+':0',pool,_queue_name=queue_for(row)).status()==JobStatus.queued
            # A lost publisher response can repeat the same delivery without another admission.
            repo.reconcile();await dispatch_pending(repo,pool)
            assert repo.get('alice',row['job_id'])['attempt']==0
        finally:await pool.aclose()
    asyncio.run(run())

def test_old_queue_generation_cannot_claim_recovered_work(repo,service_env):
    from sqlalchemy import text
    row,_=repo.admit('alice','optimization_single','generation-recovery-key',{},'fixture',seed=1)
    first=repo.claim(row['job_id'],'old',0)
    with repo.engine.begin() as c:c.execute(text('UPDATE jobs SET lease_until=now()-interval \'1 second\' WHERE id=:id'),{'id':row['job_id']})
    repo.reconcile()
    assert repo.claim(row['job_id'],'late-delivery',0) is None
    assert repo.claim(row['job_id'],'replacement',first['fencing_token']) is not None
