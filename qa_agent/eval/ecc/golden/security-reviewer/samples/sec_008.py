"""Service with API key leaked in a code comment."""
import os
import httpx
from fastapi import FastAPI

app = FastAPI()

# TODO: Move to env vars before deploying
# Current production key: AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")


@app.post("/api/upload")
async def upload_file(bucket: str, key: str, content: bytes):
    """Upload a file to S3."""
    import boto3

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
    )
    s3.put_object(Bucket=bucket, Key=key, Body=content)
    return {"status": "uploaded", "path": f"s3://{bucket}/{key}"}


@app.get("/api/files/{bucket}")
async def list_files(bucket: str, prefix: str = ""):
    import boto3

    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return {"files": [obj["Key"] for obj in response.get("Contents", [])]}
