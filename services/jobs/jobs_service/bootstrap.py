"""One-off bootstrap: apply the jobs schema, and create buckets when CREATE_BUCKETS=1.

Runs as the Compose `initialize` service locally and as a Helm pre-install/pre-upgrade
Job in Kubernetes. In the cloud the buckets come from Terraform, so CREATE_BUCKETS=0.
"""
import os
import boto3
from .config import repository

def main():
    if os.environ.get('CREATE_BUCKETS','1')=='1':
        client=boto3.client('s3',endpoint_url=os.environ.get('S3_ENDPOINT_URL'),region_name=os.environ.get('AWS_REGION','us-east-1'))
        existing={b['Name'] for b in client.list_buckets()['Buckets']}
        for bucket in (os.environ['DATASET_BUCKET'],os.environ['RESULT_BUCKET']):
            if bucket not in existing:client.create_bucket(Bucket=bucket)
    repository().migrate()
    print('Jobs schema initialized')

if __name__=='__main__':main()
