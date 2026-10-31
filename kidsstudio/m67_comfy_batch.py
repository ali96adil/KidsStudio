"""M67 execute six local ComfyUI jobs with explicit API workflow templates.

Each workflow must contain an operator-selected CLIPTextEncode node ID.
Images are collected without QA approval and no network other than localhost.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .m67_comfy_worker import run_workflow
from .m67_comfy_collect import collect_png


class ImageBatchError(RuntimeError):
    pass


def render_images(packet, workflow_template, root, *, text_node,
                  base="http://127.0.0.1:8188",
                  worker=run_workflow, collector=collect_png):
    root = Path(root).resolve()
    if packet.get("status") != "MEDIA_JOBS_PREPARED_NOT_GENERATED":
        raise ImageBatchError("invalid job packet")
    if not root.is_dir() or root.is_symlink():
        raise ImageBatchError("existing private episode root required")
    if text_node not in workflow_template:
        raise ImageBatchError("missing prompt text node")
    node = workflow_template[text_node]
    if node.get("class_type") != "CLIPTextEncode" or "text" not in node.get("inputs", {}):
        raise ImageBatchError("CLIPTextEncode text input required")
    if not any(n.get("class_type") == "SaveImage"
               for n in workflow_template.values() if isinstance(n, dict)):
        raise ImageBatchError("SaveImage required")
    report = {"episode_id": packet["episode_id"],
              "status": "RUNNING", "images": [],
              "visual_qa": "PENDING", "youtube_upload_authorized": False}
    report_file = root / "comfy_batch_report.json"
    if report_file.exists():
        raise ImageBatchError("existing batch report; do not overwrite")
    def save():
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    save()
    for job in packet["jobs"]:
        beat = job["beat"]
        target = root / job["visual"]["output"]
        if target.exists() or target.is_symlink():
            report["status"] = "BLOCKED"
            save()
            raise ImageBatchError("image already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        workflow = copy.deepcopy(workflow_template)
        workflow[text_node]["inputs"]["text"] = job["visual"]["description"]
        try:
            result = worker(workflow, base=base)
            if len(result["images"]) != 1:
                raise ImageBatchError("expected exactly one image per beat")
            collected = collector(result["images"][0], target, base=base)
            report["images"].append({"beat": beat, "status": "PENDING_QA",
                                     "sha256": collected["sha256"],
                                     "file": job["visual"]["output"]})
            save()
        except Exception as exc:
            report["status"] = "BLOCKED"
            report["failed_beat"] = beat
            report["error_type"] = type(exc).__name__
            save()
            raise ImageBatchError(f"ComfyUI image batch failed at beat {beat}") from exc
    report["status"] = "IMAGES_GENERATED_PENDING_QA"
    save()
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--workflow", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--text-node", required=True)
    args = p.parse_args(argv)
    report = render_images(
        json.loads(args.jobs.read_text(encoding="utf-8")),
        json.loads(args.workflow.read_text(encoding="utf-8")),
        args.root, text_node=args.text_node)
    print(json.dumps({"status": report["status"],
                      "images": len(report["images"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
