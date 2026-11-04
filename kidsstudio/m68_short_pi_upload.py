"""M68 one-shot PRIVATE-only Shorts upload on Pi.

Explicit invocation only. Persist attempt before Google network; never retry an
uncertain upload. Uses existing M25 HTTPS transport and M68 journal.
"""
from __future__ import annotations

from pathlib import Path

from .m68_short_attempt_journal import ShortAttemptJournal, ShortAttemptError
from .youtube_private_upload import (
    GoogleYouTubeTransport, CHUNK, CHANNEL, file_sha256,
)


def upload_short_private(queue, *, short_id, series_id, media_sha256,
                         media_path, channel_id, title, description,
                         made_for_kids, contains_synthetic_media,
                         token, transport=None):
    path = Path(media_path)
    if (not path.is_absolute() or path.is_symlink() or path.suffix.lower() != ".mp4"
            or not path.is_file() or not 1000 <= path.stat().st_size <= 10*1024**3
            or file_sha256(path) != media_sha256):
        raise ShortAttemptError("exact local staged MP4 SHA required")
    if (not isinstance(channel_id, str) or not CHANNEL.fullmatch(channel_id)
            or not isinstance(title, str) or not 1 <= len(title.strip()) <= 100
            or not isinstance(description, str) or len(description) > 4800
            or type(made_for_kids) is not bool
            or type(contains_synthetic_media) is not bool
            or not isinstance(token, str) or len(token) < 30
            or any(c.isspace() for c in token)):
        raise ShortAttemptError("valid private upload metadata and token required")
    with queue._connection() as db:
        policy = db.execute(
            """SELECT state,channel_id,allowed_made_for_kids,
                      allowed_synthetic_media FROM studio_youtube_private_policies
               WHERE series_id=?""", (series_id,)).fetchone()
        if (not policy or policy["state"] != "ENABLED"
                or policy["channel_id"] != channel_id
                or bool(policy["allowed_made_for_kids"]) != made_for_kids
                or bool(policy["allowed_synthetic_media"]) != contains_synthetic_media):
            raise ShortAttemptError("current owner private policy mismatch")
    # Revalidate staged identity and six-axis QA immediately before the one-shot
    # journal write. A quota reservation alone is never editorial approval.
    with queue._connection() as db:
        short = db.execute(
            "SELECT * FROM studio_derived_shorts WHERE short_id=?",
            (short_id,)).fetchone()
        review = db.execute(
            "SELECT * FROM studio_short_reviews WHERE short_id=?",
            (short_id,)).fetchone()
        if (not short or short["state"] != "PI_STAGED_NOT_APPROVED"
                or short["media_sha256"] != media_sha256
                or not review or review["short_id"] != short_id
                or review["media_sha256"] != media_sha256
                or review["source_episode_id"] != short["source_episode_id"]
                or review["decision"] != "PASS"):
            raise ShortAttemptError("staged short and matching approved QA required")
        import json
        from .m68_short_content_review import CHECKS
        try:
            checks = json.loads(review["checks_json"])
        except (TypeError, ValueError) as exc:
            raise ShortAttemptError("invalid persisted QA") from exc
        if (not isinstance(checks, dict) or set(checks) != set(CHECKS)
                or any(checks[key] is not True for key in CHECKS)):
            raise ShortAttemptError("six independent QA checks must pass")
    from .m68_pi_preflight import assess
    preflight = assess(queue, short_id=short_id, series_id=series_id,
                       media_path=path)
    if preflight["status"] != "READY_FOR_EXPLICIT_PRIVATE_UPLOAD":
        raise ShortAttemptError(
            "Pi upload preflight blocked: " + ",".join(preflight["reasons"]))
    journal = ShortAttemptJournal(queue)
    journal.begin(short_id=short_id, series_id=series_id, media_sha256=media_sha256)
    transport = transport if transport is not None else GoogleYouTubeTransport()
    metadata = {
        "snippet": {"title": title.strip(), "description": description,
                    "categoryId": "27"},
        "status": {"privacyStatus": "private",
                   "selfDeclaredMadeForKids": made_for_kids,
                   "containsSyntheticMedia": contains_synthetic_media},
    }
    try:
        size = path.stat().st_size
        # Recheck bytes immediately before contacting Google. If a producer
        # replaced the file after the journal write, quarantine without upload.
        if file_sha256(path) != media_sha256:
            raise ShortAttemptError("staged media changed before Google request")
        session = transport.start(token, metadata, size)
        offset = 0
        video_id = None
        with path.open("rb") as stream:
            while offset < size:
                stream.seek(offset)
                block = stream.read(min(CHUNK, size - offset))
                if not block:
                    raise ShortAttemptError("media truncated during upload")
                status, next_value = transport.put_chunk(token, session, block, offset, size)
                if status in (200, 201):
                    if offset + len(block) != size:
                        raise ShortAttemptError("premature upload completion")
                    video_id = next_value
                    break
                if status != 308 or type(next_value) is not int or next_value != offset + len(block):
                    raise ShortAttemptError("unexpected YouTube resumable offset")
                offset = next_value
        if file_sha256(path) != media_sha256:
            raise ShortAttemptError("media changed during upload")
        if not video_id:
            raise ShortAttemptError("no final YouTube video ID")
        journal.record_upload_result(short_id=short_id, series_id=series_id,
                                     media_sha256=media_sha256, video_id=video_id)
        return journal.verify_private(
            short_id=short_id, series_id=series_id, media_sha256=media_sha256,
            video_id=video_id, channel_id=channel_id, token=token, transport=transport)
    except Exception:
        # Never erase or retry; network may already have uploaded the video.
        journal.mark_manual(short_id=short_id)
        raise
