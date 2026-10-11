"""One-off local bootstrap; production migrations run under a separate role."""
import os
import boto3
from jobs_service.config import repository

client=boto3.client('s3',endpoint_url=os.environ.get('S3_ENDPOINT_URL'),region_name=os.environ.get('AWS_REGION','us-east-1'))
for bucket in (os.environ['DATASET_BUCKET'],os.environ['RESULT_BUCKET']):
    existing={b['Name'] for b in client.list_buckets()['Buckets']}
    if bucket not in existing:client.create_bucket(Bucket=bucket)
repository().migrate()
print('Local buckets and jobs schema initialized')
