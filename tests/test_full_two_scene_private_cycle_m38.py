"""M38 integrated two-scene PRIVATE production acceptance.

ACTUAL: FFmpeg AAC sound-bearing MP4, original WAV, per-scene SHA jobs,
PCM continuity, frame capture, assembly, final full decode and Pi SQLite.
MOCKED: Whisper, two local WAV reviewers, two AV reviewers, and final M27
pedagogy/safety reviewers. All media are synthetic; no qualified models,
owner approval, YouTube OAuth, publication, Mac or Raspberry Pi run.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from kidsstudio.agent_final_qa import AgentFinalQA, ROLE_CRITERIA
from kidsstudio.audio_continuity import compare_voice_to_a2v
from kidsstudio.audio_review_import import import_voice_review
from kidsstudio.episode_assembly import EpisodeAssembler, EpisodeAssemblyError
from kidsstudio.episode_quality import inspect_video, save_report
from kidsstudio.real_media_evidence import capture_frames, digest
from kidsstudio.studio_cycle import StudioCycle
from kidsstudio.studio_quality_ledger import QualityLedger
from kidsstudio.synchronized_av_import import import_synchronized, AVImportError
from test_studio_orchestrator_m32 import Orchestration32
from test_synchronized_av_m37 import SynchronizedAV37
from test_local_audio_review_m34 import executable


class FullTwoScenePrivateCycle38(unittest.TestCase):
    def setUp(self):
        # Execute fixture setup only. Don't run its test methods as
        # implicit evidence that actual model inference occurred.
        av=SynchronizedAV37(
            "test_actual_soundtrack_real_pcm_and_frames_bound_to_two_mock_AV_models")
        av.setUp()
        self.addCleanup(av.doCleanups)
        self.av=av
        h=Orchestration32("test_plan_cannot_advertise_public_permission")
        h.setUp()
        self.addCleanup(h.doCleanups)
        self.h=h
        h.coord.pin(h.plan)
        self.cycle=StudioCycle(h.queue,h.plan)
        self.media=h.root/"m38_private"
        self.media.mkdir()
        self.clip1=self.media/"01_red.mp4"
        shutil.copyfile(av.mp4,self.clip1)
        self.clip2=self.media/"02_blue.mp4"
        subprocess.run([av.ffmpeg,"-v","error","-nostdin","-n",
            "-i",str(av.mp4),"-vf","hue=h=70",
            "-c:v","libx264","-preset","ultrafast",
            "-c:a","copy",str(self.clip2)],
            check=True,timeout=60,capture_output=True)
        self.assertNotEqual(digest(self.clip1),digest(self.clip2))
        self.clips=(self.clip1,self.clip2)
        self.rights=[]
        self.m10=[]
        for index,clip in enumerate(self.clips,1):
            m10=compare_voice_to_a2v(
                av.wav,clip,voice_sha256=av.wav_sha,a2v_sha256=digest(clip),
                ffmpeg=av.ffmpeg)
            self.assertEqual(m10["status"],
                "AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED")
            record=self.media/f"scene{index}_m10.json"
            record.write_text(json.dumps(m10))
            self.m10.append(record)
            source=json.loads(av.rights.read_text())
            source["artifact_sha256"]=digest(clip)
            proof=self.media/f"scene{index}_rights.json"
            proof.write_text(json.dumps(source))
            self.rights.append(proof)
        v06=self.media/"not_used_face_v06.py"
        v07=self.media/"not_used_face_v07.py"
        v06.write_text("# not used in test\n")
        v07.write_text("# not used in test\n")
        self.recipe=self.media/"assembly.json"
        self.recipe.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(h.root),
            "output_root":str(h.root/"assembled"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(h.parent),"sha256":digest(h.parent)},
            "tools":{
                "ffmpeg":av.ffmpeg,"ffprobe":av.ffprobe,
                "face_python":sys.executable,
                "face_v06":str(v06),"face_v06_sha256":digest(v06),
                "face_v07":str(v07),"face_v07_sha256":digest(v07)},
            "clips":[{"video":str(clip),"sha256":digest(clip),
                      "face_cleanup":"none"} for clip in self.clips]
        }))
        self.actions=[]

    def queue_stage(self,action):
        result=self.cycle.step(execute=True)
        self.assertEqual(result["status"],"M33_ONE_PRIVATE_JOB_QUEUED")
        self.assertEqual(result["action"],action)
        self.assertFalse(result["public_release_authorized"])
        self.actions.append(action)
        return result["job_id"]

    def complete_scene_job(self,job,kind,path):
        lease=self.h.queue.claim(worker_id="mock-m38-mac",capabilities=[kind])
        self.assertEqual(lease["job_id"],job)
        self.h.queue.complete(job_id=job,worker_id="mock-m38-mac",
            generation=lease["generation"],result={
                "status":("VOICE_RENDERED_PENDING_QA" if kind=="voice_synthesize"
                          else "A2V_RENDERED_PENDING_QA"),
                "artifact_type":"wav" if kind=="voice_synthesize" else "mp4",
                "artifact_sha256":digest(path),
                "artifact_bytes":path.stat().st_size,
                "publication_approved":False})
        self.assertEqual(self.cycle.step(execute=True)["status"],
                         "M33_CURRENT_SCENE_RECEIPT_RECONCILED")

    def accept_voice(self,index,job):
        source=self.h.scripts[index-1]
        # Real Whisper inference is NOT executed. This mock writes back
        # the expected input text; a real model might disagree.
        mock_whisper=executable(self.media/f"whisper_m38_{index}",
            "import sys\nfrom pathlib import Path\na=sys.argv\n"
            "Path(a[a.index('-of')+1]+'.txt').write_text("+
            repr(source.read_text(encoding="utf-8"))+",encoding='utf-8')\n")
        report_dir=self.media/f"scene{index}_voice_model_evidence"
        self.av.audio.run_review(scene=index,job_id=job,
            script=source,script_sha=digest(source),
            whisper_binary=str(mock_whisper),out_dir=report_dir,
            wav=self.av.wav,wav_sha=self.av.wav_sha)
        result=import_voice_review(queue=self.h.queue,series_id="colors-ar",
            episode=1,scene=index,report_dir=report_dir,
            rights_file=self.av.audio.rights,
            runner_key=self.av.audio.key,execute=True)
        self.assertEqual(result["status"],
                         "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY")
        self.assertFalse(result["public_release_authorized"])

    def accept_ltx(self,index,job):
        source=self.h.scripts[index-1]
        report_dir=self.media/f"scene{index}_synchronized_av_evidence"
        self.av.review(scene=index,job_id=job,
            script=source,script_sha=digest(source),
            mp4=self.clips[index-1],mp4_sha=digest(self.clips[index-1]),
            m10_report=self.m10[index-1],rights_file=self.rights[index-1],
            out_dir=report_dir)
        result=import_synchronized(queue=self.h.queue,
            series_id="colors-ar",episode=1,scene=index,
            report_dir=report_dir,m10_report=self.m10[index-1],
            rights_file=self.rights[index-1],
            runner_key=self.av.key,execute=True)
        self.assertEqual(result["status"],
                         "M37_AI_LTX_APPROVED_INTERNAL_PRIVATE_ONLY")
        self.assertFalse(result["public_release_authorized"])

    def synthetic_final_model_receipts(self,final_job,master,tech,frames):
        # This tests only the final M27 **schema and Pi transition**;
        # the two model judgments are fabricated and are not qualified.
        observed=self.media/"m38_final_evidence.json"
        observed.write_text(json.dumps({
            "schema_version":1,"media_sha256":digest(master),
            "script_sha256":digest(self.h.parent),
            "transcript_sha256":digest(self.h.parent),
            "frames_manifest_sha256":digest(
                Path(frames["frames_manifest_file"])),
            "audio_analysis_sha256":digest(tech),
            "sampling_complete":True,
            "subjective_quality_verified":False,
            "publishing_approved":False}))
        catalogue=self.media/"m38_rights_catalogue.json"
        catalogue.write_text(json.dumps({
            "schema_version":1,"media_sha256":digest(master),
            "assets":[{"asset_sha256":digest(path),
                "provenance_kind":"original_created",
                "proof_sha256":digest(self.av.proof),
                "use_scope":"commercial_youtube_kids",
                "rights_status":"DOCUMENTED_NOT_LEGALLY_ADJUDICATED"}
                for path in (*self.clips,self.av.wav)],
            "all_assets_accounted_for":True,
            "publishing_approved":False}))
        review=self.media/"m38_fake_final_model_review.json"
        review.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar",
            "episode_number":1,"render_job_id":final_job,
            "media_sha256":digest(master),
            "script_sha256":digest(self.h.parent),
            "observed_evidence_sha256":digest(observed),
            "rights_catalogue_sha256":digest(catalogue),
            "reviewers":[{
                "role":role,"provider_id":"mock_m38_"+str(index),
                "model_id":"synthetic-m38-no-inference-"+str(index),
                "evidence_sha256":digest(observed),
                "criteria":{key:{
                    "decision":"PASS",
                    "evidence":"SYNTHETIC fixture only; no actual educational, "
                        "copyright or audiovisual model review took place: "+key}
                    for key in sorted(criteria)},
                "summary":"Synthetic CI assertions and schema validation only, "
                    "not a real independent AI full-episode assessment.",
                "release_approved":False}
                for index,(role,criteria) in enumerate(ROLE_CRITERIA.items())],
            "publishing_approved":False}))
        return review,observed,catalogue

    def test_real_two_scene_media_through_private_ai_and_final_qa_no_upload(self):
        # Nothing is queued from a read-only call or while paused.
        self.assertEqual(self.cycle.step()["status"],
                         "M33_OBSERVATION_ONLY_NOT_DEVICE_QUALIFIED")
        self.h.queue.set_paused(True)
        self.assertEqual(self.cycle.step(execute=True)["status"],
                         "M33_BLOCKED_NO_ACTION")
        self.h.queue.set_paused(False)
        for index in (1,2):
            voice=self.queue_stage(
                "FIRST_AI_VOICE" if index==1 else "NEXT_VOICE")
            self.complete_scene_job(voice,"voice_synthesize",self.av.wav)
            self.assertEqual(self.cycle.step(execute=True)["status"],
                             "M33_WAIT_FOR_WORKER_OR_REVIEW")
            self.accept_voice(index,voice)
            ltx=self.queue_stage("NEXT_LTX")
            self.complete_scene_job(ltx,"ltx_animate",self.clips[index-1])
            if index==2:
                # Replay of scene one's correctly signed model evidence
                # cannot approve the second scene or consume its M10.
                with self.assertRaises(AVImportError):
                    import_synchronized(queue=self.h.queue,
                        series_id="colors-ar",episode=1,scene=2,
                        report_dir=self.media/"scene1_synchronized_av_evidence",
                        m10_report=self.m10[1],rights_file=self.rights[1],
                        runner_key=self.av.key,execute=True)
                with self.h.queue._connection() as db:
                    self.assertFalse(db.execute("""SELECT 1 FROM
                        studio_scene_audio_checks WHERE
                        series_id='colors-ar' AND ordinal=1
                        AND scene=2""").fetchone())
            self.accept_ltx(index,ltx)
        state=self.h.scenes.snapshot("colors-ar",1)
        self.assertTrue(all(
            s["stages"][stage]["state"]=="QA_APPROVED"
            for s in state["scenes"]
            for stage in ("voice_synthesize","ltx_animate")))
        self.assertEqual(self.h.coord.status(self.h.plan)["next_action"],
                         "ASSEMBLE_FINAL_EPISODE")
        final_job=self.queue_stage("ASSEMBLE_FINAL_EPISODE")
        # The actual assembly MUST fail if an approved clip changes bytes.
        saved=self.clip2.read_bytes()
        self.clip2.write_bytes(saved+b"TAMPERED")
        with self.assertRaises(EpisodeAssemblyError):
            EpisodeAssembler(self.recipe).preflight()
        self.assertFalse((self.h.root/"assembled").exists())
        self.clip2.write_bytes(saved)
        engine=EpisodeAssembler(self.recipe)
        self.assertEqual(engine.preflight()["status"],
                         "READY_FOR_LOCAL_ASSEMBLY")
        output=engine.execute(run_id="m38-two-real-media-scenes")
        self.assertEqual(output["status"],"RENDERED_PENDING_HUMAN_AV_QA")
        master=Path(output["final_media_path"])
        self.assertEqual(output["clips_built"],2)
        self.assertEqual(digest(master),output["final_media_sha256"])
        self.assertEqual(len(list(master.parent.glob("*_normalized.mp4"))),2)
        self.assertEqual((digest(self.clip1),digest(self.clip2)),
                         tuple(x["sha256"] for x in
                               json.loads(self.recipe.read_text())["clips"]))
        lease=self.h.queue.claim(worker_id="m38-actual-media-assembly",
            capabilities=["episode_assemble"])
        self.assertEqual(lease["job_id"],final_job)
        self.h.queue.complete(job_id=final_job,
            worker_id="m38-actual-media-assembly",
            generation=lease["generation"],result={
                "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                "artifact_type":"mp4","artifact_sha256":digest(master),
                "artifact_bytes":master.stat().st_size,
                "publication_approved":False})
        self.assertEqual(self.cycle.step(execute=True)["status"],
                         "M33_FINAL_MASTER_RECEIPT_RECONCILED")
        qa=inspect_video(master,digest(master),
            ffprobe=self.av.ffprobe,ffmpeg=self.av.ffmpeg)
        self.assertEqual(qa["status"],"TECH_PASS_OWNER_REVIEW_PENDING",
                         msg=json.dumps(qa,ensure_ascii=False))
        self.assertTrue(all(qa["checks"].values()))
        self.assertFalse(qa["subjective_checks_performed"])
        report=self.media/"final_m7_report.json"
        save_report(qa,report)
        ledger=QualityLedger(self.h.queue)
        ledger.initialize()
        ledger.register_technical("colors-ar",1,report)
        self.assertEqual(self.cycle.step(execute=True)["status"],
                         "M33_WAIT_EXTERNAL_QA")
        self.assertEqual(self.h.queue.status()["counts"]["QUEUED"],0)
        frames=capture_frames(mp4=master,expected_mp4_sha=digest(master),
            ffprobe_binary=self.av.ffprobe,ffmpeg_binary=self.av.ffmpeg,
            out_dir=self.media/"final_frames",frames=3)
        review,evidence,rights=self.synthetic_final_model_receipts(
            final_job,master,report,frames)
        final_ai=AgentFinalQA(self.h.queue)
        final_ai.initialize()
        ready=final_ai.register("colors-ar",1,
            review_bundle=review,observed_media_evidence=evidence,
            rights_catalogue=rights)
        self.assertEqual(ready["status"],"AI_INTERNAL_READY_PRIVATE_ONLY")
        completed=self.cycle.step(execute=True)
        self.assertEqual(completed["status"],
                         "M33_INTERNAL_FINAL_READY_PRIVATE_ONLY")
        with self.h.queue._connection() as db:
            state=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id='colors-ar' AND ordinal=1""").fetchone()
            self.assertEqual(state["state"],"EPISODE_APPROVED")
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_scene_ai_reviews""").fetchone()[0],4)
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM
                studio_scene_repair_attempts""").fetchone()[0]
                if db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_scene_repair_attempts'""").fetchone() else 0,0)
        self.assertFalse(completed["public_release_authorized"])
        self.assertFalse(self.cycle.status()["private_upload_permitted_by_this_tool"])
        self.assertEqual(self.actions,[
            "FIRST_AI_VOICE","NEXT_LTX","NEXT_VOICE","NEXT_LTX",
            "ASSEMBLE_FINAL_EPISODE"])
        self.assertEqual(len(list(self.media.glob("*_model_evidence"))),2)


if __name__=="__main__":
    unittest.main()
