"""M67 local production command: prepare, generate, inspect, and pin assets.

Run stages separately so an interrupted Mac render never overwrites media.
No stage grants AI QA, owner approval, Pi transfer or YouTube publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_media_jobs import make_jobs
from .m67_production_handoff import build_manifest
from .m67_comfy_batch import render_images
from .m67_macos_voice_batch import render_voices
from .m67_media_validation import inspect_media_jobs
from .m67_decode_qualification import decode_check


class ProductionStageError(RuntimeError):
    pass


def _save_new(path, payload):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ProductionStageError(f"refusing overwrite: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def prepare(storyboard, root):
    root = Path(root)
    if root.exists() or root.is_symlink():
        raise ProductionStageError("episode root must be new")
    if any((p / ".git").exists() for p in (root.resolve(), *root.resolve().parents)):
        raise ProductionStageError("episode media must be outside Git")
    jobs = make_jobs(storyboard)
    manifest = build_manifest(storyboard)
    root.mkdir(parents=True)
    (root / "art").mkdir()
    (root / "voice").mkdir()
    _save_new(root / "jobs.json", jobs)
    _save_new(root / "manifest.json", manifest)
    _save_new(root / "storyboard.json", storyboard)
    return {"status": "PREPARED", "root": str(root),
            "beats": len(jobs["jobs"]), "public_release_authorized": False}


def generate(root, *, workflow, text_node, voice, image_fn=render_images,
             voice_fn=render_voices):
    root = Path(root)
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    # Fail before starting either engine if either batch was already attempted.
    for name in ("comfy_batch_report.json", "voice_batch_report.json"):
        if (root / name).exists() or (root / name).is_symlink():
            raise ProductionStageError("batch already attempted; use a new episode root")
    images = image_fn(jobs, workflow, root, text_node=text_node)
    voices = voice_fn(jobs, root, voice=voice)
    return {"status": "GENERATED_PENDING_MEDIA_INSPECTION",
            "images": len(images["images"]), "voices": len(voices["voices"]),
            "public_release_authorized": False}


def inspect(root):
    root = Path(root)
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    report = inspect_media_jobs(jobs, root)
    _save_new(root / "media_inspection.json", report)
    return report


def pin_reviewed(root, approvals):
    """Pin exact file hashes after independent QA; no free-form PASS shortcut.

    approvals must have episode_id and a list of {beat, art_sha256,
    voice_sha256, visual_qa, voice_qa}. The review process is external.
    """
    root = Path(root)
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    inspection = inspect_media_jobs(jobs, root)
    if (root / "reviewed_manifest.json").exists() or (root / "reviewed_manifest.json").is_symlink():
        raise ProductionStageError("reviewed manifest already exists")
    if inspection["status"] != "MEDIA_STRUCTURALLY_READY_PENDING_QA":
        raise ProductionStageError("media structural validation blocked")
    decoded = decode_check(jobs, root)
    if decoded["status"] != "MEDIA_DECODED_PENDING_QA":
        raise ProductionStageError("full media decode qualification blocked")
    decoded_by_beat = {entry["beat"]: entry for entry in decoded["results"]}
    if len(decoded_by_beat) != len(jobs["jobs"]):
        raise ProductionStageError("decode result count mismatch")
    for observed in inspection["results"]:
        decoded_entry = decoded_by_beat.get(observed["beat"], {})
        if (decoded_entry.get("visual_sha256") != observed.get("visual_sha256")
                or decoded_entry.get("voice_sha256") != observed.get("voice_sha256")):
            raise ProductionStageError("media changed between inspection and decoding")
    if approvals.get("episode_id") != jobs["episode_id"]:
        raise ProductionStageError("approval episode mismatch")
    provided = approvals.get("assets")
    if not isinstance(provided, list) or len(provided) != len(jobs["jobs"]):
        raise ProductionStageError("one explicit approval per beat required")
    indexed = {item.get("beat"): item for item in provided}
    if len(indexed) != len(provided):
        raise ProductionStageError("duplicate beat approval")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for asset, observed in zip(manifest["assets"], inspection["results"]):
        approved = indexed.get(asset["beat"])
        if not approved or any(approved.get(k) != "PASS"
                               for k in ("visual_qa", "voice_qa")):
            raise ProductionStageError("independent visual and voice QA required")
        for kind in ("art", "voice"):
            observed_hash = observed["visual_sha256" if kind == "art" else "voice_sha256"]
            if approved.get(kind + "_sha256") != observed_hash:
                raise ProductionStageError("approved hash does not match current file")
            asset[kind + "_sha256"] = observed_hash
        asset["visual_qa"] = asset["voice_qa"] = "PASS"
    manifest["status"] = "ASSETS_QA_READY_FOR_RENDER"
    # Never mutate original manifest or grant public release.
    _save_new(root / "reviewed_manifest.json", manifest)
    return {"status": manifest["status"], "manifest": str(root / "reviewed_manifest.json"),
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="stage", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--storyboard", type=Path, required=True)
    a.add_argument("--root", type=Path, required=True)
    b = sub.add_parser("generate")
    b.add_argument("--root", type=Path, required=True)
    b.add_argument("--workflow", type=Path, required=True)
    b.add_argument("--text-node", required=True)
    b.add_argument("--voice", required=True)
    c = sub.add_parser("inspect")
    c.add_argument("--root", type=Path, required=True)
    e = sub.add_parser("decode")
    e.add_argument("--root", type=Path, required=True)
    d = sub.add_parser("pin-reviewed")
    d.add_argument("--root", type=Path, required=True)
    d.add_argument("--approvals", type=Path, required=True)
    args = p.parse_args(argv)
    if args.stage == "prepare":
        result = prepare(json.loads(args.storyboard.read_text(encoding="utf-8")),
                         args.root)
    elif args.stage == "generate":
        result = generate(args.root,
                          workflow=json.loads(args.workflow.read_text(encoding="utf-8")),
                          text_node=args.text_node, voice=args.voice)
    elif args.stage == "inspect":
        result = inspect(args.root)
    elif args.stage == "decode":
        root = args.root
        jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
        result = decode_check(jobs, root)
        _save_new(root / "media_decode_report.json", result)
    else:
        result = pin_reviewed(args.root,
                              json.loads(args.approvals.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
