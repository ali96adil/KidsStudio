"""M15: synthetic channel analytics, cautious comparison and owner adoption gates."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from datetime import date,timedelta

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_learning import LearningLedger,LearningError


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.queue=StudioQueue(self.root/"brain.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue);self.series.initialize()
        lessons=[{"title":f"Color lesson {i}","objective":f"Recognize color {i}"}
                 for i in range(1,10)]
        self.series.create_series("colors-ar","Colors","ar",lessons,activate=True)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='EPISODE_APPROVED',
                source_sha256=? WHERE series_id='colors-ar' AND ordinal<=8""",("a"*64,))
        self.ledger=LearningLedger(self.queue)
        self.ledger.initialize()
        self.file=self.root/"youtube_owner_export.json"
        today=date.today()-timedelta(days=3)
        published=(today-timedelta(days=7)).isoformat()
        snapshot=today.isoformat()
        profiles=[]
        metrics=[]
        for ordinal in range(1,9):
            good=ordinal<=4
            profiles.append({
                "series_id":"colors-ar","ordinal":ordinal,
                "video_id":f"video{ordinal:06d}",
                "language":"ar","format_type":"long",
                "duration_seconds":105,
                "published_date":published,
                "hook_style":"question_first" if good else "story_first",
                "story_style":"original_adventure",
                "pace_style":"calm",
                "participation_style":"ask_and_pause",
                "owner_education_verified":True,
            })
            metrics.append({
                "series_id":"colors-ar","ordinal":ordinal,
                "video_id":f"video{ordinal:06d}",
                "snapshot_date":snapshot,"window_days":7,
                "views":650 if good else 220,
                "impressions":6000 if good else 1800,
                "ctr_percent":7.0 if good else 3.2,
                "average_view_percentage":75.0 if good else 48.0,
                "average_view_duration_seconds":78.75 if good else 50.4,
                "estimated_watch_minutes":850.0 if good else 180.0
            })
        self.packet={"schema_version":1,
                     "source":"OWNER_VERIFIED_YOUTUBE_STUDIO_EXPORT",
                     "profiles":profiles,"metrics":metrics}
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.packet,ensure_ascii=False),
                             encoding="utf-8")

    def test_import_compare_propose_then_explicit_owner_adopts(self):
        imported=self.ledger.import_export(self.file)
        self.assertEqual(imported["new_snapshots"],8)
        self.assertGreaterEqual(imported["new_learning_proposals"],1)
        self.assertFalse(imported["production_modified"])
        report=self.ledger.analyze("colors-ar")
        self.assertEqual(report["status"],"OBSERVATIONAL_LEARNING_ONLY")
        self.assertEqual(report["new_proposals"],0)
        proposal=next(x for x in self.ledger.snapshot("colors-ar")["proposals"]
                      if x["feature"]=="hook_style")
        self.assertEqual(proposal["candidate"],"question_first")
        self.assertEqual(proposal["baseline"],"story_first")
        self.assertEqual(proposal["state"],"PROPOSED")
        self.assertEqual(proposal["evidence"]["confidence"],
                         "OBSERVATIONAL_EXPLORATORY_NOT_CAUSAL")
        self.assertGreater(proposal["evidence"]["retention_point_difference"],8)
        with self.queue._connection() as db:
            before=db.execute("""SELECT state,source_sha256 FROM studio_episodes
                ORDER BY ordinal""").fetchall()
            before=[tuple(x) for x in before]
        decision=self.ledger.decide(
            proposal["id"],decision="ADOPT_FOR_FUTURE_EXPERIMENT",
            owner_note="Try new question-first introductions while preserving distinct "
                       "original stories, accurate color learning and age safety.")
        self.assertFalse(decision["publication_authorized"])
        with self.queue._connection() as db:
            after=[tuple(x) for x in db.execute("""SELECT state,source_sha256
                FROM studio_episodes ORDER BY ordinal""")]
        self.assertEqual(before,after)
        self.assertEqual(self.ledger.snapshot("colors-ar")["proposals"][0]["state"],
                         "ADOPT_FOR_FUTURE_EXPERIMENT")
        with self.assertRaises(LearningError):
            self.ledger.decide(proposal["id"],decision="REJECT",
                               owner_note="Cannot silently reverse approved experiments")

    def test_adopted_learning_only_enters_next_original_script_brief(self):
        from kidsstudio.local_worker import _prompts
        self.ledger.import_export(self.file)
        idea=next(item for item in self.ledger.snapshot("colors-ar")["proposals"]
                  if item["feature"]=="hook_style")
        self.ledger.decide(
            idea["id"],decision="ADOPT_FOR_FUTURE_EXPERIMENT",
            owner_note="An original question-first opening is a controlled experiment; "
                       "do not copy previous stories, weaken learning or remove manual QA.")
        queued=self.series.plan_drafts(limit=1)
        self.assertEqual(len(queued),1)
        with self.queue._connection() as db:
            record=db.execute("SELECT payload FROM jobs WHERE job_id=?",
                              (queued[0]["job_id"],)).fetchone()
        payload=json.loads(record["payload"])
        self.assertEqual(payload["learning_experiment"]["feature"],"hook_style")
        self.assertEqual(payload["learning_experiment"]["style"],"question_first")
        _,prompt,_=_prompts("script_draft",payload)
        self.assertIn("original",prompt)
        self.assertIn("not proof of causality",prompt)
        self.assertFalse("script_text" in payload)
        with self.queue._connection() as db:
            row=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
        self.assertEqual(row["state"],"EPISODE_APPROVED")

    def test_insufficient_data_never_fabricates_a_winner(self):
        self.packet["profiles"]=self.packet["profiles"][:2]
        self.packet["metrics"]=self.packet["metrics"][:2]
        self.save()
        self.ledger.import_export(self.file)
        report=self.ledger.analyze("colors-ar")
        self.assertTrue(report["insufficient_data"])
        self.assertEqual(report["new_proposals"],0)
        self.assertEqual(self.ledger.snapshot("colors-ar")["proposals"],[])

    def test_wrong_video_identity_blocks_entire_import_transaction(self):
        self.packet["metrics"][-1]["video_id"]="incorrect00"
        self.save()
        with self.assertRaises(LearningError):
            self.ledger.import_export(self.file)
        with self.queue._connection() as db:
            count=db.execute("SELECT COUNT(*) FROM studio_video_profiles").fetchone()[0]
        self.assertEqual(count,0)

    def test_reject_invalid_ctr_and_unsupported_sample(self):
        self.packet["metrics"][0]["ctr_percent"]=120.0
        self.save()
        with self.assertRaises(LearningError):
            self.ledger.import_export(self.file)
        self.packet["metrics"][0]["ctr_percent"]=7.0
        self.packet["profiles"][0]["owner_education_verified"]=False
        self.save()
        with self.assertRaises(LearningError):
            self.ledger.import_export(self.file)

    def test_import_is_immutable_and_idempotent_for_same_original_export(self):
        self.ledger.import_export(self.file)
        self.assertEqual(self.ledger.import_export(self.file)["new_snapshots"],0)
        self.packet["metrics"][0]["views"]=999999
        self.save()
        with self.assertRaises(LearningError):
            self.ledger.import_export(self.file)
        with self.queue._connection() as db:
            original=db.execute("""SELECT views FROM studio_video_metrics
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()[0]
        self.assertEqual(original,650)

    def test_short_and_long_metrics_not_compared(self):
        self.packet["profiles"][4]["format_type"]="short"
        self.packet["profiles"][5]["format_type"]="short"
        self.packet["profiles"][6]["format_type"]="short"
        self.packet["profiles"][7]["format_type"]="short"
        self.packet["profiles"][4]["duration_seconds"]=40
        self.packet["profiles"][5]["duration_seconds"]=40
        self.packet["profiles"][6]["duration_seconds"]=40
        self.packet["profiles"][7]["duration_seconds"]=40
        self.save()
        self.ledger.import_export(self.file)
        self.assertEqual(self.ledger.analyze("colors-ar")["new_proposals"],0)

    def test_shorts_can_learn_without_thumbnail_impressions_or_ctr(self):
        # Made-for-Kids and Shorts dashboards can show unavailable reach.
        # We must NOT interpret missing CTR as 0 or block all Shorts insights.
        for item in self.packet["profiles"]:
            item["format_type"]="short"
            item["duration_seconds"]=40
        for i,item in enumerate(self.packet["metrics"]):
            item["impressions"]=0
            item["ctr_percent"]=None
            item["average_view_duration_seconds"]=30.0 if i<4 else 19.0
        self.save()
        report=self.ledger.import_export(self.file)
        self.assertGreaterEqual(report["new_learning_proposals"],1)
        ideas=self.ledger.snapshot("colors-ar")["proposals"]
        hook=next(p for p in ideas if p["feature"]=="hook_style")
        self.assertEqual(hook["evidence"]["segment"]["format"],"short")
        self.assertIsNone(hook["evidence"]["winner"]["median_ctr_pct"])
        self.assertEqual(hook["evidence"]["candidate"] if "candidate" in hook["evidence"] else hook["candidate"],
                         "question_first")
        self.assertFalse(hook["evidence"]["automatic_script_change"])

    def test_unapproved_episode_and_unqualified_owner_note_blocked(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='PLANNED'
                          WHERE series_id='colors-ar' AND ordinal=7""")
        with self.assertRaises(LearningError):
            self.ledger.import_export(self.file)
        with self.assertRaises(LearningError):
            self.ledger.decide("a"*32,decision="ADOPT_FOR_FUTURE_EXPERIMENT",
                              owner_note="yes")


if __name__=="__main__":
    unittest.main()
