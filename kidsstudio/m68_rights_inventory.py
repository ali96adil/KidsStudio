"""Read-only source asset rights inventory validation for M68 Shorts.

This validates presence, explicit licensing fields and content hashes; it
cannot independently prove legal ownership or the truth of attestations.
Never grants upload or publication rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

KINDS = frozenset(("image", "audio", "music", "font", "video", "voice", "other"))
RIGHTS = frozenset(("original", "licensed", "public_domain", "permission"))


def audit(manifest_path, *, expected_video_sha256):
    path = Path(manifest_path)
    if not path.is_file() or path.is_symlink() or not path.is_absolute():
        raise ValueError("absolute existing non-symlink rights manifest required")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("invalid rights manifest") from exc
    if not isinstance(data, dict):
        raise ValueError("rights manifest must be an object")
    items = data.get("assets")
    if (data.get("schema_version") != 1
            or data.get("video_sha256") != expected_video_sha256
            or not isinstance(items, list) or not items
            or len(items) > 500):
        raise ValueError("rights manifest schema/video identity mismatch")
    reasons = []
    seen = set()
    for i, asset in enumerate(items):
        label = "asset_" + str(i + 1)
        if not isinstance(asset, dict):
            reasons.append(label + ":invalid_record")
            continue
        identity = asset.get("id")
        if not isinstance(identity, str) or not 1 <= len(identity) <= 120 or identity in seen:
            reasons.append(label + ":invalid_or_duplicate_id")
        else:
            seen.add(identity)
            label = identity
        if asset.get("kind") not in KINDS or asset.get("rights_basis") not in RIGHTS:
            reasons.append(label + ":rights_basis_or_kind_missing")
        if (not isinstance(asset.get("source"), str)
                or not 5 <= len(asset["source"].strip()) <= 1000):
            reasons.append(label + ":source_missing")
        if (not isinstance(asset.get("evidence_reference"), str)
                or not 5 <= len(asset["evidence_reference"].strip()) <= 1000):
            reasons.append(label + ":evidence_reference_missing")
        file_name = asset.get("path")
        digest = asset.get("sha256")
        if (not isinstance(file_name, str) or not isinstance(digest, str)
                or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)):
            reasons.append(label + ":asset_hash_missing")
            continue
        asset_path = Path(file_name)
        if (not asset_path.is_absolute() or asset_path.is_symlink()
                or not asset_path.is_file()):
            reasons.append(label + ":asset_file_missing")
            continue
        with asset_path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        if sha != digest:
            reasons.append(label + ":asset_hash_mismatch")
    return {
        "status": "RIGHTS_INVENTORY_DOCUMENTED_NOT_LEGALLY_VERIFIED"
        if not reasons else "BLOCKED_RIGHTS_INVENTORY",
        "video_sha256": expected_video_sha256,
        "assets_checked": len(items),
        "reasons": reasons,
        "legal_rights_independently_verified": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.manifest, expected_video_sha256=args.video_sha256)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["reasons"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
