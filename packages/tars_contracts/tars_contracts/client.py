"""Pinned ephemeris wire client; numerical dependencies load only for consumers."""
import hashlib,json
from functools import lru_cache
import httpx
from .ttl import TTLValue

class EphemerisClient:
    # active_ttl: seconds to reuse the active manifest, so trajectory requests and job
    # admissions don't each make a network call to the ephemeris service.
    def __init__(self,url,token,active_ttl=60):
        self.http=httpx.Client(base_url=url.rstrip('/'),headers={'X-Service-Token':token},timeout=10,limits=httpx.Limits(max_connections=10,max_keepalive_connections=5))
        self._active=TTLValue(self._fetch_active,active_ttl)
    def close(self):self.http.close()
    def _fetch_active(self):
        response=self.http.get('/internal/v1/active');response.raise_for_status();return response.json()
    def active_manifest(self):return self._active.get()
    def manifest(self,dataset_id):
        response=self.http.get(f'/internal/v1/datasets/{dataset_id}');response.raise_for_status()
        data=response.json();claimed=data.pop('dataset_id')
        if claimed!=dataset_id or hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=dataset_id:raise ValueError('Invalid remote manifest')
        if data['time_scale']!='TDB' or data['frame']!='ECLIPJ2000':raise ValueError('Unsupported dataset frame')
        return {'dataset_id':claimed,**data}
    @lru_cache(maxsize=2)
    def snapshot(self,dataset_id):
        from tars_core.arrays import decode_arrays
        from tars_core.ephemeris import EphemerisSnapshot
        manifest=self.manifest(dataset_id);bodies={}
        for bid,chunk in manifest['bodies'].items():
            response=self.http.get(f'/internal/v1/datasets/{dataset_id}/bodies/{bid}');response.raise_for_status()
            if len(response.content)!=chunk['bytes'] or hashlib.sha256(response.content).hexdigest()!=chunk['sha256']:raise ValueError('Invalid remote chunk')
            bodies[int(bid)]=decode_arrays(response.content)
        return EphemerisSnapshot(dataset_id,bodies)
