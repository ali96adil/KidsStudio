"""Bounded retries for an existing private YouTube upload session.

Retries reconcile YouTube's server-side offset on every attempt.
No retry is performed for media mutation or invalid credentials.
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from .pi_private_upload_runner import resume_private_upload
from .youtube_resumable_upload import UploadError
from .youtube_upload_session import load_session

RETRYABLE_HTTP = frozenset((408, 409, 429, 500, 502, 503, 504))


def is_retryable_upload_error(exc: BaseException) -> bool:
    """Inspect exception causes without including token-bearing URLs in logs."""
    current: BaseException | None = exc
    for _ in range(6):
        if current is None:
            break
        if isinstance(current, HTTPError):
            return current.code in RETRYABLE_HTTP
        if isinstance(current, (URLError, TimeoutError, ConnectionError)):
            return True
        current = current.__cause__
    return False


def resume_with_retries(
    bindings,
    *,
    episode_id: str,
    session_path: str | Path,
    expected_channel_id: str,
    access_token: str,
    attempts: int = 5,
    initial_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep=time.sleep,
) -> dict:
    if not isinstance(attempts, int) or not 1 <= attempts <= 20:
        raise ValueError("attempts must be 1..20")
    if not 0 <= initial_delay <= max_delay <= 300:
        raise ValueError("invalid retry delay")
    for index in range(attempts):
        # Revalidate the file fingerprint on each attempt.
        load_session(session_path)
        try:
            return resume_private_upload(
                bindings,
                episode_id=episode_id,
                session_path=session_path,
                expected_channel_id=expected_channel_id,
                access_token=access_token,
            )
        except UploadError as exc:
            if index == attempts - 1 or not is_retryable_upload_error(exc):
                raise
            sleep(min(initial_delay * (2 ** index), max_delay))
    raise AssertionError("unreachable")
