"""Read-only preflight for the private Pi upload pipeline."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from .pi_youtube_release_check import load_credentials
from .pi_pipeline_service import read_titles


def _private_directory(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    info = path.stat()
    return not bool(info.st_mode & 0o077) and (not hasattr(os, "getuid") or info.st_uid == os.getuid())


def inspect_pi_pipeline(*, state_dir: str | Path, credentials: str | Path, titles_file: str | Path) -> dict:
    """Validate configuration without making network requests or changing files."""
    root = Path(state_dir)
    checks = {}
    checks["state_dir_private"] = _private_directory(root)
    checks["staging_dir_private"] = _private_directory(root / "staging")
    checks["inbox_dir_private"] = _private_directory(root / "inbox")
    checks["sessions_dir_private"] = _private_directory(root / "sessions")
    try:
        creds = load_credentials(Path(credentials))
        checks["credentials_private_and_valid"] = True
        checks["channel_configured"] = bool(creds["channel_id"])
    except (OSError, ValueError, json.JSONDecodeError, KeyError):
        checks["credentials_private_and_valid"] = False
        checks["channel_configured"] = False
    try:
        titles = read_titles(titles_file)
        title_path = Path(titles_file)
        info = title_path.stat()
        checks["titles_private_and_valid"] = (
            not title_path.is_symlink() and stat.S_ISREG(info.st_mode)
            and not info.st_mode & 0o077
            and (not hasattr(os, "getuid") or info.st_uid == os.getuid())
            and bool(titles)
        )
    except (OSError, ValueError, json.JSONDecodeError):
        checks["titles_private_and_valid"] = False
    return {"ready": all(checks.values()), "checks": checks, "network_checked": False,
            "youtube_upload_tested": False}
