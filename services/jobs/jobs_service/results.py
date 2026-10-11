import hashlib,json
from botocore.exceptions import ClientError

class ResultStore:
    def __init__(self,client,bucket):self.client,self.bucket=client,bucket
    def _put(self,key,raw):
        try:self.client.put_object(Bucket=self.bucket,Key=key,Body=raw,ContentType='application/json',IfNoneMatch='*')
        except ClientError as e:
            if e.response['ResponseMetadata']['HTTPStatusCode']!=412:raise
            if self.client.get_object(Bucket=self.bucket,Key=key)['Body'].read()!=raw:raise ValueError('Immutable result conflict')
    def save(self,lease,result):
        raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        sha=hashlib.sha256(raw).hexdigest();job_id=lease['job_id']
        self._put(f'attempts/{job_id}/{lease["fencing_token"]}/{sha}.json',raw)
        key=f'results/{job_id}/{sha}.json';self._put(key,raw)
        return {'object_key':key,'sha256':sha,'bytes':len(raw),'schema_version':'1','dataset_id':lease['dataset_id'],'solver_version':lease['solver_version'],'solver_digest':lease['solver_digest'],'seed':lease['seed']}
    def load(self,job_id,ref):
        if not ref['object_key'].startswith(f'results/{job_id}/'):raise ValueError('Invalid result owner reference')
        raw=self.client.get_object(Bucket=self.bucket,Key=ref['object_key'])['Body'].read()
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Corrupt result')
        return json.loads(raw)
