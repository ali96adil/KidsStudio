"""M8 offline engine, immutable archive and private preview readiness tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.engine_qualification import (
    EngineQualificationError, qualify_engine,
)
from kidsstudio.private_archive import (
    ArchiveError, archive, preflight, verify_archive
)
from kidsstudio.private_release import check_readiness, PrivateReleaseError
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_quality_ledger import QualityLedger, CRITERIA


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda:inp.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


class M8TestBase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.checkpoint=self.root/"ltx_model.safetensors"
        self.checkpoint.write_bytes(b"model-weight-bytes-only")
        self.engine_manifest=self.root/"ltx_engine.json"
        self.model_data={
            "schema_version":1,"kind":"ltx_animate","engine":"ltx_2_3_mlx",
            "platform":"Darwin","arch":"arm64","minimum_memory_gib":32,
            "network_required":False,"checkpoints":[{
                "role":"model","path":str(self.checkpoint),"sha256":sha(self.checkpoint)
            }]
        }
        self.engine_manifest.write_text(json.dumps(self.model_data))
        self.master=self.root/"private_video.mp4"
        self.master.write_bytes(b"TEST-VIDEO-ONLY"*300)
        self.script=self.root/"approved_script.txt"
        self.script.write_text("The red ball is red.",encoding="utf-8")
        self.technical=self.root/"technical_qa.json"
        self.owner=self.root/"owner_qa.json"

    def qualify(self):
        return qualify_engine(self.engine_manifest,
              expected_kind="ltx_animate",private_root=self.root,
              system="Darwin",arch="arm64",memory_bytes=48*1024**3)

    def plan_archive(self, archive_id="ep01-archive-v01"):
        plan=self.root/("plan_"+archive_id+".json")
        doc={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "archive_id":archive_id,"private_root":str(self.root),
            "archive_root":str(self.root/"archives"),"items":[
              {"role":role,"path":str(path),"sha256":sha(path)}
              for role,path in (
                 ("episode_master",self.master),
                 ("approved_script",self.script),
                 ("technical_qa",self.technical),
                 ("owner_qa",self.owner),
              )
            ]
        }
        plan.write_text(json.dumps(doc))
        return plan


class CheckpointTests(M8TestBase):
    def test_all_local_checkpoint_hashes_qualified_without_running(self):
        report=self.qualify()
        self.assertEqual(report["status"],"CHECKPOINT_BYTES_VERIFIED_ENGINE_NOT_RUN")
        self.assertFalse(report["model_execution_tested"])
        self.assertFalse(report["network_used"])
        self.assertEqual(report["checkpoints"][0]["sha256"],sha(self.checkpoint))

    def test_reject_wrong_platform_or_low_ram(self):
        with self.assertRaises(EngineQualificationError):
            qualify_engine(self.engine_manifest,expected_kind="ltx_animate",
                private_root=self.root,system="Linux",arch="aarch64",
                memory_bytes=64*1024**3)
        with self.assertRaises(EngineQualificationError):
            qualify_engine(self.engine_manifest,expected_kind="ltx_animate",
                private_root=self.root,system="Darwin",arch="arm64",
                memory_bytes=8*1024**3)

    def test_reject_model_changed_or_download_required(self):
        self.checkpoint.write_bytes(b"tampered checkpoint")
        with self.assertRaises(EngineQualificationError):
            self.qualify()
        self.model_data["checkpoints"][0]["sha256"]=sha(self.checkpoint)
        self.model_data["network_required"]=True
        self.engine_manifest.write_text(json.dumps(self.model_data))
        with self.assertRaises(EngineQualificationError):
            self.qualify()

    def test_model_symlink_disallowed(self):
        link=self.root/"model_link.safetensors"
        link.symlink_to(self.checkpoint)
        self.model_data["checkpoints"][0]["path"]=str(link)
        self.engine_manifest.write_text(json.dumps(self.model_data))
        with self.assertRaises(EngineQualificationError):
            self.qualify()


class ArchiveTests(M8TestBase):
    def setUp(self):
        super().setUp()
        self.technical.write_text('{"technical":"passed"}')
        self.owner.write_text('{"owner":"reviewed"}')

    def test_archive_and_verify_copies_dont_overwrite(self):
        plan=self.plan_archive()
        self.assertEqual(preflight(plan)["status"],"ARCHIVE_PREFLIGHT_READY_NOT_COPIED")
        result=archive(plan)
        self.assertEqual(result["status"],"ARCHIVE_VERIFIED_NOT_PUBLISHED")
        self.assertEqual(result["file_count"],4)
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        self.assertEqual(result["archive_manifest_sha256"],
                         sha(target/"archive_manifest.json"))
        self.assertEqual(verify_archive(target)["status"],"ARCHIVE_VERIFIED_NOT_PUBLISHED")
        with self.assertRaises(ArchiveError):
            archive(plan)
        self.assertEqual(self.master.read_bytes(),b"TEST-VIDEO-ONLY"*300)

    def test_modified_copy_fails_verify_and_doesnt_change_source(self):
        plan=self.plan_archive()
        archive(plan)
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        copy=next(target.glob("*_episode_master.mp4"))
        copy.write_bytes(b"tamper")
        with self.assertRaises(ArchiveError):
            verify_archive(target)
        self.assertEqual(sha(self.master),
                         json.loads(plan.read_text())["items"][0]["sha256"])

    def test_changed_source_and_symlink_blocked(self):
        plan=self.plan_archive()
        self.master.write_bytes(b"changed")
        with self.assertRaises(ArchiveError):
            archive(plan)
        self.master.write_bytes(b"TEST-VIDEO-ONLY"*300)
        link=self.root/"fake_master.mp4"
        link.symlink_to(self.master)
        data=json.loads(plan.read_text())
        data["items"][0]["path"]=str(link)
        plan.write_text(json.dumps(data))
        with self.assertRaises(ArchiveError):
            preflight(plan)


class PrivatePreviewTests(M8TestBase):
    def setUp(self):
        super().setUp()
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","Colors","ar",[
             {"title":"Red","objective":"Teach red"}],activate=True)
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=? WHERE series_id='colors-ar' AND ordinal=1""",
                (sha(self.script),))
        self.render_id=self.series.queue_render(
            "colors-ar",1,"ep01_approved",media_kind="episode_assemble")
        job=self.queue.claim(worker_id="mac",capabilities=["episode_assemble"])
        self.queue.complete(job_id=self.render_id,worker_id="mac",
                            generation=job["generation"],result={
               "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
               "artifact_sha256":sha(self.master),"artifact_type":"mp4",
               "publication_approved":False})
        self.series.reconcile()
        self.quality=QualityLedger(self.queue)
        self.quality.initialize()
        self.technical.write_text(json.dumps({
            "schema_version":1,"status":"TECH_PASS_OWNER_REVIEW_PENDING",
            "media_sha256":sha(self.master),
            "expected_media_sha256":sha(self.master),
            "file_bytes":self.master.stat().st_size,
            "duration_seconds":10.0,
            "checks":{key:True for key in (
              "media_sha256_matches","h264_video","aac_audio",
              "one_video_stream","one_audio_stream","resolution_1280x720",
              "frame_rate_24","sample_rate_48000","duration_bounded",
              "full_decode_success")},
            "subjective_checks_performed":False,"rights_verified":False,
            "publishing_approved":False
        }))
        self.owner.write_text(json.dumps({
            "schema_version":1,"media_sha256":sha(self.master),
            "reviewer_role":"owner",
            "criteria":{name:{
                "decision":"PASS",
                "evidence":"Owner directly inspected this aspect of final episode: "+name
              } for name in CRITERIA},
            "summary":"Owner has watched the full episode, studied pronunciation, "
                      "learning quality, continuity and rights records."
        }))

    def finalize(self):
        self.quality.register_technical("colors-ar",1,self.technical)
        self.quality.submit_owner_review("colors-ar",1,self.owner)
        self.series.approve_episode("colors-ar",1,
                "Owner reviewed entire video and checked evidence for this run")

    def test_private_readiness_stays_blocked_before_owner_approval(self):
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        archive(self.plan_archive())
        with self.assertRaises(PrivateReleaseError):
            check_readiness(self.queue,target,series_id="colors-ar",ordinal=1)

    def test_after_all_gates_one_private_packet_no_upload(self):
        self.finalize()
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        archive(self.plan_archive())
        packet=check_readiness(self.queue,target,series_id="colors-ar",ordinal=1)
        self.assertEqual(packet["status"],"READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED")
        self.assertFalse(packet["upload_performed"])
        self.assertFalse(packet["public_release_authorized"])
        self.assertEqual(packet["video_sha256"],sha(self.master))

    def test_m12_private_gate_rejects_unverified_stage_or_missing_m10(self):
        from kidsstudio.studio_stage_ledger import StageLedger
        from kidsstudio.studio_audio_ledger import AudioEvidenceLedger
        self.finalize()
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        archive(self.plan_archive())
        StageLedger(self.queue).initialize()
        ids={}
        for kind,media_sha,source_voice in (
            ("voice_synthesize","b"*64,None),
            ("ltx_animate","c"*64,"b"*64),
        ):
            job=self.queue.enqueue(
                kind=kind,request_key="synthetic-m12-"+kind,
                payload={"recipe_id":"mock"},max_attempts=1)
            ids[kind]=job["job_id"]
            with self.queue._connection(write=True) as db:
                db.execute("""INSERT INTO studio_episode_stages
                    (series_id,ordinal,stage,state,job_id,script_sha256,
                     source_voice_sha256,artifact_sha256,attempt,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    ("colors-ar",1,kind,"QA_APPROVED",ids[kind],
                     sha(self.script),source_voice,media_sha,1,1.0))
        # An owner QA flag does not substitute for a completed Pi media receipt.
        with self.assertRaises(PrivateReleaseError):
            check_readiness(self.queue,target,series_id="colors-ar",ordinal=1)
        for kind,art_sha,typ,status in (
            ("voice_synthesize","b"*64,"wav","VOICE_RENDERED_PENDING_QA"),
            ("ltx_animate","c"*64,"mp4","A2V_RENDERED_PENDING_QA"),
        ):
            lease=self.queue.claim(worker_id="mac",capabilities=[kind])
            self.queue.complete(job_id=ids[kind],worker_id="mac",
                generation=lease["generation"],result={
                "status":status,"artifact_sha256":art_sha,
                "artifact_type":typ,"publication_approved":False})
        # M10 hasn't been installed: legacy staged episodes can be inspected.
        self.assertEqual(check_readiness(self.queue,target,
            series_id="colors-ar",ordinal=1)["status"],
            "READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED")
        AudioEvidenceLedger(self.queue).initialize()
        with self.assertRaises(PrivateReleaseError):
            check_readiness(self.queue,target,series_id="colors-ar",ordinal=1)
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_audio_checks
                (series_id,ordinal,ltx_job_id,voice_sha256,a2v_sha256,
                 report_sha256,correlation,status,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
                 ("colors-ar",1,ids["ltx_animate"],"b"*64,"c"*64,
                  "d"*64,0.95,
                  "TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING",1.0))
        self.assertFalse(check_readiness(self.queue,target,
            series_id="colors-ar",ordinal=1)["public_release_authorized"])

    def test_wrong_technical_or_owner_evidence_archive_rejected(self):
        self.finalize()
        target=self.root/"archives"/"colors-ar"/"ep001"/"ep01-archive-v01"
        # Change original human report after it was registered: archive is
        # internally valid, but doesn't match approved report SHA256.
        self.owner.write_text('{"rewritten":"unreviewed"}')
        archive(self.plan_archive())
        with self.assertRaises(PrivateReleaseError):
            check_readiness(self.queue,target,series_id="colors-ar",ordinal=1)


if __name__=="__main__":
    unittest.main()
