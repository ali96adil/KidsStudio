"""Offline PCM energy-presence gate for the six-beat Arabic colors pilot.

This detects missing/near-silent narration on a per-beat basis. It cannot
recognize words, accents, clipping, intelligibility, audio quality or owner
approval. No speech/audio contents, filenames or measured amplitudes are logged.
No network, subprocess, media mutations, transfer or YouTube activity.
"""
from __future__ import annotations

from array import array
import os
from pathlib import Path
import sys
import wave

from .optional_tool_evidence import private_evidence_file


class AudioPresenceError(ValueError):
    """The PCM file has a missing or nearly silent four-second story beat."""


def check_six_beat_pcm_energy(*, root: str, relative_path: str) -> dict:
    """Check exactly six four-second mono PCM beats, each with ≥60ms energy.

    This uses a deliberately modest 196/32768 sample-amplitude threshold;
    light room-noise can pass, so a result never claims intelligible speech.
    """
    file = private_evidence_file(root, relative_path, max_bytes=128 * 1024**2)
    try:
        with wave.open(str(file), "rb") as track:
            rate = track.getframerate()
            if (track.getcomptype() != "NONE" or track.getnchannels() != 1
                    or track.getsampwidth() != 2 or not 16000 <= rate <= 96000
                    or abs(track.getnframes() / rate - 24.0) > 0.1):
                raise AudioPresenceError("Expected 24s mono 16-bit PCM narration.")
            active_needed = int(rate * 0.06)
            for beat in range(6):
                raw = track.readframes(4 * rate)
                if len(raw) != 4 * rate * 2:
                    raise AudioPresenceError("Incomplete story beat in PCM.")
                samples = array("h")
                samples.frombytes(raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                # Sampling all frames avoids a loud click passing as a beat;
                # require at least 60ms above -44dBFS-equivalent threshold.
                active = sum(1 for sample in samples if abs(sample) >= 196)
                if active < active_needed:
                    raise AudioPresenceError("A story beat is silent/too quiet.")
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as exc:
        raise AudioPresenceError("PCM narration unreadable.") from exc
    return {
        "schema_version": 1,
        "status": "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED",
        "beat_count": 6,
        "beats_with_minimum_energy": 6,
        "speech_words_verified": False,
        "arabic_pronunciation_reviewed": False,
        "owner_audio_reviewed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }
