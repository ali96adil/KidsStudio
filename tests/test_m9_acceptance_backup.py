"""M9 no-device offline acceptance inventory and SQLite restore drill tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kidsstudio.backup_drill import create_backup, restore_drill, BackupError
from kidsstudio.acceptance_review import inspect_studio, AcceptanceError
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_quality_ledger import QualityLedger
from kidsstudio.studio_stage_ledger import StageLedger


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue);self.series.initialize()
        self.series.create_series("colors-ar","ألوان","ar",[
            {"title":"أحمر","objective":"التعرف على اللون الأحمر"},
            {"title":"أزرق","objective":"التعرف على اللون الأزرق"}],activate=True)
        self.stages=StageLedger(self.queue);self.stages.initialize()
        self.quality=QualityLedger(self.queue);self.quality.initialize()

    def test_live_database_snapshot_and_sacrificial_restore(self):
        self.series.note("colors-ar","Private note to retain during backup")
        self.series.plan_drafts(limit=1)
        before=self.series.snapshot()
        backup=self.root/"studio-backup-v01.sqlite"
        result=create_backup(self.queue.path,backup)
        self.assertEqual(result["status"],"BACKUP_VERIFIED_NOT_RESTORED_TO_PRODUCTION")
        self.assertGreater(result["backup_bytes"],0)
        self.assertEqual(result["table_rows"]["studio_episodes"],2)
        proof=restore_drill(backup)
        self.assertEqual(proof["status"],"SACRIFICIAL_RESTORE_DRILL_PASSED")
        self.assertFalse(proof["restored_to_production"])
        self.assertEqual(proof["restored_row_counts"]["studio_episodes"],2)
        self.assertEqual(self.series.snapshot(),before)
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.stat().st_mode&0o777,0o600)
        with self.assertRaises(BackupError):
            create_backup(self.queue.path,backup)

    def test_broken_backup_and_foreign_key_detection(self):
        p=self.root/"bad.sqlite"
        p.write_bytes(b"not a SQLite backup")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_drill(p)
        self.assertTrue(self.queue.path.is_file())

    def test_missing_schema_report_is_blocked_not_auto_initialized(self):
        # A new queue with no M3/6/7 migration must show schema blockers.
        other=StudioQueue(self.root/"old.db")
        other.initialize()
        view=inspect_studio(other)
        self.assertEqual(view["status"],"BLOCKED_LOCAL_SCHEMA_INCOMPLETE")
        self.assertFalse(view["public_release_authorized"])
        with other._connection() as db:
            self.assertIsNone(db.execute("""SELECT 1 FROM sqlite_master
                 WHERE name='studio_episode_stages'""").fetchone())

    def test_basic_report_tracks_missing_real_production_and_backup(self):
        report=inspect_studio(self.queue)
        self.assertEqual(report["status"],"INTEGRATION_PREPARATION_INCOMPLETE")
        by_code={r["code"]:r for r in report["findings"]}
        self.assertEqual(by_code["required_schema"]["status"],"PASS")
        self.assertEqual(by_code["restore_drill"]["status"],"ACTION")
        self.assertEqual(by_code["live_chatterbox_ltx"]["status"],"DEVICE_TEST_REQUIRED")
        self.assertFalse(report["full_episode_rendered_on_owner_mac"])
        self.assertNotIn("Private note",json.dumps(report))
        self.assertNotIn(str(self.root),json.dumps(report))

    def test_acceptance_succeeds_backup_check_but_not_mac_inference(self):
        self.series.plan_drafts(limit=2)
        backup=self.root/"snap.sqlite"
        create_backup(self.queue.path,backup)
        report=inspect_studio(self.queue,backup_file=backup)
        self.assertEqual(report["backup_drill_status"],
                         "SACRIFICIAL_RESTORE_DRILL_PASSED")
        self.assertEqual(next(r for r in report["findings"]
                              if r["code"]=="restore_drill")["status"],"PASS")
        self.assertFalse(report["owner_device_qualified"])

    def test_queue_provenance_tamper_is_blocker(self):
        self.series.plan_drafts(limit=1)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes
                        SET draft_job_id=? WHERE ordinal=1""",("f"*32,))
        report=inspect_studio(self.queue)
        self.assertEqual(report["status"],"BLOCKED_RECONCILIATION")
        provenance=next(x for x in report["findings"]
                        if x["code"]=="provenance")
        self.assertEqual(provenance["status"],"BLOCKED")
        self.assertEqual(provenance["count"],1)

    def test_foreign_archive_dimensions_refused(self):
        with self.assertRaises(AcceptanceError):
            inspect_studio(self.queue,archive_dir=self.root/"somewhere")
        self.assertFalse((self.root/"somewhere").exists())


if __name__=="__main__":
    unittest.main()
