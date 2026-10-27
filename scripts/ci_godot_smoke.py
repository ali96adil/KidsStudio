"""CI end-to-end Godot 4.7.2 + FFmpeg smoke with generated synthetic layers.

This intentionally uses NO children's media, proprietary character art, online
model inference, ComfyUI or vision-model credentials. Real Godot executes the
checked-in rig player and must produce a real MP4 (not mock subprocesses).
"""
from __future__ import annotations

import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import subprocess
import sys
import threading

from PIL import Image, ImageDraw

from kidsstudio.godot_export import export_godot
from kidsstudio.coordinator_api import Coordinator, create_handler
from kidsstudio.media_worker import MediaRecipes, MediaJournal, RemoteMediaWorker
from kidsstudio.remote_worker import RemoteClient
from kidsstudio.studio_queue import StudioQueue


def _layer(name: str, canvas: tuple[int, int]) -> Image.Image:
    art = Image.new("RGBA", canvas)
    pen = ImageDraw.Draw(art)
    shapes: dict[str, tuple[str, tuple[int, int, int, int], tuple[int, int, int, int]]] = {
        "body": ("ellipse", (35, 50, 91, 107), (242, 190, 163, 255)),
        "head": ("ellipse", (30, 24, 99, 71), (244, 195, 170, 255)),
        "arm_left": ("ellipse", (17, 56, 43, 95), (228, 155, 145, 255)),
        "arm_right": ("ellipse", (87, 54, 113, 97), (230, 162, 150, 255)),
        "leg_left": ("ellipse", (42, 97, 59, 125), (239, 176, 170, 255)),
        "leg_right": ("ellipse", (66, 98, 83, 125), (240, 178, 172, 255)),
        "ear_left": ("ellipse", (38, 4, 52, 36), (240, 176, 160, 255)),
        "ear_right": ("ellipse", (76, 5, 90, 37), (241, 177, 161, 255)),
        "eyes": ("ellipse", (49, 41, 56, 48), (25, 20, 24, 255)),
        "mouth": ("ellipse", (62, 54, 68, 60), (103, 45, 51, 255)),
    }
    _, bounds, fill = shapes[name]
    pen.ellipse(bounds, fill=fill)
    return art


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/ci_godot_smoke.py /tmp/safe-test-root")
    base = Path(sys.argv[1]).expanduser().resolve()
    if base.exists():
        raise FileExistsError("Smoke root must not exist to protect earlier render.")
    (base / "source" / "assets").mkdir(parents=True)
    width, height = 128, 128
    pivots: dict[str, list[int]] = {
        "body": [64, 65], "head": [64, 65],
        "arm_left": [39, 59], "arm_right": [91, 57],
        "leg_left": [51, 100], "leg_right": [73, 100],
        "ear_left": [46, 31], "ear_right": [83, 32],
        "eyes": [53, 43], "mouth": [65, 57],
    }
    names = list(pivots)
    for part_id in names:
        _layer(part_id, (width, height)).save(
            base / "source" / "assets" / (part_id + ".png")
        )
    manifest = {
        "schema_version": 1,
        "character_id": "ci_synthetic_bunny",
        "canvas": {"width": width, "height": height},
        "parts": [
            {
                "id": name, "file": "assets/" + name + ".png",
                "pivot": pivots[name], "z": i,
            }
            for i, name in enumerate(names)
        ],
    }
    rig_file = base / "source" / "rig.json"
    rig_file.write_text(json.dumps(manifest), encoding="utf-8")
    # Generate only 3 frames to minimize public-CI GPU/CPU cost, while
    # executing GDScript, textures, timeline and video encoding end-to-end.
    spec = {
        "schema_version": 1,
        "fps": 30,
        "duration_seconds": 0.1,
        "beats": [{"start": 0, "end": 0.1, "motion": "wave_right"}],
    }
    scene_file = base / "source" / "scene.json"
    scene_file.write_text(json.dumps(spec), encoding="utf-8")
    project = base / "godot_project"
    exported = export_godot(rig_file, scene_file, project)
    assert exported["status"] == "PREVIEW_ONLY_UNAPPROVED"
    # Actual coordinator + HTTPS + media worker + real Godot/FFmpeg in one
    # bounded 3-frame run. No paid models, personal art or API secrets.
    report_file = project / "export_report.json"
    digest = hashlib.sha256(report_file.read_bytes()).hexdigest()
    recipes_file = base / "test_media_recipes.json"
    recipes_file.write_text(json.dumps({
        "schema_version": 1,
        "recipes": {
            "synthetic_scene_ci": {
                "kind": "godot_render",
                "output_root": str(base / "movie"),
                "inputs": {"project_report": str(report_file)},
                "sha256": {"project_report": digest},
            }
        },
    }), encoding="utf-8")

    queue = StudioQueue(base / "pi_queue.sqlite")
    queue.initialize()
    job = queue.enqueue(
        kind="godot_render", request_key="native-3frames-v1",
        payload={"recipe_id": "synthetic_scene_ci"},
    )
    token = "CI-only-not-an-actual-secret-" + "g" * 40
    coordinator = Coordinator(
        queue, base / "pi_vault",
        {"mac-media-01": (token, {"godot_render"})}
    )
    cert = base / "cert.pem"
    key = base / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-nodes", "-sha256", "-days", "1",
        "-keyout", str(key), "-out", str(cert),
        "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost",
    ], check=True, capture_output=True, timeout=30)
    listener = ThreadingHTTPServer(
        ("127.0.0.1", 0), create_handler(coordinator)
    )
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(str(cert), str(key))
    listener.socket = ssl_context.wrap_socket(listener.socket, server_side=True)
    threading.Thread(target=listener.serve_forever, daemon=True).start()
    try:
        client = RemoteClient(
            f"https://localhost:{listener.server_port}",
            worker_id="mac-media-01", token=token, ca_file=str(cert)
        )
        worker = RemoteMediaWorker(
            client, MediaRecipes(recipes_file),
            MediaJournal(base / "mac_receipts.sqlite")
        )
        done = worker.run_once()
        if done["status"] != "COMPLETED":
            raise RuntimeError("Pi-to-Mac real render was not acknowledged.")
    finally:
        listener.shutdown()
        listener.server_close()

    mp4 = base / "movie" / job["job_id"] / "character_preview.mp4"
    render_report = json.loads(
        (mp4.parent / "render_report.json").read_text(encoding="utf-8")
    )
    state = json.loads(queue.get(job["job_id"])["result_json"])
    actual_hash = hashlib.sha256(mp4.read_bytes()).hexdigest()
    if not mp4.is_file() or mp4.stat().st_size <= 1000:
        raise RuntimeError("Godot/FFmpeg did not produce a usable video file.")
    if render_report["frames_expected"] != 3:
        raise RuntimeError("Godot produced unexpected frame count.")
    if (state["artifact_sha256"] != actual_hash or
        state["status"] != "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW" or
        state["publication_approved"] is not False):
        raise RuntimeError("Pi media report failed provenance/approval checks.")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(mp4), "-frames:v", "1", "-f", "null", "-",
    ], check=True, capture_output=True, timeout=30)
    print("REAL_GODOT_PI_MAC_TLS_SMOKE_PASS")
    print(json.dumps({
        "status": state["status"],
        "mp4_bytes": mp4.stat().st_size,
        "mp4_sha256": actual_hash,
        "frames_expected": render_report["frames_expected"],
        "asset_status": exported["status"],
        "coordinator_state": queue.get(job["job_id"])["state"],
        "publication_approved": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
