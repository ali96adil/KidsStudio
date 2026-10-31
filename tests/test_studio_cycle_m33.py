"""M33 SQLite-integrated automation tests; all media/model evidence is synthetic.

Uses the existing M32 two-scene fixture to verify that an M33 cycle
consumes receipts instead of claiming to have rendered children's media.
No Whisper/Ollama/YouTube operation in this suite.
"""
import hashlib
import json
import unittest

from test_studio_orchestrator_m32 import Orchestration32
from kidsstudio.studio_cycle import StudioCycle
from kidsstudio.scene_ai_qa import SceneAIGate
from kidsstudio.studio_scenes import SceneError

class Cycle33(unittest.TestCase):
    def setUp(self):
        self.fixture=Orchestration32("test_plan_cannot_advertise_public_permission")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.h=self.fixture
        self.h.coord.pin(self.h.plan)
        self.cycle=StudioCycle(self.h.queue,self.h.plan)

    def next_job(self,action):
        result=self.cycle.run_bounded(execute=True)
        self.assertEqual(result["status"],"M33_BOUNDED_CYCLE_STOPPED")
        last=result["operations"][-1]
        self.assertEqual(last["status"],"M33_ONE_PRIVATE_JOB_QUEUED")
        self.assertEqual(last["action"],action)
        self.assertFalse(last["public_release_authorized"])
        return last["job_id"]

    def completed(self,job,kind):
        leased=self.h.queue.claim(worker_id="mac-m33-test",capabilities=[kind])
        self.assertEqual(leased["job_id"],job)
        checksum=hashlib.sha256(job.encode("ascii")).hexdigest()
        self.h.queue.complete(job_id=job,worker_id="mac-m33-test",
            generation=leased["generation"],result={
                "status":("VOICE_RENDERED_PENDING_QA" if kind=="voice_synthesize"
                    else "A2V_RENDERED_PENDING_QA"),
                "artifact_sha256":checksum,
                "artifact_type":"wav" if kind=="voice_synthesize" else "mp4",
                "artifact_bytes":300,"publication_approved":False})
        updated=self.cycle.step(execute=True)
        self.assertEqual(updated["status"],"M33_CURRENT_SCENE_RECEIPT_RECONCILED")
        return checksum

    def agent_proof(self,scene,stage,job,sha):
        SceneAIGate(self.h.queue).initialize()
        technical="e"*64 if stage=="voice_synthesize" else "d"*64
        with self.h.queue._connection(write=True) as db:
            if stage=="voice_synthesize":
                db.execute("""INSERT INTO studio_scene_voice_checks VALUES
                    (?,?,?,?,?,?,?,?)""",("colors-ar",1,scene,job,sha,
                    technical,"TECH_PASS_OWNER_LISTENING_PENDING",
                    self.h.queue.clock()))
            else:
                voice=db.execute("""SELECT artifact_sha256 FROM
                    studio_scene_stages WHERE series_id='colors-ar'
                    AND ordinal=1 AND scene=? AND stage='voice_synthesize'""",
                    (scene,)).fetchone()
                db.execute("""INSERT INTO studio_scene_audio_checks VALUES
                    (?,?,?,?,?,?,?,?)""",("colors-ar",1,scene,job,technical,
                    voice["artifact_sha256"],sha,
                    "TECH_COMPATIBLE_HUMAN_QA_REQUIRED"))
            db.execute("""INSERT INTO studio_scene_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,scene,stage,job,sha,
                 self.h.plan_data["scenes"][scene-1]["script_sha256"],
                 "a"*64,"b"*64,"c"*64,technical,
                 "model_alpha","model_beta","AI_SCENE_READY_PRIVATE_ONLY",
                 0.0 if stage=="voice_synthesize" else None,
                 self.h.queue.clock()))
        accepted=self.cycle.step(execute=True)
        self.assertEqual(accepted["status"],"M33_EXISTING_AI_SCENE_QA_CONSUMED")
        self.assertTrue(accepted["owner_post_private_video_review_required"])
        self.assertFalse(accepted["public_release_authorized"])

    def test_two_scene_cycle_to_external_final_review(self):
        read=self.cycle.run_bounded(execute=False)
        self.assertEqual(read["status"],"M33_OBSERVATION_ONLY_NOT_DEVICE_QUALIFIED")
        self.assertEqual(self.h.queue.status()["counts"]["QUEUED"],0)
        for scene in (1,2):
            job=self.next_job("FIRST_AI_VOICE" if scene==1 else "NEXT_VOICE")
            voice=self.completed(job,"voice_synthesize")
            self.assertEqual(self.cycle.step(execute=True)["status"],
                             "M33_WAIT_FOR_WORKER_OR_REVIEW")
            self.agent_proof(scene,"voice_synthesize",job,voice)
            movie_job=self.next_job("NEXT_LTX")
            movie=self.completed(movie_job,"ltx_animate")
            self.agent_proof(scene,"ltx_animate",movie_job,movie)
        final=self.next_job("ASSEMBLE_FINAL_EPISODE")
        self.assertEqual(self.h.queue.get(final)["kind"],"episode_assemble")
        lease=self.h.queue.claim(worker_id="mac-ci",
            capabilities=["episode_assemble"])
        self.assertEqual(lease["job_id"],final)
        self.h.queue.complete(job_id=final,worker_id="mac-ci",
            generation=lease["generation"],result={
                "status":"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                "artifact_type":"mp4","artifact_sha256":"f"*64,
                "artifact_bytes":10000,"publication_approved":False})
        self.assertEqual(self.cycle.step(execute=True)["status"],
                         "M33_FINAL_MASTER_RECEIPT_RECONCILED")
        waiting=self.cycle.step(execute=True)
        self.assertEqual(waiting["status"],"M33_WAIT_EXTERNAL_QA")
        with self.h.queue._connection() as db:
            ep=db.execute("""SELECT state FROM studio_episodes WHERE
                series_id='colors-ar' AND ordinal=1""").fetchone()
        self.assertEqual(ep["state"],"RENDERED_QA_PENDING")
        self.assertFalse(self.cycle.status()["mac_pi_hardware_test_ready"])

    def test_forged_or_stale_ai_qa_never_progresses(self):
        job=self.next_job("FIRST_AI_VOICE")
        sha=self.completed(job,"voice_synthesize")
        # Initialize ledger before asserting a missing tech digest.
        SceneAIGate(self.h.queue).initialize()
        with self.h.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_scene_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,1,"voice_synthesize",job,sha,
                 self.h.plan_data["scenes"][0]["script_sha256"],
                 "a"*64,"b"*64,"c"*64,"e"*64,
                 "model_alpha","model_beta","AI_SCENE_READY_PRIVATE_ONLY",
                 0.0,self.h.queue.clock()))
        with self.assertRaises(SceneError):
            self.cycle.step(execute=True)
        self.assertEqual(self.h.scenes.snapshot("colors-ar",1)[
            "scenes"][0]["stages"]["voice_synthesize"]["state"],"PENDING_QA")

    def test_paused_and_mutated_plan_fail_closed(self):
        self.h.queue.set_paused(True)
        blocked=self.cycle.step(execute=True)
        self.assertEqual(blocked["status"],"M33_BLOCKED_NO_ACTION")
        self.assertEqual(self.h.queue.status()["counts"]["QUEUED"],0)
        self.h.queue.set_paused(False)
        raw=self.h.plan.read_text()
        self.h.plan.write_text(raw.replace("voice_1","unapproved_change"))
        blocked=self.cycle.step(execute=True)
        self.assertEqual(blocked["status"],"M33_BLOCKED_NO_ACTION")
        self.assertEqual(self.h.queue.status()["counts"]["QUEUED"],0)

if __name__=="__main__":
    unittest.main()
