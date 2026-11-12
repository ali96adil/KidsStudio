"""Read-only first physical Mac/Pi pilot doctor; no device actions.

Check offline host and source qualification, optional installed Mac Arabic
voice readiness, and give stable actionable blocker codes. Never create
directories, inspect OAuth secrets, contact Pi/Google or render video.
A READY result means only that supervised device tests MAY BEGIN.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .host_qualification import qualify_host

_HINTS = {
    "python_3_11_plus":
        "Select a trusted Python 3.11+ virtual environment on this device.",
    "artifact_root_exists":
        "Create the expected private artifact directory outside Git.",
    "artifact_root_outside_git":
        "Use an owner-only artifact directory OUTSIDE the source checkout.",
    "artifact_root_not_symlink":
        "Use a real directory, not a symlink, for private media.",
    "artifact_root_no_symlink_components":
        "Remove symlinks from every part of the private artifact path.",
    "artifact_root_owned_by_user":
        "Run under the account that owns the private media directory.",
    "artifact_root_private":
        "Restrict the private artifact directory permissions to 0700.",
    "free_space_threshold":
        "Free at least 2 GiB, or more for the planned physical pilot.",
    "role_matches_os_machine":
        "Run the Mac probe on macOS or the Pi probe on Linux ARM.",
    "raspberry_pi_model_confirmed":
        "Run on the actual Raspberry Pi; generic Linux ARM is not enough.",
    "source_commit_sha40":
        "Use a real Git checkout with a valid pinned 40-character commit.",
    "source_checkout_clean":
        "Inspect git status and preserve or commit all changes before testing.",
    "offline_review_selftest_failed":
        "Repair the local offline review pipeline test before supervised use.",
    "macos_required":
        "The first colors render requires the actual macOS machine.",
    "private_artifact_root_or_host_unready":
        "Correct the detailed host private root, ownership and space checks.",
    "mac_platform_architecture_mismatch":
        "The Mac pilot supports macOS arm64 or x86_64 only.",
    "local_media_or_git_executable_missing":
        "Install or select local ffmpeg, ffprobe, say and git binaries.",
    "pinned_clean_git_checkout_required":
        "Check out the exact reviewed commit and ensure git status is clean.",
    "installed_arabic_voice_missing_or_invalid":
        "Install/select an Arabic Apple say voice, or explicitly choose a verified original WAV.",
    "supplied_wav_missing_unverified_or_silent":
        "Use an existing private, SHA-verified 24s mono 16-bit PCM WAV with all six beats audible.",
    "unexpected_supplied_wav_arguments":
        "Use only one mode: do not add WAV parameters to the Apple say voice mode.",
    "unexpected_macos_voice_argument":
        "Use only one mode: do not mix KIDSSTUDIO_MAC_VOICE with supplied-WAV mode.",
    "pillow_or_audio_dependency_missing":
        "Use a Python 3.11+ environment with Pillow and KidsStudio installed.",
    "ssh_client_missing":
        "Install/enable the macOS OpenSSH client for a later, supervised Pi transfer.",
}


def _mac_preflight(*, artifact_root: str, min_free_gib: float,
                   mac_voice: str | None, voice_mode: str = "macos",
                   narration_root: str | None = None,
                   narration_name: str | None = None,
                   narration_sha256: str | None = None) -> dict:
    # Avoid importing Pillow-dependent episode code on Raspberry Pi: the
    # upload-only device does not need a graphics rendering dependency.
    from .mac_colors_preflight import inspect_mac_colors_preflight
    return inspect_mac_colors_preflight(
        artifact_root=artifact_root, min_free_gib=min_free_gib,
        mac_voice=mac_voice, voice_mode=voice_mode,
        narration_root=narration_root, narration_name=narration_name,
        narration_sha256=narration_sha256)


def inspect_first_pilot_device(*, role: str, artifact_root: str | None = None,
                               min_free_gib: float = 2.0,
                               mac_voice: str | None = None,
                               voice_mode: str = "macos",
                               narration_root: str | None = None,
                               narration_name: str | None = None,
                               narration_sha256: str | None = None) -> dict:
    if role not in ("mac", "pi"):
        raise ValueError("Choose the Mac or Pi role.")
    if voice_mode not in ("macos", "supplied_wav"):
        raise ValueError("Unsupported voice mode.")
    if role == "pi" and (
            mac_voice is not None or voice_mode != "macos"
            or any(x is not None for x in (
                narration_root, narration_name, narration_sha256))):
        raise ValueError("Mac-only narration options cannot be selected for Pi.")
    if min_free_gib < 0 or min_free_gib > 1024:
        raise ValueError("Invalid disk threshold.")
    path = artifact_root or str(Path.home() / "kidsstudio-private" /
                                ("ready" if role == "mac" else "inbox"))
    qualification = qualify_host(
        role="mac-render" if role == "mac" else "pi-private-handoff",
        artifact_root=path, min_free_gib=min_free_gib)
    checks = qualification["checks"]
    failed = {code for code, ok in checks.items() if ok is not True}
    if qualification["synthetic_review_pipeline"] != "OFFLINE_REVIEW_PIPELINE_PASS":
        failed.add("offline_review_selftest_failed")

    voice_found = None
    wav_found = None
    if role == "mac":
        try:
            mac = _mac_preflight(
                artifact_root=path, min_free_gib=min_free_gib,
                mac_voice=mac_voice, voice_mode=voice_mode,
                narration_root=narration_root, narration_name=narration_name,
                narration_sha256=narration_sha256)
            failed.update(mac["blockers"])
            voice_found = mac["local_arabic_voice_available"] is True
            wav_found = mac.get("supplied_wav_six_beats_sha_verified", False) is True
        except ImportError:
            failed.add("pillow_or_audio_dependency_missing")
            voice_found = False
            wav_found = False
        if not shutil.which("ssh"):
            failed.add("ssh_client_missing")
    if qualification["status"] != "SUPERVISED_TESTS_READY" and not failed:
        failed.add("offline_review_selftest_failed")

    # Non-sensitive, stable codes only. Never output shell paths, voice names,
    # filenames, credentials or detailed subprocess exception strings.
    blockers = [
        {"code": code, "suggested_fix": _HINTS.get(
            code, "Inspect the local qualification check before device testing.")}
        for code in sorted(failed)
    ]
    ready = not blockers
    return {
        "schema_version": 1,
        "status": ("FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY"
                   if ready else "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_BLOCKED"),
        "role": role,
        "source_commit": qualification["source_commit"],
        "source_checkout_clean": qualification["source_checkout_clean"] is True,
        "failed_check_count": len(blockers),
        "blockers": blockers,
        "voice_mode": voice_mode if role == "mac" else None,
        "installed_mac_arabic_voice_qualified": voice_found,
        "original_supplied_wav_sha_energy_qualified": wav_found,
        "same_revision_on_other_device_verified": False,
        "actual_mac_arabic_speech_rendered": False,
        "actual_pi_ssh_transfer_tested": False,
        "real_youtube_oauth_or_upload_tested": False,
        "real_ssh_or_google_network_called": False,
        "files_created_or_modified": False,
        "owner_full_video_review_completed": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only offline Mac/Pi first-episode preflight (no writes/network)")
    parser.add_argument("--role", choices=("mac", "pi"), required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument("--min-free-gib", type=float, default=2.0)
    parser.add_argument("--mac-voice")
    parser.add_argument("--voice-mode", choices=("macos", "supplied_wav"),
                        default="macos")
    parser.add_argument("--narration-root")
    parser.add_argument("--narration-name")
    parser.add_argument("--narration-sha256")
    args = parser.parse_args(argv)
    try:
        result = inspect_first_pilot_device(
            role=args.role, artifact_root=args.artifact_root,
            min_free_gib=args.min_free_gib, mac_voice=args.mac_voice,
            voice_mode=args.voice_mode, narration_root=args.narration_root,
            narration_name=args.narration_name,
            narration_sha256=args.narration_sha256)
    except (OSError, ValueError, TypeError, KeyError, AssertionError,
            ImportError, OverflowError):
        print(json.dumps({
            "status": "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_ERROR",
            "real_ssh_or_google_network_called": False,
            "files_created_or_modified": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "FIRST_PILOT_OFFLINE_DEVICE_PREFLIGHT_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
