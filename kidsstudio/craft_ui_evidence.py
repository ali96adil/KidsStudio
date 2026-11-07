"""Offline Craft Anything screenshot evidence intake for KidsStudio's own UI.

Never invokes reverse engineering, MCP, browser navigation or a coding agent.
PNG header/digest checks do NOT certify layout equivalence or complete PNG integrity.
"""
from __future__ import annotations

import argparse
import json
import re
import struct

from .optional_tool_evidence import (
    ToolEvidenceError, private_evidence_file, read_private_json,
)
from .transfer_verify import verify_staged_file

_SHA = re.compile(r"[a-fA-F0-9]{64}\\Z")
_VIEWPORTS = frozenset({375, 768, 1280})
_PNG_HEADER = b"\\x89PNG\\r\\n\\x1a\\n"


def audit_craft_ui_evidence(*, root: str, manifest: dict) -> dict:
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1
            or manifest.get("tool") != "craft-anything"
            or manifest.get("target") != "kidsstudio-owned-dashboard"):
        raise ToolEvidenceError("Only versioned evidence of our own dashboard is accepted.")
    records = manifest.get("screenshots")
    if not isinstance(records, list) or len(records) != 3:
        raise ToolEvidenceError("Exactly three responsive screenshots are required.")
    observed: set[int] = set()
    hashes: set[str] = set()
    summaries = []
    for record in records:
        if not isinstance(record, dict):
            raise ToolEvidenceError("Invalid screenshot record.")
        width = record.get("viewport_css_width")
        if type(width) is not int or width not in _VIEWPORTS or width in observed:
            raise ToolEvidenceError("Screenshot viewport widths must be unique.")
        observed.add(width)
        path = record.get("relative_path")
        expected = record.get("sha256")
        if not isinstance(expected, str) or not _SHA.fullmatch(expected):
            raise ToolEvidenceError("A valid expected screenshot SHA256 is required.")
        evidence = private_evidence_file(root, path, max_bytes=15 * 1024 * 1024)
        verification = verify_staged_file(
            root=root, relative_path=path, expected_sha256=expected,
            max_bytes=15 * 1024 * 1024)
        if verification["status"] != "VERIFIED":
            raise ToolEvidenceError("Screenshot has changed or hash is incorrect.")
        # Checks only the uncompressed IHDR dimensions, not a full PNG decoder.
        with evidence.open("rb") as file:
            header = file.read(24)
        if (len(header) != 24 or header[:8] != _PNG_HEADER
                or header[8:16] != b"\\x00\\x00\\x00\\x0dIHDR"):
            raise ToolEvidenceError("Invalid PNG IHDR header.")
        pixels_w, pixels_h = struct.unpack(">II", header[16:24])
        if not (width <= pixels_w <= width * 4 and
                300 <= pixels_h <= 16000):
            raise ToolEvidenceError("Screenshot pixel dimensions implausible.")
        if expected.lower() in hashes:
            raise ToolEvidenceError("Duplicate screenshot content is not independent evidence.")
        hashes.add(expected.lower())
        summaries.append({
            "viewport_css_width_reported": width,
            "png_pixel_width": pixels_w,
            "png_pixel_height": pixels_h,
            "sha256": expected.lower(),
        })
    if observed != _VIEWPORTS:
        raise ToolEvidenceError("Mobile, tablet and desktop evidence is incomplete.")
    return {
        "status": "CRAFT_UI_EVIDENCE_HASH_VERIFIED_VISUAL_UNREVIEWED",
        "tool": "craft-anything",
        "screenshots": sorted(summaries, key=lambda item: item["viewport_css_width_reported"]),
        "tool_provenance_authenticated": False,
        "viewport_claims_authenticated": False,
        "full_png_decoding_performed": False,
        "pixel_similarity_measured": False,
        "manual_layout_review_required": True,
        "mcp_or_agent_invoked": False,
        "source_code_examined": False,
        "file_mutated": False,
        "production_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline private Craft Anything UI evidence")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--manifest", required=True, help="Relative JSON path under private evidence root")
    args = parser.parse_args(argv)
    try:
        report = audit_craft_ui_evidence(
            root=args.evidence_root,
            manifest=read_private_json(args.evidence_root, args.manifest),
        )
    except (ToolEvidenceError, ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"status": "CRAFT_UI_EVIDENCE_REJECTED",
                          "mcp_or_agent_invoked": False,
                          "production_approved": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
