"""Verify only the loopback tars-local stack; never prints access credentials."""
import argparse,json,subprocess,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--restart-worker',action='store_true');parser.add_argument('--kill-worker',action='store_true');args=parser.parse_args()
http=httpx.Client(timeout=15,headers={'Origin':'http://localhost:3000'})
http.get('http://localhost:8003/api/v1/jobs') # mints the anonymous tars_uid cookie reused by every call below
evidence={'environment':'local-loopback','claims':{}}
for name,port in [('ephemeris',8001),('trajectory',8002),('jobs',8003)]:
    response=http.get(f'http://localhost:{port}/readyz');response.raise_for_status();evidence[name]=response.json()
http.get('http://localhost:3000/healthz').raise_for_status()
payload={'kind':'optimization_single','payload':{'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','population_size':6,'max_iterations':20,'seed':42}}
key=str(uuid.uuid4())
def submit(_):
    result=http.post('http://localhost:8003/api/v1/jobs',json=payload,headers={'Idempotency-Key':key});result.raise_for_status();return result.json()['job_id']
with ThreadPoolExecutor(max_workers=10) as pool:ids=list(pool.map(submit,range(50)))
assert len(set(ids))==1,'Duplicate admission created multiple jobs'
job_id=ids[0]
def status(jid):
    response=http.get(f'http://localhost:8003/api/v1/jobs/{jid}');response.raise_for_status();return response.json()
def wait(jid,seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        row=status(jid)
        if row['status']=='succeeded':return row
        if row['status']=='failed':raise RuntimeError(row['error'])
        time.sleep(.5)
    raise TimeoutError('Local verification job did not finish within the observation window')
row=wait(job_id)
result=http.get(f'http://localhost:8003/api/v1/jobs/{job_id}/result');result.raise_for_status();result=result.json()
assert result['seed']==42 and result['dataset_id']==row['dataset_id'] and result['solver_digest']==row['solver_digest']
evidence['claims'].update({'concurrent_requests':50,'logical_jobs':1,'result_seed':42,'dataset_id':row['dataset_id'],'solver_digest':row['solver_digest'],'job_id':job_id})
command=['docker','compose','--env-file',str(root/'.env.local'),'-p','tars-local']
if args.restart_worker:
    process=subprocess.Popen(command+['restart','worker'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    checks=[]
    while process.poll() is None:
        checks.append({'ephemeris':http.get('http://localhost:8001/bodies').status_code,'jobs':http.get(f'http://localhost:8003/api/v1/jobs/{job_id}').status_code,'frontend':http.get('http://localhost:3000/healthz').status_code})
        time.sleep(.1)
    assert process.returncode==0
    assert checks and all(all(code==200 for code in check.values()) for check in checks)
    evidence['claims']['independent_worker_restart']={'requests':len(checks),'all_nonworker_reads_200':True}
if args.kill_worker:
    payload['payload'].update({'population_size':100,'max_iterations':500})
    response=http.post('http://localhost:8003/api/v1/jobs',json=payload,headers={'Idempotency-Key':str(uuid.uuid4())});response.raise_for_status();killed_id=response.json()['job_id']
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        running=status(killed_id)
        if running['status']=='running' and running['progress']:break
        if running['status'] in ('failed','succeeded'):raise RuntimeError('Job finished before the crash drill could interrupt it')
        time.sleep(.25)
    else:raise TimeoutError('Worker did not begin the crash-drill calculation')
    started=time.monotonic()
    subprocess.run(command+['kill','-s','SIGKILL','worker'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    subprocess.run(command+['up','-d','--no-deps','worker'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    recovered=wait(killed_id,300)
    assert recovered['attempt']>=2 and recovered['seed']==42
    evidence['claims']['crash_recovery']={'job_id':killed_id,'attempts':recovered['attempt'],'elapsed_seconds':round(time.monotonic()-started,2),'seed_preserved':True}
folder=root/'artifacts/verification';folder.mkdir(parents=True,exist_ok=True)
path=folder/('local-'+str(time.time_ns())+'.json');path.write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2));print('Evidence:',path)
