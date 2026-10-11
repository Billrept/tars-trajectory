"""Create private local-development credentials without replacing existing files."""
import secrets,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
path=root/'.env.local'
if path.exists():
    print('Keeping existing .env.local')
else:
    password=secrets.token_hex(24)
    values={'APP_ENV':'local','POSTGRES_PASSWORD':password,'S3_ACCESS_KEY':'tars_local','S3_SECRET_KEY':secrets.token_hex(24),'SERVICE_TOKEN':secrets.token_hex(32),'PUBLIC_API_URL':'http://localhost:8002','PUBLIC_EPHEMERIS_URL':'http://localhost:8001','PUBLIC_JOBS_URL':'http://localhost:8003','CORS_ORIGINS':'http://localhost:3000','EPHEMERIS_START':'2025-01-01','EPHEMERIS_END':'2060-01-01'}
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(''.join(f'{k}={v}\n' for k,v in values.items()))
    print('Created private .env.local')
