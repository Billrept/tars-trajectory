import os
import boto3
from arq.connections import RedisSettings
from .repository import JobRepository
from .results import ResultStore
from tars_core import SOLVER_DIGEST

QUEUE_NAME=f'tars:{os.environ.get("APP_ENV","local")}:jobs:1:1.0.0:{SOLVER_DIGEST[:16]}'

def queue_for(row):return f'tars:{os.environ.get("APP_ENV","local")}:jobs:{row["schema_version"]}:{row["solver_version"]}:{row["solver_digest"][:16]}'

def redis_settings():
    settings=RedisSettings.from_dsn(os.environ['QUEUE_REDIS_URL'])
    if settings.ssl and os.environ.get('QUEUE_REDIS_CA_CERT'):settings.ssl_ca_certs=os.environ['QUEUE_REDIS_CA_CERT'] # managed Redis private CA
    return settings
def repository():return JobRepository(os.environ['DATABASE_URL'],os.environ.get('DATABASE_SCHEMA','tars_jobs'))
def result_store():return ResultStore(boto3.client('s3',endpoint_url=os.environ.get('S3_ENDPOINT_URL'),region_name=os.environ.get('AWS_REGION','us-east-1')),os.environ['RESULT_BUCKET'])
