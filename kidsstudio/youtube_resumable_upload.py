"""YouTube resumable private video upload transport.

Requires an already-authorized OAuth access token with upload scope.
Does not change visibility after upload; initializes privacy as private.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024  # multiple of 256 KiB

class UploadError(RuntimeError):
    pass

def _request(req: Request, timeout: float):
    try:
        return urlopen(req, timeout=timeout)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise UploadError("YouTube upload request failed") from exc

def start_session(access_token: str, video_size: int, title: str, description: str = "", *, timeout: float = 30) -> str:
    if not access_token or "\n" in access_token or "\r" in access_token:
        raise ValueError("invalid access token")
    if video_size <= 0 or not title.strip():
        raise ValueError("video size and title required")
    metadata = json.dumps({
        "snippet": {"title": title, "description": description, "categoryId": "27"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": True},
    }).encode()
    url = UPLOAD_URL + "?" + urlencode({"uploadType": "resumable", "part": "snippet,status"})
    req = Request(url, data=metadata, method="POST", headers={
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(video_size),
    })
    with _request(req, timeout) as response:
        location = response.headers.get("Location")
    if not location or not location.startswith("https://www.googleapis.com/"):
        raise UploadError("invalid resumable upload session location")
    return location

def parse_range_offset(range_header: str | None, total: int) -> int:
    if not range_header:
        return 0
    if not range_header.startswith("bytes=0-"):
        raise UploadError("unexpected upload range")
    try:
        last = int(range_header[8:])
    except ValueError as exc:
        raise UploadError("invalid upload range") from exc
    if not 0 <= last < total:
        raise UploadError("upload range out of bounds")
    return last + 1

def upload_chunk(session_url: str, access_token: str, payload: bytes, start: int, total: int, *, timeout: float = 90) -> tuple[int, dict | None]:
    if not session_url.startswith("https://www.googleapis.com/"):
        raise ValueError("invalid upload session")
    if not payload or start < 0 or start + len(payload) > total:
        raise ValueError("invalid upload chunk")
    req = Request(session_url, data=payload, method="PUT", headers={
        "Authorization": "Bearer " + access_token,
        "Content-Length": str(len(payload)),
        "Content-Range": f"bytes {start}-{start + len(payload) - 1}/{total}",
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(64 * 1024)
            if response.status not in (200, 201):
                raise UploadError("unexpected completion status")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise UploadError("invalid completion payload")
            return total, result
    except HTTPError as exc:
        if exc.code == 308:
            return parse_range_offset(exc.headers.get("Range"), total), None
        raise UploadError("upload chunk rejected") from exc
    except (URLError, TimeoutError) as exc:
        raise UploadError("upload chunk transport failed") from exc

def upload_video(session_url: str, access_token: str, video_path: str | Path, *, offset: int = 0) -> dict:
    video = Path(video_path)
    total = video.stat().st_size
    if total <= 0 or not 0 <= offset < total:
        raise ValueError("invalid video or offset")
    with video.open("rb") as handle:
        while offset < total:
            handle.seek(offset)
            chunk = handle.read(CHUNK_SIZE)
            next_offset, result = upload_chunk(session_url, access_token, chunk, offset, total)
            if result is not None:
                if result.get("status", {}).get("privacyStatus") != "private":
                    raise UploadError("upload response not private")
                return result
            if next_offset <= offset:
                raise UploadError("upload made no progress")
            offset = next_offset
    raise UploadError("upload completed without video receipt")
