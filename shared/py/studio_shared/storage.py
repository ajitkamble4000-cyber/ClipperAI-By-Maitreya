"""S3-compatible object storage (Cloudflare R2 in production).

Key layout:
  uploads/{user_id}/{upload_id}/{filename}   browser uploads (sources, voiceovers, music, images)
  sources/{project_id}/...                   ingested source media (auto-deleted after N days)
  cache/transcripts/{hash}-{model}.json      transcript cache
  projects/{project_id}/...                  clips, scene assets, renders (kept)
  jobs/{job_id}/...                          intermediate step outputs (for resume)
  assets/{hash}.{ext}                        content-addressed generated assets
  settings/cookies.txt.enc                   encrypted yt-dlp cookies
"""

from __future__ import annotations

import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import get_settings

MIN_PART = 8 * 1024**2
MAX_PARTS = 10_000


def _client(endpoint: str) -> BaseClient:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=s.s3_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "standard"},
            # R2 does not support the newer default CRC checksums on presigned URLs.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


@lru_cache
def client() -> BaseClient:
    return _client(get_settings().s3_endpoint)


@lru_cache
def presign_client() -> BaseClient:
    s = get_settings()
    return _client(s.s3_public_endpoint or s.s3_endpoint)


def bucket() -> str:
    return get_settings().s3_bucket


def ensure_bucket() -> None:
    try:
        client().head_bucket(Bucket=bucket())
    except ClientError:
        client().create_bucket(Bucket=bucket())


def choose_part_size(size: int) -> int:
    part = MIN_PART
    while size / part > MAX_PARTS:
        part *= 2
    # Bigger parts for big files = fewer requests; cap at 64 MB for resumability.
    if size > 1024**3:
        part = max(part, 32 * 1024**2)
    return part


# ---------------------------------------------------------------- multipart (browser uploads)
def create_multipart(key: str, content_type: str) -> str:
    r = client().create_multipart_upload(Bucket=bucket(), Key=key, ContentType=content_type)
    return str(r["UploadId"])


def presign_part(key: str, upload_id: str, part_number: int, expires: int = 3600) -> str:
    return str(
        presign_client().generate_presigned_url(
            "upload_part",
            Params={"Bucket": bucket(), "Key": key, "UploadId": upload_id, "PartNumber": part_number},
            ExpiresIn=expires,
        )
    )


def list_parts(key: str, upload_id: str) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    marker = 0
    while True:
        r = client().list_parts(Bucket=bucket(), Key=key, UploadId=upload_id, PartNumberMarker=marker)
        parts += [
            {"part_number": p["PartNumber"], "etag": p["ETag"], "size": p["Size"]} for p in r.get("Parts", [])
        ]
        if not r.get("IsTruncated"):
            return parts
        marker = r["NextPartNumberMarker"]


def complete_multipart(key: str, upload_id: str, parts: list[dict[str, Any]]) -> None:
    client().complete_multipart_upload(
        Bucket=bucket(),
        Key=key,
        UploadId=upload_id,
        MultipartUpload={
            "Parts": [
                {"PartNumber": int(p["part_number"]), "ETag": str(p["etag"])}
                for p in sorted(parts, key=lambda p: int(p["part_number"]))
            ]
        },
    )


def abort_multipart(key: str, upload_id: str) -> None:
    try:
        client().abort_multipart_upload(Bucket=bucket(), Key=key, UploadId=upload_id)
    except ClientError:
        pass


# ---------------------------------------------------------------- objects
def presign_get(key: str, expires: int = 900, filename: str | None = None) -> str:
    params: dict[str, Any] = {"Bucket": bucket(), "Key": key}
    if filename:
        safe = filename.replace('"', "")
        params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
    return str(presign_client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires))


def presign_put(key: str, content_type: str, expires: int = 900) -> str:
    return str(
        presign_client().generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket(), "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )
    )


def upload_file(path: Path | str, key: str, content_type: str | None = None) -> str:
    ct = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    client().upload_file(str(path), bucket(), key, ExtraArgs={"ContentType": ct})
    return key


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)
    return key


def get_bytes(key: str) -> bytes:
    return bytes(client().get_object(Bucket=bucket(), Key=key)["Body"].read())


def download_file(key: str, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    client().download_file(bucket(), key, str(p))
    return p


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError:
        return False


def head(key: str) -> dict[str, Any]:
    r = client().head_object(Bucket=bucket(), Key=key)
    return {"size": r["ContentLength"], "content_type": r.get("ContentType")}


def delete(key: str) -> None:
    client().delete_object(Bucket=bucket(), Key=key)


def delete_prefix(prefix: str) -> int:
    n = 0
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            client().delete_objects(Bucket=bucket(), Delete={"Objects": objs})
            n += len(objs)
    return n
