"""Verify the public ephemeris stream on loopback only."""
import json
from pathlib import Path
import httpx
from websockets.sync.client import connect
h=httpx.Client(timeout=15)
b=h.get('http://localhost:8001/epoch-range').json()
with connect('ws://localhost:8001/ws/ephemeris/stream',origin='http://localhost:3000') as ws:
    ws.send(json.dumps({'body_ids':[399,499],'start_iso':b['start_iso'],'speed':0,'fps':1}))
    event=json.loads(ws.recv(timeout=10));assert len(event['bodies'])==2
report={'ephemeris_stream':{'bodies':len(event['bodies']),'dataset_id':event['dataset_id'],'epoch_iso':event['epoch_iso']}}
Path('artifacts/verification/live-streams.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
