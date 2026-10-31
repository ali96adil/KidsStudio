"""Read-only M68 Pi operator diagnostics.

Usage:
 python -m kidsstudio.m68_pi_check --db /private/studio.sqlite \
   --short-id colors-short-01 --series-id colors --media /private/short.mp4

No OAuth token, upload, mutation, or publishing action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_queue import StudioQueue
from .m68_pi_preflight import assess


def main(argv=None):
    parser = argparse.ArgumentParser(description="M68 read-only Pi Shorts readiness")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--short-id", required=True)
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--media", type=Path, required=True)
    args = parser.parse_args(argv)
    # StudioQueue constructor does not create or initialize the database.
    if not args.db.is_file():
        parser.error("existing Pi queue database required")
    result = assess(StudioQueue(args.db), short_id=args.short_id,
                    series_id=args.series_id, media_path=args.media)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_EXPLICIT_PRIVATE_UPLOAD" else 2


if __name__ == "__main__":
    raise SystemExit(main())
