"""Backward-compatible names of durable upload creation markers.

The first deployment used the literal backslash-zero separator. Never
forget those markers when upgrading: they may represent remote sessions.
"""
from __future__ import annotations

import hashlib


def intent_filenames(episode_id: str, channel_id: str) -> tuple[str, str]:
    canonical = hashlib.sha256(
        (episode_id + chr(0) + channel_id).encode("utf-8")
    ).hexdigest() + ".intent"
    legacy = hashlib.sha256(
        (episode_id + chr(92) + "0" + channel_id).encode("utf-8")
    ).hexdigest() + ".intent"
    return canonical, legacy
