"""M67 verify locally generated media files without granting QA.

Inspects PNG dimensions and PCM WAV duration using standard library only.
Returns hashes for subsequent review; never mutates the production manifest.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import wave

from .m67_production_handoff import _safe_file


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _png_dimensions(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature")
    if header[12:16] != b"IHDR":
        raise ValueError("invalid PNG header")
    return struct.unpack(">II", header[16:24])


def inspect_media_jobs(packet, root):
    root = Path(root).resolve()
    results = []
    for job in packet["jobs"]:
        issues = []
        data = {"beat": job["beat"], "status": "PENDING_QA"}
        for kind in ("visual", "voice"):
            try:
                file = _safe_file(root, job[kind]["output"])
                if kind == "visual":
                    size = _png_dimensions(file)
                    if size != tuple(job["visual"]["canvas"]):
                        raise ValueError("unexpected image dimensions")
                    data["image_size"] = list(size)
                else:
                    with wave.open(str(file), "rb") as wav:
                        if wav.getcomptype() != "NONE" or wav.getframerate() != 48000:
                            raise ValueError("expected 48kHz uncompressed WAV")
                        if wav.getnchannels() not in (1, 2):
                            raise ValueError("invalid channel count")
                        if wav.getsampwidth() not in (2, 3, 4):
                            raise ValueError("invalid PCM bit depth")
                        duration = wav.getnframes() / wav.getframerate()
                        if duration <= 0 or duration > job["voice"]["duration_budget_seconds"]:
                            raise ValueError("voice exceeds scene budget")
                        data["voice_duration_seconds"] = round(duration, 3)
                data[kind + "_sha256"] = _digest(file)
            except (OSError, ValueError, KeyError, EOFError) as exc:
                issues.append({"asset": kind, "reason": type(exc).__name__})
        data["issues"] = issues
        if issues:
            data["status"] = "BLOCKED"
        results.append(data)
    return {
        "status": "MEDIA_STRUCTURALLY_READY_PENDING_QA"
        if all(r["status"] == "PENDING_QA" for r in results) else "BLOCKED",
        "episode_id": packet["episode_id"],
        "results": results,
        "visual_qa": "PENDING",
        "voice_qa": "PENDING",
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
