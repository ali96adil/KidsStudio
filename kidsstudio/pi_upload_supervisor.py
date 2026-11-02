"""Bounded Pi upload supervisor with per-attempt OAuth refresh."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .pi_private_upload_runner import resume_private_upload
from .pi_upload_retry import is_retryable_upload_error
from .youtube_resumable_upload import UploadError
from .youtube_upload_session import load_session


def supervise_resume(
    bindings,
    *,
    episode_id: str,
    session_path: str | Path,
    expected_channel_id: str,
    token_provider: Callable[[], str],
    attempts: int = 5,
    initial_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    if not isinstance(attempts, int) or not 1 <= attempts <= 20:
        raise ValueError("attempts must be 1..20")
    if not 0 <= initial_delay <= max_delay <= 300:
        raise ValueError("invalid retry delay")
    for index in range(attempts):
        load_session(session_path)
        # Refresh before every attempt; token material remains in memory.
        token = token_provider()
        try:
            return resume_private_upload(
                bindings,
                episode_id=episode_id,
                session_path=session_path,
                expected_channel_id=expected_channel_id,
                access_token=token,
            )
        except UploadError as exc:
            if index == attempts - 1 or not is_retryable_upload_error(exc):
                raise
            sleep(min(initial_delay * 2 ** index, max_delay))
    raise AssertionError("unreachable")
