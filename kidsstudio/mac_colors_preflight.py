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

from .first_colors_episode import EpisodeMuxError, _arabic_voice, _SHA
from .audio_pcm_energy import check_six_beat_pcm_energy
from .optional_tool_evidence import private_evidence_file
from .transfer_verify import verify_staged_file
from .host_qualification import _source_checkout
from .host_readiness import inspect_host

_COMMIT = re.compile(r"[a-f0-9]{40}\Z")
_COMMON_BINARIES = ("ffmpeg", "ffprobe", "git")


def _valid_supplied_wav(*, narration_root: str | None,
                        narration_name: str | None,
                        narration_sha256: str | None) -> bool:
    """Offline original 24s mono WAV: private, SHA-bound, six audible beats.

    A signal-energy pass is NOT a proof of Arabic, clear speech or rights.
    The user-supplied source must be checked again by the production mux.
    """
    if (not isinstance(narration_root, str) or not narration_root
            or not isinstance(narration_name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.wav", narration_name)
            or not isinstance(narration_sha256, str)
            or not _SHA.fullmatch(narration_sha256)):
        return False
    try:
        private_evidence_file(narration_root, narration_name, max_bytes=128 * 1024**2)
        proof = verify_staged_file(
            root=narration_root, relative_path=narration_name,
            expected_sha256=narration_sha256, max_bytes=128 * 1024**2)
        if proof["status"] != "VERIFIED":
            return False
        gate = check_six_beat_pcm_energy(
            root=narration_root, relative_path=narration_name)
        return gate["status"] == "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED"
    except (ValueError, OSError, KeyError, TypeError):
        return False


def inspect_mac_colors_preflight(*, artifact_root: str,
                                 min_free_gib: float = 2.0,
                                 mac_voice: str | None = None,
                                 voice_mode: str = "macos",
                                 narration_root: str | None = None,
                                 narration_name: str | None = None,
                                 narration_sha256: str | None = None) -> dict:
    if voice_mode not in ("macos", "supplied_wav"):
        raise ValueError("Unsupported offline voice mode.")
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
    missing = [name for name in (*_COMMON_BINARIES, *(
        ("say",) if voice_mode == "macos" else ())) if not shutil.which(name)]
    if missing:
        blockers.append("local_media_or_git_executable_missing")
    revision, clean = _source_checkout()
    if not isinstance(revision, str) or not _COMMIT.fullmatch(revision) or not clean:
        blockers.append("pinned_clean_git_checkout_required")
    has_apple_voice = False
    verified_supplied = False
    if voice_mode == "macos":
        if any(x is not None for x in (
                narration_root, narration_name, narration_sha256)):
            blockers.append("unexpected_supplied_wav_arguments")
        if not missing and platform.system() == "Darwin":
            try:
                _arabic_voice(mac_voice)
                has_apple_voice = True
            except EpisodeMuxError:
                blockers.append("installed_arabic_voice_missing_or_invalid")
    else:
        if mac_voice is not None:
            blockers.append("unexpected_macos_voice_argument")
        verified_supplied = _valid_supplied_wav(
            narration_root=narration_root, narration_name=narration_name,
            narration_sha256=narration_sha256)
        if not verified_supplied:
            blockers.append("supplied_wav_missing_unverified_or_silent")
    return {
        "schema_version": 1,
        "status": ("MAC_COLORS_PREFLIGHT_READY" if not blockers
                   else "MAC_COLORS_PREFLIGHT_BLOCKED"),
        "blockers": blockers,
        "source_commit": revision if isinstance(revision, str) and
                         _COMMIT.fullmatch(revision) else None,
        "voice_mode": voice_mode,
        "local_arabic_voice_available": has_apple_voice,
        "supplied_wav_six_beats_sha_verified": verified_supplied,
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
    parser.add_argument("--voice-mode", choices=("macos", "supplied_wav"),
                        default="macos")
    parser.add_argument("--narration-root")
    parser.add_argument("--narration-name")
    parser.add_argument("--narration-sha256")
    args = parser.parse_args(argv)
    try:
        result = inspect_mac_colors_preflight(
            artifact_root=args.artifact_root, min_free_gib=args.min_free_gib,
            mac_voice=args.mac_voice, voice_mode=args.voice_mode,
            narration_root=args.narration_root,
            narration_name=args.narration_name,
            narration_sha256=args.narration_sha256)
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
