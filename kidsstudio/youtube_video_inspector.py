"""Read-only YouTube Data API video inspector. Never changes visibility."""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .youtube_release_plan import VIDEO_ID_RE

API_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_RESPONSE = 128 * 1024

class YouTubeInspectError(RuntimeError):
    pass

def parse_video_response(payload: dict, expected_video_id: str) -> dict:
    if not isinstance(payload, dict):
        raise YouTubeInspectError("invalid YouTube response")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise YouTubeInspectError("video missing or inaccessible")
    video = items[0]
    if not isinstance(video, dict) or video.get("id") != expected_video_id:
        raise YouTubeInspectError("video identity mismatch")
    snippet = video.get("snippet")
    status = video.get("status")
    if not isinstance(snippet, dict) or not isinstance(status, dict):
        raise YouTubeInspectError("missing required video fields")
    channel_id = snippet.get("channelId")
    privacy = status.get("privacyStatus")
    if not isinstance(channel_id, str) or not channel_id:
        raise YouTubeInspectError("missing channel ID")
    if privacy not in ("private", "unlisted", "public"):
        raise YouTubeInspectError("unknown privacy status")
    return {"video_id": expected_video_id, "channel_id": channel_id, "privacy": privacy, "read_only": True}

def inspect_video(video_id: str, access_token: str, *, timeout: float = 10) -> dict:
    """Fetch current privacy via OAuth bearer; token must have YouTube read permission."""
    if not isinstance(video_id, str) or VIDEO_ID_RE.fullmatch(video_id) is None:
        raise ValueError("invalid YouTube video ID")
    if not isinstance(access_token, str) or not access_token.strip() or "\r" in access_token or "\n" in access_token:
        raise ValueError("invalid access token")
    url = API_URL + "?" + urlencode({"part": "snippet,status", "id": video_id})
    request = Request(url, headers={
        "Authorization": "Bearer " + access_token,
        "Accept": "application/json",
    }, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise YouTubeInspectError("YouTube status request failed") from exc
    if len(raw) > MAX_RESPONSE:
        raise YouTubeInspectError("YouTube response too large")
    try:
        return parse_video_response(json.loads(raw), video_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise YouTubeInspectError("invalid YouTube JSON") from exc
