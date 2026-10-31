"""Actual local Ollama vision evidence for M68 Shorts.

Captures decoded frames from the pinned MP4 and queries a local vision model.
Silent frames cannot establish audio quality or legal copyright ownership;
those axes always fail closed. This is a diagnostic REJECT candidate, not
a complete six-axis AI certification or YouTube upload authorization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from .local_vision_review import OllamaVision
from .m67_master_handoff import verify_inventory
from .m68_ai_review_adapter import run_ai_review
from .m68_short_content_review import CHECKS
from .real_media_evidence import capture_frames, digest

VISUAL_AXES = frozenset(("pedagogy", "visual", "age_appropriate", "source_consistency"))
UNOBSERVABLE = {
    "audio": "Audio cannot be evaluated from silent decoded video frames; independent actual audio analysis is required.",
    "copyright": "Visual similarity cannot establish licensing, consent, provenance, or copyright ownership of source assets.",
}


def run_vision_diagnostic(root, handoff, *, mp4, script, ffmpeg, ffprobe,
                          endpoint, model, frames=5):
    root = Path(root)
    mp4 = Path(mp4)
    script = Path(script)
    if not script.is_file() or script.is_symlink() or not 1 <= script.stat().st_size <= 8000:
        raise ValueError("existing bounded approved script required")
    source_text = script.read_text(encoding="utf-8")
    if not source_text.strip():
        raise ValueError("nonempty approved script required")
    verified = verify_inventory(root, handoff)["sha256"]
    if not mp4.is_file() or mp4.is_symlink() or digest(mp4) != verified:
        raise ValueError("exact verified MP4 required")
    vision = OllamaVision(endpoint, model, "m68_local_ollama_vision")
    with tempfile.TemporaryDirectory(prefix="m68_frames_") as directory:
        capture = capture_frames(
            mp4=mp4, expected_mp4_sha=verified,
            ffprobe_binary=ffprobe, ffmpeg_binary=ffmpeg,
            out_dir=directory, frames=frames)
        manifest = json.loads(Path(capture["frames_manifest_file"]).read_text(encoding="utf-8"))
        images = [Path(item["file"]).read_bytes() for item in manifest["frames"]]
        def infer(*, axis, root, handoff):
            if axis in UNOBSERVABLE:
                passed, evidence = False, UNOBSERVABLE[axis]
            else:
                objective = (
                    "Review the actual ordered frames for " + axis +
                    ". Check educational appropriateness, consistency with the "
                    "provided approved script, and child safety. No assumptions "
                    "about sound or copyright. If uncertain, reject.")
                answer, _ = vision.run(
                    role="visual_child_safety", script=source_text,
                    images=images, objective=objective)
                results = answer["checks"]
                passed = all(item["decision"] == "PASS" for item in results.values())
                evidence = " ".join(item["evidence"] for item in results.values())
                if len(evidence) > 2000:
                    evidence = evidence[:2000]
            return {"axis": axis, "passed": passed, "evidence": evidence,
                    "short_id": handoff["short_id"],
                    "source_episode_id": handoff["source_episode_id"],
                    "video_sha256": verified}
        receipt = run_ai_review(root, handoff, infer=infer,
                                reviewer_id="kidsstudio-ai-vision-diagnostic")
    if receipt["decision"] != "REJECT" or receipt["checks"]["audio"] or receipt["checks"]["copyright"]:
        raise ValueError("vision-only review must not certify audio or rights")
    receipt["review_scope"] = "REAL_LOCAL_VISION_ONLY_AUDIO_AND_RIGHTS_UNVERIFIED"
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "handoff", "mp4", "script"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/api/chat")
    parser.add_argument("--model", required=True)
    parser.add_argument("--frames", type=int, default=5)
    args = parser.parse_args(argv)
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    receipt = run_vision_diagnostic(
        args.root, handoff, mp4=args.mp4, script=args.script,
        ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, endpoint=args.endpoint,
        model=args.model, frames=args.frames)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
