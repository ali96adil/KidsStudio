"""Hosted macOS ONLY: test the actual one-command supplied-WAV Mac launcher.

Synthesize a synthetic non-speech 24-second mono PCM WAV entirely locally,
then invoke the same Bash script the Mac owner would run. This exercises the
REAL Mac shell, source/host gates, preview, 24s FFmpeg encode, SHA/MP4 check and
0600 technical evidence collector, with no SSH/Google or human owner approval.
Never uploads artifacts; all media live in a self-deleting temporary HOME.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def run() -> dict:
    if platform.system() != "Darwin":
        raise RuntimeError("This hosted launcher smoke requires macOS.")
    repo = Path(__file__).resolve().parents[1]
    bash = repo / "scripts" / "run_mac_colors_pilot.sh"
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, timeout=5).strip()
    with tempfile.TemporaryDirectory(prefix="kidsstudio-ci-private-") as home:
        # macOS tempfile paths often begin /var/folders, where /var is a
        # symlink to /private/var. The production private-file validator
        # intentionally rejects ALL symlink components: use the canonical
        # absolute path for the CI-only HOME and original WAV.
        h = Path(home).resolve(strict=True)
        original = h / "kidsstudio-private" / "narration"
        original.mkdir(parents=True, mode=0o700)
        wav = original / "ci_original_sound_NOT_speech.wav"
        # CLI uses synthetic local sine, never Apple say or an actual Arabic voice.
        synth = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=24",
            "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
            "-y", str(wav),
        ], capture_output=True, timeout=60, check=False)
        if synth.returncode or not wav.exists():
            raise RuntimeError("Cannot generate offline test-only 24s WAV.")
        wav.chmod(0o600)
        digest = hashlib.sha256(wav.read_bytes()).hexdigest()

        env = dict(os.environ)
        env.update({
            "HOME": str(h),
            "KIDSSTUDIO_PYTHON": sys.executable,
            "KIDSSTUDIO_NARRATION_ROOT": str(original),
            "KIDSSTUDIO_NARRATION_NAME": wav.name,
            "KIDSSTUDIO_NARRATION_SHA256": digest,
            "KIDSSTUDIO_SKIP_OPEN": "1",
        })
        env.pop("KIDSSTUDIO_MAC_VOICE", None)
        proc = subprocess.run(
            ["/bin/bash", str(bash)], cwd=repo, env=env,
            capture_output=True, text=True, timeout=1000, check=False)
        if proc.returncode:
            # Extract only constant safety status codes, never user paths,
            # video names, voice names or raw potentially-sensitive stderr.
            safe_statuses = []
            for line in proc.stdout.splitlines():
                if line.startswith("{"):
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict):
                        status = item.get("status")
                        if isinstance(status, str) and status.isascii():
                            safe_statuses.append(status[:100])
                        safe_statuses.extend(
                            item.get("blockers", [])
                            if isinstance(item.get("blockers"), list) else [])
                elif line.startswith("MAC_COLORS_BLOCKED:"):
                    # This fixed launcher prefix includes only safe static
                    # diagnostics. Never serialize raw shell stderr.
                    safe_statuses.append("MAC_COLORS_BLOCKED")
            safe_statuses = [
                value for value in safe_statuses if isinstance(value, str)
                and len(value) <= 100
                and all(c.isascii() and (c.isalnum() or c in "_-") for c in value)
            ]
            raise RuntimeError(
                "Mac launcher CI failed, safe gates: " + ",".join(safe_statuses))
        output = proc.stdout
        for expected in (
            "MAC_PILOT_PRIVATE_DIRS_READY",
            "MAC_COLORS_PREFLIGHT_READY",
            "COLORS_EPISODE_PREVIEW_ONLY",
            "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED",
            "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
            "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING",
            "Local open skipped explicitly",
        ):
            if expected not in output:
                raise AssertionError("Missing expected Mac pilot shell gate.")

        ready = h / "kidsstudio-private" / "ready"
        proof = h / "kidsstudio-private" / "qualification"
        videos = list(ready.glob("colors_ar_01_test_*.mp4"))
        if len(videos) != 1:
            raise AssertionError("One original private MP4 expected.")
        movie = videos[0]
        sha = hashlib.sha256(movie.read_bytes()).hexdigest()
        sidecar = proof / (movie.stem + ".evidence.json")
        if not sidecar.is_file():
            raise AssertionError("Real Mac shell did not collect private evidence.")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        if (movie.stat().st_mode & 0o077
                or sidecar.stat().st_mode & 0o077
                or movie.stat().st_size < 100_000
                or data["video_sha256"] != sha
                or data["video_name"] != movie.name
                or data["source_commit"] != revision
                or data["source_checkout_clean"] is not True
                or data["technical_preflight"] !=
                   "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED"
                or data["full_video_owner_review_pending"] is not True
                or data["publication_approved"] is not False):
            raise AssertionError("Missing private original media/evidence provenance.")
        return {
            "schema_version": 1,
            "status": "MACOS_CI_REAL_SUPPLIED_WAV_LAUNCHER_PASSED",
            "original_synthetic_wav_verified_sha": True,
            "six_audio_beats_energy_qualified": True,
            "native_arabic_apple_voice_used": False,
            "operator_mac_tested": False,
            "real_mac_shell_script_executed": True,
            "24_second_video_created": True,
            "private_technical_sidecar_saved": True,
            "owner_reviewed_video_or_arabic": False,
            "real_ssh_pi_transfer": False,
            "real_youtube_upload": False,
            "publication_approved": False,
        }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
