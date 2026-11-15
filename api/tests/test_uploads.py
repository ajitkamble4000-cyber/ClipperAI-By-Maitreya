"""Resumable multipart upload: init, partial upload, resume via list, complete."""

from __future__ import annotations

import os

import httpx
import pytest
from studio_shared import storage

pytestmark = pytest.mark.integration


def test_resumable_multipart_upload(client, make_member):
    _, _, hdr = make_member()
    size = 8 * 1024**2 * 2 + 12345  # 3 parts of 8 MB
    data = os.urandom(size)
    r = client.post(
        "/uploads",
        json={"filename": "../evil name.mp4", "size": size, "content_type": "video/mp4"},
        headers=hdr,
    )
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["part_count"] == 3 and up["filename"] == "evil name.mp4"
    part = up["part_size"]

    # Upload only part 1, then "refresh the page".
    urls = client.post(f"/uploads/{up['id']}/parts", json={"part_numbers": [1, 2, 3]}, headers=hdr).json()[
        "urls"
    ]
    httpx.put(urls["1"], content=data[:part]).raise_for_status()

    resumed = client.get(f"/uploads/{up['id']}", headers=hdr).json()
    assert [p["part_number"] for p in resumed["parts"]] == [1]
    assert any(u["id"] == up["id"] for u in client.get("/uploads", headers=hdr).json())

    etags = {p["part_number"]: p["etag"] for p in resumed["parts"]}
    urls = client.post(f"/uploads/{up['id']}/parts", json={"part_numbers": [2, 3]}, headers=hdr).json()[
        "urls"
    ]
    for n in (2, 3):
        resp = httpx.put(urls[str(n)], content=data[(n - 1) * part : n * part])
        resp.raise_for_status()
        etags[n] = resp.headers["etag"]

    done = client.post(
        f"/uploads/{up['id']}/complete",
        json={"parts": [{"part_number": n, "etag": e} for n, e in etags.items()]},
        headers=hdr,
    )
    assert done.status_code == 200, done.text
    key = f"uploads/{done.json()['id']}"
    row_key = [k for k in [storage.client().list_objects_v2(Bucket=storage.bucket(), Prefix="uploads/")]][0]
    assert row_key["KeyCount"] >= 1
    from studio_shared import db

    k = db.fetch_one("select r2_key from uploads where id = %s", [up["id"]])["r2_key"]
    assert storage.get_bytes(k) == data
    assert key


@pytest.mark.parametrize(
    "body,msg",
    [
        ({"filename": "a.exe", "size": 10, "content_type": "video/mp4"}, "not allowed"),
        ({"filename": "a.mp4", "size": 5 * 1024**3, "content_type": "video/mp4"}, "up to 1 GB"),
        ({"filename": "a.mp4", "size": 10, "content_type": "text/html"}, "not allowed"),
    ],
)
def test_upload_validation(client, make_member, body, msg):
    _, _, hdr = make_member()
    r = client.post("/uploads", json=body, headers=hdr)
    assert r.status_code in (400, 403) and msg in r.json()["detail"]


def test_sign_rejects_settings_and_other_users(client, make_member):
    _, _, hdr = make_member()
    assert (
        client.get("/files/sign", params={"key": "settings/cookies.txt.enc"}, headers=hdr).status_code == 403
    )
    assert (
        client.get("/files/sign", params={"key": "uploads/someone-else/x.mp4"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.get("/files/sign", params={"key": "projects/x/clip.mp4"}, headers=hdr).status_code == 403
    )  # not theirs
    assert client.get("/files/sign", params={"key": "library/music/a.mp3"}, headers=hdr).status_code == 200
