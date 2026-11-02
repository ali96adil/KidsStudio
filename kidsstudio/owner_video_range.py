"""Strict single HTTP byte-range parsing for local private video previews."""
from __future__ import annotations

import re

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
MAX_CHUNK = 8 * 1024 * 1024

def parse_range(header: str | None, size: int) -> tuple[int, int, bool]:
    """Return inclusive (start,end,partial). Raise ValueError for invalid ranges."""
    if type(size) is not int or size <= 0:
        raise ValueError("empty or invalid media file")
    if header is None:
        return 0, min(size, MAX_CHUNK) - 1, size > MAX_CHUNK
    if not isinstance(header, str):
        raise ValueError("invalid range")
    match = RANGE_RE.fullmatch(header.strip())
    if match is None or not any(match.groups()):
        raise ValueError("only one byte range is supported")
    first, last = match.groups()
    if first:
        start = int(first)
        if start >= size:
            raise ValueError("range starts after end of file")
        end = min(int(last), size - 1) if last else size - 1
        if end < start:
            raise ValueError("range end precedes start")
    else:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("invalid suffix length")
        start = max(0, size - suffix)
        end = size - 1
    end = min(end, start + MAX_CHUNK - 1)
    return start, end, True
