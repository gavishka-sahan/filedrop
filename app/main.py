import os
import uuid
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from database import create_tables, get_db, File as FileModel
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.responses import StreamingResponse, RedirectResponse
import redis
import boto3
import json

redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

INSTANCE_ID = os.getenv("INSTANCE_ID", "unknown")
#UPLOAD_DIR = Path("/uploads")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET = os.getenv("MINIO_BUCKET")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", MINIO_ENDPOINT)
s3 = boto3.client(
    "s3",
    endpoint_url=f"http://{MINIO_ENDPOINT}",
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
)

s3_public = boto3.client(
    "s3",
    endpoint_url=f"http://{MINIO_PUBLIC_ENDPOINT}",
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
)

INSTANCE_ID = os.getenv("INSTANCE_ID", "unknown")

@asynccontextmanager
async def lifespan(app: FastAPI):
   #UPLOAD_DIR.mkdir(exist_ok=True)
    create_tables()
    yield

app = FastAPI(lifespan=lifespan)

Instrumentator().instrument(app).expose(app)

@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE_ID}

@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    file_id = uuid.uuid4()
    extension = Path(file.filename).suffix
    object_key = f"{file_id}{extension}"

    s3.upload_fileobj(file.file, MINIO_BUCKET, object_key)

    with get_db() as db:
        record = FileModel(
            id=file_id,
            filename=file.filename,
            stored_path=object_key,
            content_type=file.content_type,
        )
        db.add(record)
    return {
        "file_id": str(file_id),
        "download_url": f"/files/{file_id}",
    }

@app.get("/files/{file_id}")
def download_file(file_id: uuid.UUID):
    cache_key = f"file:{file_id}"

    try:
        cached = redis_client.get(cache_key)
    except redis.RedisError as e:
        print(f"[{INSTANCE_ID}] Redis unavailable on read: {e}")
        cached = None

    if cached:
        print(f"[{INSTANCE_ID}] CACHE HIT for {file_id}")
        metadata = json.loads(cached)
        object_key = metadata["object_key"]
        filename = metadata["filename"]
        content_type = metadata["content_type"]
    else:
        print(f"[{INSTANCE_ID}] CACHE MISS for {file_id}")
        with get_db() as db:
            record = db.get(FileModel, file_id)
            if not record:
                raise HTTPException(status_code=404, detail="File not found")
            object_key = record.stored_path
            filename = record.filename
            content_type = record.content_type

        try:
            redis_client.set(
                cache_key,
                json.dumps({
                    "object_key": object_key,
                    "filename": filename,
                    "content_type": content_type,
                }),
                ex=300,  # 5 minutes
            )
        except redis.RedisError as e:
            print(f"[{INSTANCE_ID}] Redis unavailable on write: {e}")

    url = s3_public.generate_presigned_url(
        "get_object",
        Params={"Bucket": MINIO_BUCKET, "Key": object_key},
        ExpiresIn=3600,
    )

    return RedirectResponse(url=url, status_code=302)


@app.get("/debug/redis")
def debug_redis():
    redis_client.set("test_key", "hello from filedrop")
    value = redis_client.get("test_key")
    return {"redis_value": value}
