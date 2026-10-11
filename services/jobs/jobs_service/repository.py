"""PostgreSQL is the admission and execution authority; Redis can be lost."""
import hashlib,json,os,re,secrets,uuid
from pathlib import Path
from sqlalchemy import create_engine,text
from tars_core import SOLVER_DIGEST

class IdempotencyConflict(ValueError): pass
class QuotaExceeded(ValueError): pass
class GlobalCapReached(ValueError): pass

def encode(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def row_dict(row):
    if row is None:return None
    value=dict(row);value['job_id']=str(value.pop('id'))
    for field in ('created_at','updated_at','ended_at','lease_until'):
        if value.get(field) is not None:value[field]=value[field].isoformat()
    return value

class JobRepository:
    def __init__(self,url,schema='tars_jobs'):
        if not re.fullmatch('[a-z][a-z0-9_]*',schema):raise ValueError('Invalid schema name')
        self.schema=schema
        self.engine=create_engine(url.replace('postgresql://','postgresql+psycopg://',1),pool_size=10,max_overflow=0,pool_timeout=5,pool_pre_ping=True,connect_args={'options':f'-csearch_path={schema}','connect_timeout':5})

    def migrate(self):
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(72131984)'))
            c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
            c.exec_driver_sql(Path(__file__).with_name('schema.sql').read_text())

    def admit(self,owner,kind,key,payload,dataset_id,seed=None):
        if not 16<=len(key)<=128 or any(ord(x)<32 or ord(x)>126 for x in key):raise ValueError('Invalid idempotency key')
        fingerprint=hashlib.sha256(encode({'kind':kind,'payload':payload}).encode()).hexdigest()
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,0))'),{'owner':owner})
            old=c.execute(text('SELECT * FROM jobs WHERE owner=:owner AND kind=:kind AND schema_version=\'1\' AND idempotency_key=:key'),{'owner':owner,'kind':kind,'key':key}).mappings().first()
            if old:
                if old['fingerprint']!=fingerprint:raise IdempotencyConflict('Key already used for another request')
                return row_dict(old),False
            pending=c.execute(text('SELECT count(*) FROM jobs WHERE owner=:owner AND status=\'queued\''),{'owner':owner}).scalar()
            daily=c.execute(text('SELECT count(*) FROM jobs WHERE owner=:owner AND created_at>=date_trunc(\'day\',now())'),{'owner':owner}).scalar()
            if pending>=3 or daily>=50:raise QuotaExceeded('Job admission quota exceeded')
            if c.execute(text("SELECT count(*) FROM jobs WHERE status='queued'")).scalar()>=int(os.environ.get('GLOBAL_QUEUE_CAP','25')):raise GlobalCapReached('Global queued-job cap reached')
            job_id=str(uuid.uuid4())
            row=c.execute(text('INSERT INTO jobs(id,owner,kind,idempotency_key,fingerprint,payload,dataset_id,seed,solver_digest) VALUES(:id,:owner,:kind,:key,:fingerprint,CAST(:payload AS jsonb),:dataset,:seed,:digest) RETURNING *'),{'id':job_id,'owner':owner,'kind':kind,'key':key,'fingerprint':fingerprint,'payload':encode(payload),'dataset':dataset_id,'seed':seed if seed is not None else secrets.randbits(32),'digest':SOLVER_DIGEST}).mappings().one()
            c.execute(text('INSERT INTO outbox(job_id) VALUES(:id)'),{'id':job_id})
            return row_dict(row),True

    def get(self,owner,job_id):
        with self.engine.connect() as c:
            return row_dict(c.execute(text('SELECT * FROM jobs WHERE id=:id AND owner=:owner'),{'id':job_id,'owner':owner}).mappings().first())

    def list(self,owner,limit):
        with self.engine.connect() as c:
            rows=c.execute(text('SELECT id, kind, status, payload, created_at FROM jobs WHERE owner=:owner ORDER BY created_at DESC LIMIT :limit'),{'owner':owner,'limit':limit}).mappings().all()
        return [{'job_id':str(row['id']),'kind':row['kind'],'status':row['status'],'payload':row['payload'],'created_at':row['created_at']} for row in rows]

    def replay(self,owner,kind,key,payload):
        fingerprint=hashlib.sha256(encode({'kind':kind,'payload':payload}).encode()).hexdigest()
        with self.engine.connect() as c:
            row=c.execute(text('SELECT * FROM jobs WHERE owner=:owner AND kind=:kind AND schema_version=\'1\' AND idempotency_key=:key'),{'owner':owner,'kind':kind,'key':key}).mappings().first()
        if row and row['fingerprint']!=fingerprint:raise IdempotencyConflict('Key already used for another request')
        return row_dict(row)

    def load(self,job_id):
        with self.engine.connect() as c:return row_dict(c.execute(text('SELECT * FROM jobs WHERE id=:id'),{'id':job_id}).mappings().first())

    def claim(self,job_id,worker_id,generation=None):
        with self.engine.begin() as c:
            owner=c.execute(text('SELECT owner FROM jobs WHERE id=:id'),{'id':job_id}).scalar()
            if owner is None:return None
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,0))'),{'owner':owner})
            row=c.execute(text('SELECT * FROM jobs WHERE id=:id FOR UPDATE'),{'id':job_id}).mappings().one()
            if generation is not None and row['fencing_token']!=generation:return None
            if row['status']!='queued' or row['attempt']>=3:return None
            active=c.execute(text('SELECT count(*) FROM jobs WHERE owner=:owner AND status=\'running\' AND lease_until>now()'),{'owner':owner}).scalar()
            if active>=2:return None
            row=c.execute(text('UPDATE jobs SET status=\'running\', attempt=attempt+1,fencing_token=fencing_token+1,worker_id=:worker,lease_until=now()+interval \'90 seconds\',sequence=sequence+1,updated_at=now() WHERE id=:id RETURNING *'),{'id':job_id,'worker':worker_id}).mappings().one()
            c.execute(text('INSERT INTO attempts(job_id,fencing_token,worker_id) VALUES(:id,:token,:worker)'),{'id':job_id,'token':row['fencing_token'],'worker':worker_id})
            return row_dict(row)

    def _update(self,lease,assignments,params=None):
        values={'id':lease['job_id'],'token':lease['fencing_token'],'worker':lease['worker_id'],**(params or {})}
        with self.engine.begin() as c:
            return c.execute(text(f'UPDATE jobs SET {assignments},sequence=sequence+1,updated_at=now() WHERE id=:id AND status=\'running\' AND fencing_token=:token AND worker_id=:worker AND lease_until>now()'),values).rowcount==1

    def heartbeat(self,lease):
        return self._update(lease,'lease_until=now()+interval \'90 seconds\'')

    def write_progress(self,lease,progress):
        return self._update(lease,'progress=CAST(:progress AS jsonb)',{'progress':encode(progress)})

    def complete(self,lease,result_ref):
        ok=self._update(lease,'status=\'succeeded\',result_ref=CAST(:result AS jsonb),ended_at=now(),lease_until=NULL',{'result':encode(result_ref)})
        if ok:self._finish_attempt(lease,'succeeded')
        return ok

    def fail(self,lease,error,retry=False):
        status='queued' if retry and lease['attempt']<3 else 'failed'
        ok=self._update(lease,'status=:status,error=:error,lease_until=NULL,ended_at=CASE WHEN :status=\'failed\' THEN now() ELSE NULL END',{'status':status,'error':error})
        if ok:
            self._finish_attempt(lease,'failed',error)
            if status=='queued':
                with self.engine.begin() as c:c.execute(text('UPDATE outbox SET sent_at=NULL,lease_until=NULL,claim_token=NULL WHERE job_id=:id'),{'id':lease['job_id']})
        return ok

    def _finish_attempt(self,lease,status,error=None):
        with self.engine.begin() as c:c.execute(text('UPDATE attempts SET status=:status,error=:error,ended_at=now() WHERE job_id=:id AND fencing_token=:token'),{'status':status,'error':error,'id':lease['job_id'],'token':lease['fencing_token']})

    def reconcile(self):
        with self.engine.begin() as c:
            expired=c.execute(text('UPDATE jobs SET status=CASE WHEN attempt<3 THEN \'queued\' ELSE \'failed\' END,error=\'LEASE_EXPIRED\',ended_at=CASE WHEN attempt>=3 THEN now() ELSE NULL END,lease_until=NULL,worker_id=NULL,sequence=sequence+1,updated_at=now() WHERE status=\'running\' AND lease_until<=now() RETURNING id')).all()
            c.execute(text('UPDATE outbox SET sent_at=NULL,lease_until=NULL,claim_token=NULL WHERE job_id IN (SELECT id FROM jobs WHERE status=\'queued\') AND (lease_until IS NULL OR lease_until<=now())'))
            return len(expired)

    def pending_outbox(self):
        token=str(uuid.uuid4())
        with self.engine.begin() as c:
            rows=c.execute(text('UPDATE outbox SET claim_token=:token,lease_until=now()+interval \'30 seconds\' WHERE job_id IN (SELECT o.job_id FROM outbox o JOIN jobs j ON j.id=o.job_id WHERE j.status=\'queued\' AND o.sent_at IS NULL AND (o.lease_until IS NULL OR o.lease_until<now()) FOR UPDATE OF o SKIP LOCKED LIMIT 16) RETURNING job_id'),{'token':token}).all()
        return [(str(row[0]),token) for row in rows]

    def mark_sent(self,job_id,token):
        with self.engine.begin() as c:
            return c.execute(text('UPDATE outbox SET sent_at=now(),lease_until=NULL WHERE job_id=:id AND claim_token=:token'),{'id':job_id,'token':token}).rowcount==1

    def cleanup(self):
        with self.engine.begin() as c:
            return c.execute(text('DELETE FROM jobs WHERE status IN (\'succeeded\',\'failed\') AND ended_at<now()-interval \'30 days\' AND result_ref IS NULL')).rowcount
