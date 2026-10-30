"""One-command M67 local episode runner.

Requires existing, reviewed rig, image and voice assets. Renders Godot
beats, attaches animations, and composes a private local preview only when
animation QA was independently approved. No Pi or YouTube interaction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_batch_godot import batch_render
from .m67_animation_attach import attach_animations
from .m67_animated_compositor import compose_animated
from .m67_production_handoff import audit_assets


class LocalRunError(RuntimeError):
    pass


def run_local(storyboard, manifest, root, rig, review, evidence, workspace,
              *, approved_animations=None, batch_fn=batch_render,
              compose_fn=compose_animated):
    root = Path(root).resolve()
    workspace = Path(workspace)
    if workspace.exists() or workspace.is_symlink():
        raise LocalRunError("new workspace required")
    if not root.is_dir() or root.is_symlink():
        raise LocalRunError("private episode root required")
    if not workspace.resolve().is_relative_to(root):
        raise LocalRunError("workspace must be inside episode root")
    if not audit_assets(manifest, root)["render_authorized"]:
        raise LocalRunError("art and voice assets must pass QA")
    batch = batch_fn(storyboard, Path(rig), workspace,
                     review_report=Path(review), evidence_path=Path(evidence))
    pinned = attach_animations(manifest, batch, root, workspace)
    # An external reviewer supplies a mapping beat -> expected SHA256. Never
    # infer approval from successful rendering or from a user-controlled flag
    # embedded in the storyboard.
    approvals = approved_animations or {}
    for asset in pinned["assets"]:
        number = str(asset["beat"])
        if approvals.get(number) == asset["godot_animation_sha256"]:
            asset["godot_animation_qa"] = "PASS"
    if not all(a["godot_animation_qa"] == "PASS" for a in pinned["assets"]):
        return {"status": "ANIMATIONS_PENDING_QA",
                "batch_report": str(workspace / "batch_report.json"),
                "animations": [{"beat": a["beat"],
                                "sha256": a["godot_animation_sha256"],
                                "qa": a["godot_animation_qa"]}
                               for a in pinned["assets"]],
                "youtube_upload_authorized": False}
    render_dir = root / "render"
    render_dir.mkdir(exist_ok=True)
    output = render_dir / f"{storyboard['episode_id']}_preview.mp4"
    return compose_fn(pinned, root, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rig", type=Path, required=True)
    parser.add_argument("--review-report", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--animation-approvals", type=Path)
    args = parser.parse_args(argv)
    approvals = (json.loads(args.animation_approvals.read_text(encoding="utf-8"))
                 if args.animation_approvals else None)
    result = run_local(
        json.loads(args.storyboard.read_text(encoding="utf-8")),
        json.loads(args.manifest.read_text(encoding="utf-8")),
        args.root, args.rig, args.review_report, args.evidence,
        args.workspace, approved_animations=approvals)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "ANIMATIONS_PENDING_QA" else 3


if __name__ == "__main__":
    raise SystemExit(main())
