"""Read-only Mac-only colors pilot readiness probe before rendering.

Reports fixed safe blocker codes, never executable paths, installed voice
names, filenames, microphone data, credentials or other private system data.
No speech/audio generation, file writes, cloud/network/SSH/YouTube.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil

from .first_colors_episode import EpisodeMuxError, _arabic_voice
from .host_qualification import _source_checkout
from .host_readiness import inspect_host

_COMMIT = re.compile(r"[a-f0-9]{40}\Z")
_REQUIRED_BINARIES = ("ffmpeg", "ffprobe", "say", "shasum", "git")


def inspect_mac_colors_preflight(*, artifact_root: str,
                                 min_free_gib: float = 2.0,
                                 mac_voice: str | None = None) -> dict:
    blockers: list[str] = []
    if platform.system() != "Darwin":
        blockers.append("macos_required")
    readiness = inspect_host(
        artifact_root=artifact_root, min_free_gib=min_free_gib)
    if not readiness["ready_for_supervised_tests"]:
        blockers.append("private_artifact_root_or_host_unready")
    if readiness["host_system"] != "Darwin" or readiness["machine"].lower() not in (
        "arm64", "x86_64",
    ):
        blockers.append("mac_platform_architecture_mismatch")
    missing = [name for name in _REQUIRED_BINARIES if not shutil.which(name)]
    if missing:
        blockers.append("local_media_or_git_executable_missing")
    revision, clean = _source_checkout()
    if not isinstance(revision, str) or not _COMMIT.fullmatch(revision) or not clean:
        blockers.append("pinned_clean_git_checkout_required")
    if not missing and platform.system() == "Darwin":
        try:
            _arabic_voice(mac_voice)
        except EpisodeMuxError:
            blockers.append("installed_arabic_voice_missing_or_invalid")
    return {
        "schema_version": 1,
        "status": ("MAC_COLORS_PREFLIGHT_READY" if not blockers
                   else "MAC_COLORS_PREFLIGHT_BLOCKED"),
        "blockers": blockers,
        "source_commit": revision if isinstance(revision, str) and
                         _COMMIT.fullmatch(revision) else None,
        "local_arabic_voice_available": (
            "installed_arabic_voice_missing_or_invalid" not in blockers
            and platform.system() == "Darwin" and not missing
        ),
        "video_render_executed": False,
        "speech_generated": False,
        "operator_audio_reviewed": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline no-render Mac colors/Arabic voice preflight")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--min-free-gib", type=float, default=2.0)
    parser.add_argument("--mac-voice")
    args = parser.parse_args(argv)
    try:
        result = inspect_mac_colors_preflight(
            artifact_root=args.artifact_root, min_free_gib=args.min_free_gib,
            mac_voice=args.mac_voice)
    except (OSError, ValueError, TypeError, KeyError):
        result = {
            "status": "MAC_COLORS_PREFLIGHT_ERROR",
            "speech_generated": False,
            "video_render_executed": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "MAC_COLORS_PREFLIGHT_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
