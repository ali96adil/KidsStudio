"""M13 two-scene synthetic tests: distinct voice/LTX jobs and ordered montage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.scene_catalogue import (
    freeze_scene_catalogue, verify_scene_seal, SceneCatalogueError
)
from kidsstudio.media_worker import MediaRecipes, MediaError
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.series_manager import SeriesManager,SeriesError
from kidsstudio.studio_scenes import SceneLedger,SceneError
from kidsstudio.scene_assembly import (
    inspect_scene_assembly,write_scene_recipe,SceneAssemblyError
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_probe(path,executable):
    return {"width":384,"height":384,"duration":4.0,"audio_streams":1}


class SceneWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.queue=StudioQueue(self.root/"studio.sqlite")
        self.queue.initialize()
        self.series=SeriesManager(self.queue)
        self.series.initialize()
        self.series.create_series("colors-ar","الألوان","ar",
             [{"title":"الأحمر","objective":"التعرف على اللون الأحمر"}],activate=True)
        self.parent=self.root/"episode.txt"
        self.parent.write_text("المشهد الأول: الكرة حمراء. المشهد الثاني: ابحث عن الأحمر.",
                               encoding="utf-8")
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
               source_sha256=? WHERE series_id='colors-ar' AND ordinal=1""",
               (sha(self.parent),))
        self.scene_text=[]
        for i in range(1,3):
            src=self.root/f"scene{i}.txt"
            src.write_text(f"المشهد {i} واللون الأحمر.",encoding="utf-8")
            self.scene_text.append(src)
        self.plan=self.root/"scenes.json"
        self.plan.write_text(json.dumps({
             "schema_version":1,"series_id":"colors-ar",
             "episode_number":1,"episode_script_sha256":sha(self.parent),
             "scenes":[{"scene":i,"script_sha256":sha(self.scene_text[i-1]),
                        "objective":f"تعليم اللون بالمشهد رقم {i}"}
                       for i in (1,2)]
        }),encoding="utf-8")
        self.ledger=SceneLedger(self.queue)
        self.ledger.initialize()
        self.outputs=self.root/"outputs";self.outputs.mkdir()
        self.a2v_paths={}
        for name in ("v06.py","v07.py"):
            (self.root/name).write_text("pass\n")
        self.template=self.root/"assembly_template.json"
        self.template_data={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.root),
            "output_root":str(self.root/"assembled"),
            "script":{"path":str(self.parent),"sha256":sha(self.parent)},
            "voice_rights":"INTERNAL_TEST_ONLY",
            "tools":{"ffmpeg":sys.executable,"ffprobe":sys.executable,
                     "face_python":sys.executable,
                     "face_v06":str(self.root/"v06.py"),
                     "face_v06_sha256":sha(self.root/"v06.py"),
                     "face_v07":str(self.root/"v07.py"),
                     "face_v07_sha256":sha(self.root/"v07.py")},
            "face_cleanup_by_scene":["bunny_v07","none"]
        }
        self.template.write_text(json.dumps(self.template_data))

    def media(self,scene,kind):
        jobid=self.ledger.queue_stage("colors-ar",1,scene,kind,
                                     f"approved_scene_{scene}_{kind}")
        lease=self.queue.claim(worker_id="mac",capabilities=[kind])
        self.assertEqual(lease["job_id"],jobid)
        folder=self.outputs/jobid;folder.mkdir()
        is_voice=kind=="voice_synthesize"
        media=folder/("narration.wav" if is_voice else "a2v.mp4")
        media.write_bytes((f"fake-{kind}-scene-{scene}").encode()*30)
        checksum=sha(media)
        voice=self.voice_hashes[scene] if not is_voice else None
        receipt={
            "schema_version":1,"job_id":jobid,"stage":kind,
            "status":"VOICE_RENDERED_PENDING_QA" if is_voice else
                     "A2V_RENDERED_PENDING_QA",
            "script_sha256":sha(self.scene_text[scene-1]),
            "source_voice_sha256":voice,
            "recipe_sha256":"a"*64,
            "publication_approved":False,
            "artifact_sha256":checksum,
            "artifact_bytes":media.stat().st_size,
            "artifact_type":"wav" if is_voice else "mp4",
            "duration_seconds":4.0
        }
        (folder/"stage_receipt.json").write_text(json.dumps(receipt))
        self.queue.complete(job_id=jobid,worker_id="mac",
                            generation=lease["generation"],result={
           "status":receipt["status"],"artifact_sha256":checksum,
           "artifact_bytes":media.stat().st_size,
           "artifact_type":receipt["artifact_type"],
           "publication_approved":False})
        self.ledger.reconcile()
        if is_voice:
            self.voice_hashes[scene]=checksum
        else:
            self.a2v_paths[scene]=media
        return jobid,checksum

    def audio_report(self,scene,voice_sha,ltx_sha):
        report=self.root/f"audio_{scene}.json"
        report.write_text(json.dumps({
            "schema_version":1,
            "status":"AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED",
            "voice_sha256":voice_sha,"a2v_sha256":ltx_sha,
            "voice_seconds":4.0,"a2v_audio_seconds":4.0,
            "duration_close":True,"envelope_correlation":0.95,
            "estimated_lag_seconds":0.02,"energy_present":True,
            "audio_content_identity_proven":False,
            "speaker_identity_proven":False,"lip_sync_verified":False,
            "owner_audiovisual_review_required":True,
            "publishing_approved":False
        }))
        return report

    def complete_plan(self):
        self.ledger.register_plan(self.plan)
        self.voice_hashes={}
        for scene in (1,2):
            _,voice_sha=self.media(scene,"voice_synthesize")
            self.ledger.approve("colors-ar",1,scene,"voice_synthesize",voice_sha,
                                "Owner listened to scene and approved voice WAV")
            _,ltx_sha=self.media(scene,"ltx_animate")
            self.ledger.register_audio("colors-ar",1,scene,
                                       self.audio_report(scene,voice_sha,ltx_sha))
            self.ledger.approve("colors-ar",1,scene,"ltx_animate",ltx_sha,
                                "Owner watched scene animation and verified lip sync")

    def preview(self):
        return inspect_scene_assembly(
            self.queue,template=self.template,
            series_id="colors-ar",ordinal=1,
            voice_output_root=self.outputs,ltx_output_root=self.outputs,
            video_prober=fake_probe)

    def test_two_scene_script_and_audio_approval_chain(self):
        self.ledger.register_plan(self.plan)
        with self.assertRaises(SceneError):
            self.ledger.queue_stage("colors-ar",1,1,"ltx_animate","ltx_one")
        with self.assertRaises(SeriesError):
            self.series.queue_render("colors-ar",1,"episode_all",
                                     media_kind="episode_assemble")
        self.voice_hashes={}
        _,voice_sha=self.media(1,"voice_synthesize")
        with self.assertRaises(SceneError):
            self.ledger.queue_stage("colors-ar",1,1,"ltx_animate","ltx_one")
        self.ledger.approve("colors-ar",1,1,"voice_synthesize",voice_sha,
                            "Owner listened and reviewed scene one narration")
        _,ltx_sha=self.media(1,"ltx_animate")
        with self.assertRaises(SceneError):
            self.ledger.approve("colors-ar",1,1,"ltx_animate",ltx_sha,
                                "No source continuity was checked yet")
        self.ledger.register_audio("colors-ar",1,1,
            self.audio_report(1,voice_sha,ltx_sha))
        self.ledger.approve("colors-ar",1,1,"ltx_animate",ltx_sha,
                            "Owner visually approved first scene movement")
        with self.assertRaises(SeriesError):
            self.series.queue_render("colors-ar",1,"episode_all",
                                     media_kind="episode_assemble")

    def test_all_two_scenes_to_ordered_private_m4_recipe(self):
        self.complete_plan()
        recipe,evidence=self.preview()
        self.assertEqual(evidence["status"],
                         "ALL_SCENES_VERIFIED_ASSEMBLY_NOT_RENDERED")
        self.assertEqual(evidence["scene_count"],2)
        self.assertEqual([x["video"] for x in recipe["clips"]],
                         [str(self.a2v_paths[1]),str(self.a2v_paths[2])])
        self.assertFalse((self.root/"assembled").exists())
        path=self.root/"recipes"/"episode_01.json"
        final=write_scene_recipe(path,recipe,evidence)
        self.assertEqual(final["status"],"M4_RECIPE_CREATED_OWNER_REVIEW_REQUIRED")
        self.assertFalse(final["rendered"])
        self.assertEqual(json.loads(path.read_text())["clips"][0]["face_cleanup"],
                         "bunny_v07")
        with self.assertRaises(SceneAssemblyError):
            write_scene_recipe(path,recipe,evidence)
        self.series.queue_render("colors-ar",1,"episode_all",
                                  media_kind="episode_assemble",
                                  catalogue_sha256="a"*64)

    def freeze_for_mac_worker(self):
        self.complete_plan()
        recipe,evidence=self.preview()
        path=self.root/"recipes"/"episode_01.json"
        write_scene_recipe(path,recipe,evidence)
        proof=self.root/"intake"/"scene_evidence.json"
        catalog=self.root/"intake"/"frozen_catalogue.json"
        result=freeze_scene_catalogue(
            self.queue,template=self.template,assembly_recipe=path,
            series_id="colors-ar",ordinal=1,
            voice_output_root=self.outputs,ltx_output_root=self.outputs,
            evidence_path=proof,catalog_path=catalog,
            recipe_id="ep01_verified_v1",video_prober=fake_probe)
        return result,path,proof,catalog

    def test_m14_owner_frozen_catalogue_rechecks_all_real_scene_files(self):
        result,recipe,proof,catalog=self.freeze_for_mac_worker()
        self.assertEqual(result["status"],
                         "MULTISCENE_MEDIA_CATALOGUE_FROZEN_NOT_EXECUTED")
        self.assertEqual(result["scene_count"],2)
        self.assertFalse(result["rendered"])
        data=MediaRecipes(catalog)
        selected=data.resolve("episode_assemble","ep01_verified_v1")
        self.assertEqual(selected["sha256"]["episode_recipe"],sha(recipe))
        self.assertEqual(selected["sha256"]["scene_evidence"],sha(proof))
        self.assertFalse((self.root/"assembled").exists())
        with self.assertRaises(SceneCatalogueError):
            freeze_scene_catalogue(
                self.queue,template=self.template,assembly_recipe=recipe,
                series_id="colors-ar",ordinal=1,
                voice_output_root=self.outputs,ltx_output_root=self.outputs,
                evidence_path=proof,catalog_path=catalog,
                recipe_id="ep01_verified_v1",video_prober=fake_probe)

    def test_m16_pi_catalogue_hash_must_match_mac_before_execution(self):
        from kidsstudio.media_worker import RemoteMediaWorker, MediaJournal
        import json as _json

        class LocalPi:
            def __init__(self,queue):
                self.queue=queue
                self.calls=[]
            def call(self,action,payload):
                self.calls.append(action)
                if action=="claim":
                    job=self.queue.claim(worker_id="mac",capabilities=["episode_assemble"])
                    return {"job":dict(job, payload=_json.loads(job["payload"]))
                            if job else None}
                if action=="fail":
                    self.queue.fail(job_id=payload["job_id"],worker_id="mac",
                        generation=payload["generation"],
                        error_code=payload["error_code"],retryable=False)
                    return {"status":"FAILED"}
                if action=="complete-media":
                    self.queue.complete(job_id=payload["job_id"],worker_id="mac",
                        generation=payload["generation"],result={
                            "status":payload["result_status"],
                            "artifact_sha256":payload["artifact_sha256"],
                            "artifact_type":payload["artifact_type"],
                            "publication_approved":False})
                    return {"status":"COMPLETED"}
                return {"ok":True}

        class FakeRender:
            def __init__(self):
                self.calls=0
            def execute(self,kind,recipe_id,job_id):
                self.calls+=1
                return {"result_status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                        "artifact_sha256":"f"*64,"artifact_bytes":123,
                        "artifact_type":"mp4","publication_approved":False}

        _,recipe,proof,catalog=self.freeze_for_mac_worker()
        with self.assertRaises(SeriesError):
            self.series.queue_render("colors-ar",1,"ep01_verified_v1",
                                     media_kind="episode_assemble")
        self.series.queue_render("colors-ar",1,"ep01_verified_v1",
                                 media_kind="episode_assemble",
                                 catalogue_sha256="e"*64)
        fake=FakeRender()
        remote=RemoteMediaWorker(LocalPi(self.queue),MediaRecipes(catalog),
                                 MediaJournal(self.root/"journal.sqlite"),
                                 executor=fake)
        self.assertEqual(remote.run_once()["status"],"CONFIG_REJECTED")
        self.assertEqual(fake.calls,0)

    def test_m16_matching_pi_catalogue_hash_allows_simulated_execution_only(self):
        from kidsstudio.media_worker import RemoteMediaWorker,MediaJournal
        import json as _json
        class MockPi:
            def __init__(self,queue):self.queue=queue
            def call(self,action,payload):
                if action=="claim":
                    job=self.queue.claim(worker_id="mac",capabilities=["episode_assemble"])
                    return {"job":dict(job,payload=_json.loads(job["payload"])) if job else None}
                if action=="complete-media":
                    self.queue.complete(job_id=payload["job_id"],worker_id="mac",
                        generation=payload["generation"],result={
                        "status":payload["result_status"],
                        "artifact_sha256":payload["artifact_sha256"],
                        "artifact_type":payload["artifact_type"],
                        "publication_approved":False})
                    return {"status":"COMPLETED"}
                return {"ok":True}
        class FakeExecutor:
            def __init__(self):self.count=0
            def execute(self,kind,recipe_id,job_id):
                self.count+=1
                return {"result_status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                        "artifact_sha256":"a"*64,"artifact_bytes":100,
                        "artifact_type":"mp4","publication_approved":False}
        _,_,_,catalog=self.freeze_for_mac_worker()
        jobid=self.series.queue_render("colors-ar",1,"ep01_verified_v1",
                          media_kind="episode_assemble",catalogue_sha256=sha(catalog))
        fake=FakeExecutor()
        reply=RemoteMediaWorker(MockPi(self.queue),MediaRecipes(catalog),
               MediaJournal(self.root/"journal.sqlite"),executor=fake).run_once()
        self.assertEqual(reply["status"],"COMPLETED")
        self.assertEqual(fake.count,1)
        self.assertEqual(self.queue.get(jobid)["state"],"COMPLETED")
        self.assertFalse((self.root/"assembled").exists())

    def test_m14_rejects_unsealed_multiscene_worker_catalogue(self):
        self.complete_plan()
        recipe,report=self.preview()
        out=self.root/"recipes"/"unsealed.json"
        write_scene_recipe(out,recipe,report)
        catalog=self.root/"unsealed_catalogue.json"
        catalog.write_text(json.dumps({
            "schema_version":1,
            "recipes":{"ep01_unsealed":{
                "kind":"episode_assemble",
                "output_root":recipe["output_root"],
                "inputs":{"episode_recipe":str(out)},
                "sha256":{"episode_recipe":sha(out)}
            }}
        }))
        with self.assertRaises(MediaError):
            MediaRecipes(catalog).resolve("episode_assemble","ep01_unsealed")
        self.assertFalse((self.root/"assembled").exists())

    def test_m14_refuses_mutated_mac_receipt_after_freeze(self):
        _,recipe,proof,catalog=self.freeze_for_mac_worker()
        with self.queue._connection() as db:
            row=db.execute("""SELECT job_id FROM studio_scene_stages
                WHERE series_id='colors-ar' AND ordinal=1 AND scene=2
                AND stage='ltx_animate'""").fetchone()
        file=self.outputs/row["job_id"]/"stage_receipt.json"
        data=json.loads(file.read_text())
        data["source_voice_sha256"]="f"*64
        file.write_text(json.dumps(data))
        with self.assertRaises(MediaError):
            MediaRecipes(catalog).resolve("episode_assemble","ep01_verified_v1")

    def test_m14_refuses_replaced_second_clip_after_freeze(self):
        _,_,_,catalog=self.freeze_for_mac_worker()
        self.a2v_paths[2].write_bytes(b"SWAPPED_VIDEO")
        with self.assertRaises((MediaError,ValueError)):
            MediaRecipes(catalog).resolve("episode_assemble","ep01_verified_v1")

    def test_reject_swapped_second_scene_and_tampered_stage_receipt(self):
        self.complete_plan()
        self.a2v_paths[2].write_bytes(b"other video")
        with self.assertRaises(Exception):
            self.preview()

    def test_refuse_duplicate_scene_plan_and_reused_script(self):
        self.ledger.register_plan(self.plan)
        with self.assertRaises(SceneError):
            self.ledger.register_plan(self.plan)
        content=json.loads(self.plan.read_text())
        content["scenes"][1]["script_sha256"]=content["scenes"][0]["script_sha256"]
        self.plan.write_text(json.dumps(content))
        with self.assertRaises(SceneError):
            SceneLedger(self.queue).register_plan(self.plan)


if __name__=="__main__":
    unittest.main()
