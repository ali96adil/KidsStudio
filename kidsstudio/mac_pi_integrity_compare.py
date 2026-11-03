"""Compare Mac and Pi offline verification reports; never contacts a network."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare_reports(mac: dict, pi: dict) -> dict:
    if not isinstance(mac, dict) or not isinstance(pi, dict):
        raise ValueError("both reports must be JSON objects")
    if mac.get("status") != "READY_FOR_TRANSFER_NOT_TRANSFERRED":
        raise ValueError("unexpected Mac precheck status")
    if pi.get("status") != "PI_MEDIA_VERIFIED_NOT_QUEUED":
        raise ValueError("unexpected Pi precheck status")
    for report in (mac, pi):
        if report.get("network_checked") is not False or report.get("youtube_uploaded") is not False:
            raise ValueError("reports must represent offline prechecks")
        if report.get("public_release_authorized") is not False:
            raise ValueError("reports cannot authorize public release")
        if type(report.get("size")) is not int or report["size"] <= 0:
            raise ValueError("invalid media size")
        digest = report.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid SHA-256")
    match = all(mac.get(key) == pi.get(key) for key in ("episode_id", "size", "sha256"))
    return {
        "status": "MAC_PI_INTEGRITY_MATCH" if match else "MAC_PI_INTEGRITY_MISMATCH",
        "matching": match,
        "episode_id": mac.get("episode_id") if match else None,
        "size": mac["size"] if match else None,
        "sha256": mac["sha256"] if match else None,
        "offline_reports_only": True,
        "network_checked": False,
        "youtube_uploaded": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mac-report", type=Path, required=True)
    parser.add_argument("--pi-report", type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path: Path) -> dict:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
            raise ValueError("invalid report file")
        return json.loads(path.read_text(encoding="utf-8"))
    result = compare_reports(read(args.mac_report), read(args.pi_report))
    print(json.dumps(result, indent=2))
    return 0 if result["matching"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
