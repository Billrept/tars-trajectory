import asyncio,multiprocessing,os,queue,time,uuid
from tars_contracts.client import EphemerisClient
from tars_core import SOLVER_VERSION,SOLVER_DIGEST
from .config import repository,redis_settings,result_store,QUEUE_NAME

async def startup(ctx):
    ctx['repo']=repository();ctx['results']=result_store()
    ctx['ephemeris']=EphemerisClient(os.environ['EPHEMERIS_URL'],os.environ['SERVICE_TOKEN'])
    ctx['worker_id']=str(uuid.uuid4())
async def shutdown(ctx):
    ctx['ephemeris'].close();ctx['repo'].engine.dispose()
async def execute_job(ctx,job_id,generation):
    from .compute import calculate_child
    repo=ctx['repo'];lease=await asyncio.to_thread(repo.claim,job_id,ctx['worker_id'],generation)
    if lease is None:return
    if lease['solver_version']!=SOLVER_VERSION or lease['solver_digest']!=SOLVER_DIGEST:
        await asyncio.to_thread(repo.fail,lease,'INCOMPATIBLE_SOLVER',False);return
    lost=asyncio.Event()
    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            try:valid=await asyncio.to_thread(repo.heartbeat,lease)
            except Exception:valid=False
            if not valid:lost.set();return
    beat=asyncio.create_task(heartbeat());process=None;output=None
    try:
        snapshot=await asyncio.to_thread(ctx['ephemeris'].snapshot,lease['dataset_id'])
        context=multiprocessing.get_context('spawn');output=context.Queue(maxsize=64)
        process=context.Process(target=calculate_child,args=(lease,snapshot,output));process.start()
        start=time.monotonic();last_progress=0.;pending=None
        while True:
            if lost.is_set():return
            if time.monotonic()-start>600:raise TimeoutError('Calculation deadline')
            try:kind,payload=output.get_nowait()
            except queue.Empty:
                if not process.is_alive():
                    # Queue's feeder may still be delivering the final child message.
                    try:kind,payload=await asyncio.to_thread(output.get,True,1)
                    except queue.Empty:raise RuntimeError('Child exited without result')
                else:
                    if pending is not None and time.monotonic()-last_progress>=1:
                        if not await asyncio.to_thread(repo.write_progress,lease,pending):return
                        last_progress=time.monotonic();pending=None
                    await asyncio.sleep(.05);continue
            if kind=='progress':
                pending=payload
                if time.monotonic()-last_progress>=1:
                    if not await asyncio.to_thread(repo.write_progress,lease,payload):return
                    last_progress=time.monotonic();pending=None
            elif kind=='result':
                if pending is not None and not await asyncio.to_thread(repo.write_progress,lease,pending):return
                ref=await asyncio.to_thread(ctx['results'].save,lease,payload)
                await asyncio.to_thread(repo.complete,lease,ref);return
            elif kind=='permanent_error':
                await asyncio.to_thread(repo.fail,lease,payload,False);return
    except asyncio.CancelledError:
        await asyncio.to_thread(repo.fail,lease,'WORKER_INTERRUPTED',True);raise
    except Exception:
        try:await asyncio.to_thread(repo.fail,lease,'DEPENDENCY_OR_WORKER_FAILURE',True)
        except Exception:print('Job storage unavailable; lease recovery required',flush=True)
    finally:
        beat.cancel()
        try:await beat
        except asyncio.CancelledError:pass
        if process is not None:
            if process.is_alive():process.terminate()
            await asyncio.to_thread(process.join,5)
            if process.is_alive():process.kill();await asyncio.to_thread(process.join,5)
        if output is not None:output.close()

class WorkerSettings:
    functions=[execute_job]
    on_startup=startup
    on_shutdown=shutdown
    redis_settings=redis_settings()
    queue_name=QUEUE_NAME
    max_jobs=1
    max_tries=1
    keep_result=0
    job_timeout=630
