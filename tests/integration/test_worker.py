import asyncio,multiprocessing,time
from tars_contracts.requests import JobSubmission,normalize_submission
from jobs_service.results import ResultStore

def test_real_cpu_worker_commits_seeded_result_after_queue_delivery(repo,ephemeris,dataset_store,service_env):
    from jobs_service.worker import execute_job
    payload=normalize_submission(JobSubmission(kind='optimization_single',payload={'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','population_size':6,'max_iterations':10,'seed':42}))['payload']
    manifest=ephemeris.active_manifest()
    job,_=repo.admit('alice','optimization_single','worker-result-request',payload,manifest['dataset_id'],42)
    results=ResultStore(dataset_store.client,dataset_store.bucket)
    ctx={'repo':repo,'results':results,'ephemeris':ephemeris,'worker_id':'cpu-test-worker'}
    asyncio.run(execute_job(ctx,job['job_id'],0))
    final=repo.get('alice',job['job_id'])
    assert final['status']=='succeeded',final
    result=results.load(job['job_id'],final['result_ref'])
    assert result['seed']==42 and result['dataset_id']==manifest['dataset_id']
    assert result['solver_digest']==job['solver_digest']
    assert len(result['trajectory_points'])>20
    assert not multiprocessing.active_children()

import pytest
@pytest.mark.parametrize('kind,payload',[
    ('plan',{'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2027-06-01'}),
    ('porkchop',{'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','dep_steps':10,'tof_steps':10,'tof_min_days':120,'tof_max_days':250}),
    ('optimization_multi',{'body_sequence':['earth','mars'],'dep_start':'2026-06-01','dep_end':'2026-08-01','leg_tof_bounds':[[120,250]],'population_size':6,'max_iterations':10,'seed':42}),
])
def test_other_job_kinds_commit_pinned_result(kind,payload,repo,ephemeris,dataset_store,service_env):
    from jobs_service.worker import execute_job
    normalized=normalize_submission(JobSubmission(kind=kind,payload=payload))['payload']
    manifest=ephemeris.active_manifest()
    job,_=repo.admit('alice',kind,'verified-job-kind-'+kind,normalized,manifest['dataset_id'],42)
    results=ResultStore(dataset_store.client,dataset_store.bucket)
    asyncio.run(execute_job({'repo':repo,'results':results,'ephemeris':ephemeris,'worker_id':'kind-worker'},job['job_id'],0))
    final=repo.get('alice',job['job_id']);assert final['status']=='succeeded',final
    result=results.load(job['job_id'],final['result_ref'])
    assert result['seed']==42 and result['dataset_id']==manifest['dataset_id']
    assert result['solver_digest']==job['solver_digest']
    if kind=='plan':assert result['count']>0
    if kind=='optimization_multi':assert len(result['legs'])==1
    assert not multiprocessing.active_children()
