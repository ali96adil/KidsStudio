"""M68 source binding must reject a fake approved episode without M26 receipt."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_source_binding import initialize, bind
from kidsstudio.m68_short_attempt_journal import ShortAttemptError


class SourceReceiptTests(unittest.TestCase):
    def test_completed_job_without_render_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            q = StudioQueue(Path(root) / "queue.sqlite")
            q.initialize()
            ShortRegistry(q).initialize()
            with q._connection(write=True) as db:
                db.execute("""CREATE TABLE studio_series(
                    series_id TEXT PRIMARY KEY,state TEXT)""")
                db.execute("INSERT INTO studio_series VALUES('colors','ACTIVE')")
                db.execute("""CREATE TABLE studio_episodes(
                    series_id TEXT,ordinal INTEGER,state TEXT,render_job_id TEXT,
                    PRIMARY KEY(series_id,ordinal))""")
                db.execute("""INSERT INTO studio_episodes VALUES(
                    'colors',1,'EPISODE_APPROVED',?)""", ("a" * 32,))
                db.execute("""INSERT INTO jobs(job_id,request_key,kind,payload,state,
                    max_attempts,available_at,created_at,updated_at,result_json)
                    VALUES (?,?,?,?,?,1,?,?,?,?)""",
                    ("a" * 32, "source-render", "episode_assemble", "{}",
                     "COMPLETED", 0, 0, 0, "{}"))
            ShortRegistry(q).register(short_id="colors-short-01",
                source_episode_id="colors-ep-01", media_sha256="b" * 64)
            initialize(q)
            with self.assertRaises(ShortAttemptError):
                bind(q, short_id="colors-short-01", series_id="colors",
                    source_episode_id="colors-ep-01", source_ordinal=1,
                    source_render_job_id="a" * 32,
                    source_master_sha256="c" * 64)
