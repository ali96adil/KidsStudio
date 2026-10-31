"""M68 immutable source-episode provenance binding.

Only a current approved episode with a completed render job may be bound.
The source ID is explicit because storyboard IDs are not database ordinals.
No upload is authorized by this binding.
"""
from __future__ import annotations

import re

from .m68_short_attempt_journal import ShortAttemptError

SOURCE = re.compile(r"^[A-Za-z0-9_-]{2,120}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
JOB = re.compile(r"^[0-9a-f]{32}$")


def initialize(queue):
    with queue._connection(write=True) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS studio_short_source_bindings(
            short_id TEXT PRIMARY KEY,
            series_id TEXT NOT NULL,
            source_episode_id TEXT NOT NULL,
            source_ordinal INTEGER NOT NULL,
            source_render_job_id TEXT NOT NULL,
            source_master_sha256 TEXT NOT NULL,
            bound_at REAL NOT NULL,
            FOREIGN KEY(short_id) REFERENCES studio_derived_shorts(short_id),
            FOREIGN KEY(series_id,source_ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
        )""")


def bind(queue, *, short_id, series_id, source_episode_id, source_ordinal,
         source_render_job_id, source_master_sha256):
    if (not all(isinstance(x, str) and SOURCE.fullmatch(x)
                for x in (short_id, series_id, source_episode_id))
            or type(source_ordinal) is not int or not 1 <= source_ordinal <= 120
            or not isinstance(source_render_job_id, str)
            or not JOB.fullmatch(source_render_job_id)
            or not isinstance(source_master_sha256, str)
            or not SHA.fullmatch(source_master_sha256)):
        raise ShortAttemptError("invalid source provenance identity")
    with queue._connection(write=True) as db:
        short = db.execute("SELECT * FROM studio_derived_shorts WHERE short_id=?",
                           (short_id,)).fetchone()
        episode = db.execute("""SELECT * FROM studio_episodes
            WHERE series_id=? AND ordinal=?""",
            (series_id, source_ordinal)).fetchone()
        job = db.execute("SELECT * FROM jobs WHERE job_id=?",
                         (source_render_job_id,)).fetchone()
        if (not short or short["source_episode_id"] != source_episode_id
                or not episode or episode["state"] != "EPISODE_APPROVED"
                or episode["render_job_id"] != source_render_job_id
                or not job or job["state"] != "COMPLETED"
                or job["kind"] not in ("episode_assemble", "godot_render")):
            raise ShortAttemptError("approved source episode and completed render required")
        from .private_upload_policy import PrivateUploadPolicy
        try:
            PrivateUploadPolicy._approved(
                db, series_id, source_ordinal, source_render_job_id,
                source_master_sha256)
        except Exception as exc:
            raise ShortAttemptError("source master receipt and QA not approved") from exc
        existing = db.execute(
            "SELECT * FROM studio_short_source_bindings WHERE short_id=?",
            (short_id,)).fetchone()
        expected = (series_id, source_episode_id, source_ordinal,
                    source_render_job_id, source_master_sha256)
        if existing:
            actual = tuple(existing[k] for k in (
                "series_id", "source_episode_id", "source_ordinal",
                "source_render_job_id", "source_master_sha256"))
            if actual != expected:
                raise ShortAttemptError("source provenance binding is immutable")
        else:
            db.execute("""INSERT INTO studio_short_source_bindings
                VALUES (?,?,?,?,?,?,?)""",
                (short_id, *expected, queue.clock()))
    return {"status": "SHORT_SOURCE_BOUND_NOT_UPLOAD_APPROVED",
            "short_id": short_id, "series_id": series_id,
            "source_master_sha256": source_master_sha256,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}

def verify_current(db, *, short_id, series_id):
    """Fail closed if source approval or render job changed since binding."""
    row = db.execute("""SELECT b.*,e.state AS episode_state,
        e.render_job_id AS current_render_job,j.state AS job_state,
        j.kind AS job_kind,s.source_episode_id AS current_source_id
        FROM studio_short_source_bindings b
        JOIN studio_episodes e ON e.series_id=b.series_id
            AND e.ordinal=b.source_ordinal
        JOIN jobs j ON j.job_id=b.source_render_job_id
        JOIN studio_derived_shorts s ON s.short_id=b.short_id
        WHERE b.short_id=? AND b.series_id=?""",
        (short_id, series_id)).fetchone()
    if (not row or row["episode_state"] != "EPISODE_APPROVED"
            or row["current_render_job"] != row["source_render_job_id"]
            or row["current_source_id"] != row["source_episode_id"]
            or row["job_state"] != "COMPLETED"
            or row["job_kind"] not in ("episode_assemble", "godot_render")):
        raise ShortAttemptError("current approved source provenance required")
    from .private_upload_policy import PrivateUploadPolicy
    try:
        PrivateUploadPolicy._approved(
            db, series_id, row["source_ordinal"],
            row["source_render_job_id"], row["source_master_sha256"])
    except Exception as exc:
        raise ShortAttemptError("current approved master receipt and QA required") from exc
    return row["source_master_sha256"]
