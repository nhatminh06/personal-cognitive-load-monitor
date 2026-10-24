"""Idempotently initialize local lake buckets."""

import os

import boto3
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    region_name="us-east-1",
    config=Config(s3={"addressing_style": "path"}),
)
existing = {bucket["Name"] for bucket in client.list_buckets()["Buckets"]}
for name in (os.environ["MINIO_BRONZE_BUCKET"], os.environ["MINIO_LAKEHOUSE_BUCKET"]):
    if name not in existing:
        client.create_bucket(Bucket=name)
    print(f"bucket_ready={name}")
