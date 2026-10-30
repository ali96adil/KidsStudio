"""M67.3-67.6 fail-closed production handoff for the first educational episode.

Produces immutable planning and QA manifests. Does not fabricate audio, art,
rendered video, upload approval, or owner approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .m67_production_plan import compile_plan


class ProductionHandoffError(ValueError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ProductionHandoffError("invalid relative asset path")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ProductionHandoffError("asset escapes production directory")
    target = root / rel
    if any(p.is_symlink() for p in (target, *list(target.parents)[:len(rel.parts)])):
        raise ProductionHandoffError("symlink asset rejected")
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ProductionHandoffError("asset missing or outside production directory")
    return target


def build_manifest(storyboard: dict) -> dict:
    plan = compile_plan(storyboard)
    assets = []
    for index, beat in enumerate(storyboard["beats"], 1):
        key = f"beat_{index:02d}"
        assets.append({
            "beat": index,
            "start": beat["start"],
            "end": beat["end"],
            "visual": beat["visual"],
            "narration": beat["narration"],
            "art": f"art/{key}.png",
            "voice": f"voice/{key}.wav",
            "art_sha256": None,
            "voice_sha256": None,
            "visual_qa": "PENDING",
            "voice_qa": "PENDING",
        })
    return {
        "schema_version": 1,
        "episode_id": storyboard["episode_id"],
        "status": "ASSETS_REQUIRED",
        "godot_scene_spec": plan["godot_scene_spec"],
        "assets": assets,
        "render": {"file": "render/episode_qa_master.mp4",
                   "sha256": None, "qa": "PENDING"},
        "owner_review": "PENDING",
        "youtube_visibility": "private",
        "public_release_authorized": False,
    }


def audit_assets(manifest: dict, root: Path) -> dict:
    if manifest.get("public_release_authorized") is not False:
        raise ProductionHandoffError("public release must remain blocked")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ProductionHandoffError("no production assets")
    issues = []
    for item in assets:
        for kind in ("art", "voice"):
            try:
                file = _safe_file(root, item[kind])
                expected = item.get(kind + "_sha256")
                if not isinstance(expected, str) or len(expected) != 64:
                    raise ProductionHandoffError("missing pinned digest")
                if _sha(file) != expected:
                    raise ProductionHandoffError("digest mismatch")
            except (KeyError, OSError, ProductionHandoffError) as exc:
                issues.append({"beat": item.get("beat"), "asset": kind,
                               "reason": str(exc)})
        if item.get("visual_qa") != "PASS" or item.get("voice_qa") != "PASS":
            issues.append({"beat": item.get("beat"), "asset": "qa",
                           "reason": "AI QA not passed"})
    return {
        "status": "ASSETS_QA_READY_FOR_RENDER" if not issues else "ASSETS_BLOCKED",
        "issues": issues,
        "render_authorized": not issues,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def audit_master(manifest: dict, root: Path) -> dict:
    assets = audit_assets(manifest, root)
    if not assets["render_authorized"]:
        return {"status": "MASTER_BLOCKED", "issues": assets["issues"],
                "pi_transfer_authorized": False, "public_release_authorized": False}
    render = manifest.get("render", {})
    try:
        file = _safe_file(root, render["file"])
        if render.get("qa") != "PASS" or render.get("sha256") != _sha(file):
            raise ProductionHandoffError("render QA or digest missing")
    except (KeyError, OSError, ProductionHandoffError) as exc:
        return {"status": "MASTER_BLOCKED", "issues": [str(exc)],
                "pi_transfer_authorized": False, "public_release_authorized": False}
    return {"status": "MASTER_QA_READY_FOR_EXISTING_PI_PIPELINE",
            "pi_transfer_authorized": True,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.storyboard.is_symlink() or not args.storyboard.is_file():
        parser.error("regular storyboard required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must not exist")
    data = json.loads(args.storyboard.read_text(encoding="utf-8"))
    manifest = build_manifest(data)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
