"""M67 retrieve an output PNG from local ComfyUI into a new asset path.

Download is bounded and validated for PNG signature and dimensions.
No automatic QA approval or overwrite is allowed.
"""
from __future__ import annotations

from pathlib import Path
import struct
from urllib.parse import urlencode
from urllib.request import urlopen

from .m67_comfy_worker import _endpoint, ComfyWorkerError
from .m67_production_handoff import _sha


def collect_png(image, destination, *, base="http://127.0.0.1:8188",
                max_bytes=20_000_000):
    endpoint = _endpoint(base)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ComfyWorkerError("destination exists")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ComfyWorkerError("existing output directory required")
    if not 1024 <= max_bytes <= 100_000_000:
        raise ComfyWorkerError("invalid byte limit")
    if image.get("type") != "output":
        raise ComfyWorkerError("only ComfyUI output files allowed")
    filename = image.get("filename")
    subfolder = image.get("subfolder", "")
    if not isinstance(filename, str) or not filename.endswith(".png"):
        raise ComfyWorkerError("PNG filename required")
    if not isinstance(subfolder, str):
        raise ComfyWorkerError("invalid subfolder")
    # The ComfyUI server resolves filenames itself; do not allow path
    # separators or traversal in either component.
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ComfyWorkerError("invalid filename")
    if subfolder not in ("", "."):
        raise ComfyWorkerError("subfolders require manual inspection")
    query = urlencode({"filename": filename, "subfolder": "",
                       "type": "output"})
    with urlopen(endpoint + "/view?" + query, timeout=60) as response:
        blob = response.read(max_bytes + 1)
    if len(blob) > max_bytes or len(blob) < 24:
        raise ComfyWorkerError("invalid image size")
    if blob[:8] != b"\x89PNG\r\n\x1a\n" or blob[12:16] != b"IHDR":
        raise ComfyWorkerError("not a PNG")
    width, height = struct.unpack(">II", blob[16:24])
    if (width, height) != (1280, 720):
        raise ComfyWorkerError("unexpected image dimensions")
    destination.write_bytes(blob)
    return {"status": "IMAGE_COLLECTED_PENDING_QA",
            "path": str(destination),
            "sha256": _sha(destination),
            "visual_qa": "PENDING"}
