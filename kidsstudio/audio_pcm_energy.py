"""Offline PCM energy-presence gates for validated narration timelines.

This detects missing/near-silent narration on a per-beat basis. It cannot
recognize words, accents, clipping, intelligibility, audio quality or owner
approval. No speech/audio contents, filenames or measured amplitudes are logged.
No network, subprocess, media mutations, transfer or YouTube activity.
"""
from __future__ import annotations

from array import array
import math
import os
from pathlib import Path
import sys
import wave

from .optional_tool_evidence import private_evidence_file


class AudioPresenceError(ValueError):
    """The PCM file or a narration timeline segment lacks usable signal."""


def check_pcm_timeline_energy(*, root: str, relative_path: str,
                              beat_durations: list[float]) -> dict:
    """Require modest PCM energy in each explicitly timed narration segment.

    This does not recognize words, intelligibility or pronunciation. The
    timeline is supplied by the already validated scene specification.
    """
    if (not isinstance(beat_durations, list) or not beat_durations
            or len(beat_durations) > 200
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   or not 0 < value <= 600 for value in beat_durations)
            or sum(beat_durations) > 600):
        raise AudioPresenceError("Invalid audio beat timeline.")
    file = private_evidence_file(root, relative_path, max_bytes=128 * 1024**2)
    try:
        with wave.open(str(file), "rb") as track:
            rate = track.getframerate()
            expected_duration = sum(beat_durations)
            if (track.getcomptype() != "NONE" or track.getnchannels() != 1
                    or track.getsampwidth() != 2 or not 16000 <= rate <= 96000
                    or abs(track.getnframes() / rate - expected_duration) > 0.1):
                raise AudioPresenceError("PCM duration or format differs from narration timeline.")
            for duration in beat_durations:
                frames_left = round(duration * rate)
                active = 0
                while frames_left:
                    frames = min(frames_left, rate * 4)
                    raw = track.readframes(frames)
                    if len(raw) != frames * 2:
                        raise AudioPresenceError("Incomplete story beat in PCM.")
                    samples = array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    active += sum(1 for sample in samples if abs(sample) >= 196)
                    frames_left -= frames
                active_needed = max(1, min(int(rate * 0.06),
                                           int(round(duration * rate * 0.25))))
                if active < active_needed:
                    raise AudioPresenceError("Story beat is silent or incomplete in PCM.")
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as exc:
        raise AudioPresenceError("PCM narration unreadable.") from exc
    return {
        "schema_version": 1,
        "status": "PCM_TIMELINE_ENERGY_PRESENT_UNREVIEWED",
        "beat_count": len(beat_durations),
        "beats_with_minimum_energy": len(beat_durations),
        "speech_words_verified": False,
        "arabic_pronunciation_reviewed": False,
        "owner_audio_reviewed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def check_six_beat_pcm_energy(*, root: str, relative_path: str) -> dict:
    """Check six four-second mono PCM beats, each with minimum signal energy."""
    report = check_pcm_timeline_energy(
        root=root, relative_path=relative_path, beat_durations=[4] * 6)
    report["status"] = "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED"
    return report
