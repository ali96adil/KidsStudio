"""CI-only macOS Arabic system-voice capability smoke.

Samples original KidsStudio speech on the GitHub-hosted Mac, if an Arabic
macOS voice is already installed. Never installs a voice, downloads models,
connects to Pi, uploads audio, or implies testing the operator's Mac.
The generated temporary WAV is deleted before exit, and nothing is printed
about the voice name or audio payload.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import tempfile

from kidsstudio.first_colors_episode import (
    DURATION, EpisodeMuxError, _arabic_voice, _synthesize_wav,
)
from kidsstudio.mac_episode_audio import _wav_duration


def run_macos_arabic_voice_smoke() -> dict:
    if platform.system() != "Darwin":
        raise ValueError("macOS CI runner is required")
    base = {
        "schema_version": 1,
        "github_hosted_macos_runner": True,
        "operator_mac_tested": False,
        "real_pi_transfer_test": "NOT_RUN",
        "youtube_upload_test": "NOT_RUN",
        "publication_approved": False,
    }
    try:
        picked = _arabic_voice(None)
    except EpisodeMuxError:
        return {
            **base,
            "status": "MACOS_CI_ARABIC_VOICE_NOT_INSTALLED_NOT_TESTED",
            "arabic_voice_render_tested": False,
        }
    with tempfile.TemporaryDirectory(prefix="kidsstudio-macos-ci-speech-") as tmp:
        root = Path(tmp)
        root.chmod(0o700)
        result = _synthesize_wav(root, voice=picked)
        duration = _wav_duration(result)
        if abs(duration - DURATION) > 0.1 or result.stat().st_size <= 44:
            raise AssertionError("Native macOS voice produced invalid test WAV")
    return {
        **base,
        "status": "MACOS_CI_ARABIC_VOICE_SYNTHETIC_SMOKE_PASSED",
        "arabic_voice_render_tested": True,
        "original_script_beats": 6,
        "audio_seconds": round(duration, 3),
        "arabic_pronunciation_human_reviewed": False,
    }


def main() -> int:
    try:
        report = run_macos_arabic_voice_smoke()
    except (AssertionError, OSError, ValueError):
        report = {
            "status": "MACOS_CI_ARABIC_VOICE_SMOKE_FAILED",
            "operator_mac_tested": False,
            "youtube_upload_test": "NOT_RUN",
            "publication_approved": False,
        }
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
