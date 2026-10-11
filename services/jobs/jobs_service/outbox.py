import asyncio,time
from arq import create_pool
from .config import repository,redis_settings,queue_for

async def dispatch_pending(repo,pool):
    count=0
    for job_id,token in await asyncio.to_thread(repo.pending_outbox):
        row=await asyncio.to_thread(repo.load,job_id)
        generation=row['fencing_token']
        await pool.enqueue_job('execute_job',job_id,generation,_job_id=f'{job_id}:{generation}',_queue_name=queue_for(row))
        if await asyncio.to_thread(repo.mark_sent,job_id,token):count+=1
    return count

async def main():
    repo=repository();pool=await create_pool(redis_settings());last=0
    try:
        while True:
            try:
                if time.monotonic()-last>=30:
                    await asyncio.to_thread(repo.reconcile);last=time.monotonic()
                await dispatch_pending(repo,pool)
            except Exception:
                print('Outbox dependency unavailable; retrying',flush=True)
            await asyncio.sleep(1)
    finally:
        await pool.aclose();repo.engine.dispose()

if __name__=='__main__':asyncio.run(main())
