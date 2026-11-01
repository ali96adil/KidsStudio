"""Opt-in Cloudflare Workers AI image generation; never called by default."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib import error, request


class CloudflareImageError(RuntimeError):
    pass


def generate_image(
    prompt: str,
    destination: str | Path,
    *,
    model: str,
    account_id: str | None = None,
    api_token: str | None = None,
    enabled: bool = False,
    timeout: int = 90,
    max_bytes: int = 12_000_000,
) -> Path:
    """Write a generated image to an explicit destination after opt-in.

    The caller must verify model support, license and quota beforehand.
    Never log the bearer token. Does not implement automatic paid fallback.
    """
    if not enabled:
        raise CloudflareImageError("Cloudflare image generation is disabled")
    account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account_id or not api_token:
        raise CloudflareImageError("Missing Cloudflare credentials")
    if not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Prompt must contain 1-4000 characters")
    if not model.startswith("@cf/") or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@/._-" for c in model):
        raise ValueError("Invalid Workers AI model identifier")
    if not account_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid account identifier")
    if max_bytes < 8:
        raise ValueError("max_bytes too small")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    req = request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "image/*, application/json",
    }, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    except (error.URLError, TimeoutError) as exc:
        raise CloudflareImageError("Cloudflare request failed") from exc
    if len(data) > max_bytes:
        raise CloudflareImageError("Image response exceeds size limit")
    if mime == "application/json":
        try:
            result = json.loads(data)
            encoded = result.get("result", {}).get("image")
            if not isinstance(encoded, str):
                raise ValueError("Missing image")
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError, AttributeError) as exc:
            raise CloudflareImageError("Unexpected JSON image response") from exc
    if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff") or data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        raise CloudflareImageError("Unsupported or invalid image payload")
    if len(data) > max_bytes:
        raise CloudflareImageError("Decoded image exceeds size limit")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as out:
        out.write(data)
    return destination
