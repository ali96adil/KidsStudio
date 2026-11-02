"""Safe offline first-run Pi trial in an isolated temporary directory.

No real OAuth, network transfer, YouTube upload, or public release.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from .pi_pipeline_service import run_pipeline
from .pi_live_readiness import inspect_live_readiness


def run_offline_trial() -> dict:
    with tempfile.TemporaryDirectory(prefix="kidsstudio-pi-trial-") as tmp:
        root = Path(tmp)
        state = root / "private-upload"
        credentials = root / "fake-oauth.json"
        credentials.write_text(json.dumps({
            "client_id": "offline-only", "client_secret": "offline-only",
            "refresh_token": "offline-only", "channel_id": "offline-test-channel",
        }), encoding="utf-8")
        credentials.chmod(0o600)
        titles = root / "titles.json"
        titles.write_text(json.dumps({"colors-red-ar": "Learn Red"}), encoding="utf-8")
        titles.chmod(0o600)
        # Mock the entire processing tick: no external provider is contacted.
        with patch("kidsstudio.pi_pipeline_service.pipeline_tick") as tick:
            exit_code = run_pipeline(
                state_dir=state, credentials=credentials,
                titles_file=titles, once=True,
            )
        readiness = inspect_live_readiness(
            state_dir=state, credentials=credentials, titles_file=titles,
        )
        return {
            "passed": exit_code == 0 and tick.call_count == 1
                      and readiness["ready_for_hardware_test"],
            "first_boot_exit_code": exit_code,
            "tick_invocations": tick.call_count,
            "readiness": readiness,
            "offline_only": True,
            "youtube_upload_tested": False,
            "public_release_enabled": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline private Pi pipeline trial")
    parser.parse_args()
    report = run_offline_trial()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
