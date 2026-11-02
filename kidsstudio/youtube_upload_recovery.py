"""Reconcile upload offset against YouTube before resuming an interrupted session."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .youtube_resumable_upload import UploadError, parse_range_offset, upload_video
from .youtube_upload_session import load_session

def query_upload_progress(session_url: str, access_token: str, total: int, *, timeout: float = 30) -> tuple[int, dict | None]:
    if not session_url.startswith("https://www.googleapis.com/") or total <= 0:
        raise ValueError("invalid upload session")
    req = Request(session_url, data=b"", method="PUT", headers={
        "Authorization": "Bearer " + access_token,
        "Content-Length": "0",
        "Content-Range": f"bytes */{total}",
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            if response.status not in (200, 201):
                raise UploadError("unexpected upload status")
            result = json.loads(response.read(64 * 1024))
            if not isinstance(result, dict):
                raise UploadError("invalid completion response")
            return total, result
    except HTTPError as exc:
        if exc.code == 308:
            return parse_range_offset(exc.headers.get("Range"), total), None
        raise UploadError("upload progress query failed") from exc
    except (URLError, TimeoutError) as exc:
        raise UploadError("upload progress transport failed") from exc

def resume_saved_upload(session_path: str | Path, access_token: str) -> dict:
    saved = load_session(session_path)
    offset, receipt = query_upload_progress(saved["session_url"], access_token, saved["video_size"])
    if receipt is not None:
        if receipt.get("status", {}).get("privacyStatus") != "private":
            raise UploadError("completed video is not private")
        return receipt
    if offset >= saved["video_size"]:
        raise UploadError("server reported complete without receipt")
    return upload_video(saved["session_url"], access_token, saved["video_path"], offset=offset)
