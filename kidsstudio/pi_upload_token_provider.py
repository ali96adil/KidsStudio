"""Fresh access tokens for Pi upload recovery attempts.

No OAuth secrets are logged, serialized, or passed via command-line args.
"""
from __future__ import annotations

from pathlib import Path

from .pi_youtube_release_check import load_credentials
from .youtube_oauth_token import refresh_access_token


class FileTokenProvider:
    def __init__(self, credential_path: str | Path):
        self.credential_path = Path(credential_path)

    def __call__(self) -> str:
        credentials = load_credentials(self.credential_path)
        return refresh_access_token(
            credentials["client_id"],
            credentials["client_secret"],
            credentials["refresh_token"],
        )
