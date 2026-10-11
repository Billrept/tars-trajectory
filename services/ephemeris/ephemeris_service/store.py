"""Immutable S3 datasets with a disposable Redis read cache."""
import hashlib,io,json,random,zipfile
import numpy as np
from botocore.exceptions import ClientError
from redis.exceptions import RedisError
from tars_core.ephemeris import EphemerisSnapshot

from tars_core.arrays import decode_arrays

class DatasetStore:
    def __init__(self,client,bucket,cache,prefix='tars:local'):
        self.client,self.bucket,self.cache,self.prefix=client,bucket,cache,prefix
    def cache_key(self,dataset_id,body_id):return f'{self.prefix}:ephem:v1:{dataset_id}:{body_id}'
    def _get(self,key):
        return self.client.get_object(Bucket=self.bucket,Key=key)['Body'].read()
    def _put_once(self,key,raw,content_type):
        try:self.client.put_object(Bucket=self.bucket,Key=key,Body=raw,ContentType=content_type,IfNoneMatch='*')
        except ClientError as e:
            if e.response['ResponseMetadata']['HTTPStatusCode']!=412:raise
            if self._get(key)!=raw:raise ValueError('Immutable object conflict')
    def active_manifest(self):
        pointer=json.loads(self._get('active.json'))
        return self.manifest(pointer['dataset_id'])
    def manifest(self,dataset_id):
        if len(dataset_id)!=64 or any(c not in '0123456789abcdef' for c in dataset_id):raise ValueError('Invalid dataset ID')
        manifest=json.loads(self._get(f'datasets/{dataset_id}/manifest.json'))
        claimed=manifest.pop('dataset_id')
        if claimed!=dataset_id or hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=dataset_id:
            raise ValueError('Invalid manifest checksum')
        return {'dataset_id':claimed,**manifest}
    def publish(self,bodies,provenance):
        required=set(provenance.get('required_bodies',bodies))
        if set(bodies)!=required:raise ValueError('Incomplete dataset')
        if provenance.get('query_time_type', '').startswith('UT'):
            from tars_contracts.horizons import validate_epoch_grid
            for arrays in bodies.values():
                validate_epoch_grid(arrays['epochs'],provenance['start'],provenance['end'],provenance['step_days'])
        snapshot=EphemerisSnapshot('candidate',bodies)
        chunks={}
        manifest={'schema_version':'1','frame':'ECLIPJ2000','center':'500@10','units':'KM-S','time_scale':'TDB','provenance':provenance,'bodies':{}}
        for bid,arrays in snapshot._data.items():
            out=io.BytesIO();np.savez_compressed(out,**arrays);raw=out.getvalue();decode_arrays(raw)
            chunks[bid]=raw
            start,end=snapshot.get_epoch_range(bid)
            manifest['bodies'][str(bid)]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'start_jd':start,'end_jd':end}
        dataset_id=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for bid,raw in chunks.items():
            self._put_once(f'datasets/{dataset_id}/{bid}.npz',raw,'application/octet-stream')
            try:self.cache.setex(self.cache_key(dataset_id,bid),int(86400*random.uniform(.9,1.1)),raw)
            except RedisError:pass
        self._put_once(f'datasets/{dataset_id}/manifest.json',json.dumps({'dataset_id':dataset_id,**manifest},sort_keys=True,separators=(',',':')).encode(),'application/json')
        try:
            old=self.client.get_object(Bucket=self.bucket,Key='active.json')
            condition={'IfMatch':old['ETag']};old['Body'].close()
        except ClientError as e:
            if e.response['ResponseMetadata']['HTTPStatusCode']!=404:raise
            condition={'IfNoneMatch':'*'}
        self.client.put_object(Bucket=self.bucket,Key='active.json',Body=json.dumps({'dataset_id':dataset_id}).encode(),ContentType='application/json',**condition)
        return dataset_id
    def body_bytes(self,dataset_id,body_id,manifest=None):
        manifest=manifest or self.manifest(dataset_id)
        expected=manifest['bodies'][str(body_id)]
        key=self.cache_key(dataset_id,body_id)
        try:raw=self.cache.get(key)
        except RedisError:raw=None
        if raw is None or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
            raw=self._get(f'datasets/{dataset_id}/{body_id}.npz')
            if len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise ValueError('Corrupt dataset chunk')
            try:self.cache.setex(key,int(86400*random.uniform(.9,1.1)),raw)
            except RedisError:pass
        return raw
    def snapshot(self,dataset_id,body_ids=None):
        manifest=self.manifest(dataset_id)
        ids=body_ids if body_ids is not None else map(int,manifest['bodies'])
        return EphemerisSnapshot(dataset_id,{bid:decode_arrays(self.body_bytes(dataset_id,bid,manifest)) for bid in ids})
