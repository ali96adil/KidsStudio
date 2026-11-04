"""M33 Pi->Mac first WAV pilot authorization for CURRENT M30 AI scripts.

All authors/reviewers, scripts and SHA in this suite are synthetic. The TLS
case uses a real local HTTPS server and real RemoteClient transport, but NO
model runs or uploads or actual audio is produced.
"""
from __future__ import annotations

import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest

from kidsstudio.coordinator_api import Coordinator,TransportError,create_handler
from kidsstudio.live_pilot_gate import observe_live_scene_plan,LivePilotError
from kidsstudio.remote_worker import RemoteClient
from kidsstudio.series_manager import SeriesManager
from kidsstudio.studio_queue import StudioQueue
from kidsstudio.studio_scenes import SceneLedger
from kidsstudio.script_ai_quality import ScriptAIQuality
from kidsstudio.script_gate import current_script_mode


def digest(s:str)->str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class AIPilotProof33(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m33-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.q=StudioQueue(self.root/"test.sqlite")
        self.q.initialize()
        self.registry=SeriesManager(self.q);self.registry.initialize()
        self.registry.create_series("colors-ar","Colors","ar",
            [{"title":"Red and blue","objective":"Identify red and blue toys"}],
            activate=True)
        self.scene=SceneLedger(self.q);self.scene.initialize()
        private=self.root/"private"
        private.mkdir()
        ScriptAIQuality(self.q,None,private).initialize()
        self.source=digest("original private script for colors")
        self.draft_job_id="a"*32
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=?,draft_job_id=?,
                owner_review_note=? WHERE series_id='colors-ar' AND ordinal=1""",
                (self.source,self.draft_job_id,
                 "M30_TWO_INDEPENDENT_AI_INTERNAL_PRIVATE_ONLY"))
            db.execute("""INSERT INTO studio_script_ai_reviews VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("colors-ar",1,1,self.draft_job_id,self.source,
                 "model_alpha","model_beta","1"*64,"2"*64,
                 "3"*64,"AI_SCRIPT_PRIVATE_READY",self.q.clock()))
            SeriesManager._audit(db,"colors-ar",1,
                 "SCRIPT_APPROVED_BY_TWO_INDEPENDENT_AI_PRIVATE_ONLY")
        self.goals=["Show the red ball","Show the blue balloon"]
        self.scripts=[digest("scene 1 red"),digest("scene 2 blue")]
        manifest=self.root/"scenes.json"
        manifest.write_text(json.dumps({
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "episode_script_sha256":self.source,
            "scenes":[
                {"scene":i,"script_sha256":self.scripts[i-1],
                 "objective":self.goals[i-1]} for i in (1,2)]
        }))
        self.plan=self.scene.register_plan(manifest)
        self.worker_id="mac-voice-ci"
        self.token="only-ci-test-secret-"+("k"*40)
        self.coordinator=Coordinator(self.q,self.root/"vault",
            {self.worker_id:(self.token,{"voice_synthesize"})})

    def request(self):
        return {
            "nonce":"c"*32,"series_id":"colors-ar","episode_number":1,
            "episode_revision":1,
            "scene_plan_sha256":self.plan["plan_sha256"],
            "parent_script_sha256":self.source,
            "scenes":[
                {"scene":i,"script_sha256":self.scripts[i-1],
                 "objective_sha256":digest(self.goals[i-1])}
                for i in (1,2)]
        }

    def queue_voice(self):
        return self.scene.queue_first_voice_ai(
            "colors-ar",1,"approved_mac_voice_model",
            self.plan["plan_sha256"])

    def claim(self):
        job=self.coordinator.dispatch("claim",{},self.worker_id,
            frozenset({"voice_synthesize"}))["job"]
        self.assertIsNotNone(job)
        self.assertEqual(job["kind"],"voice_synthesize")
        return job

    def proof(self,job):
        return {
            "job_id":job["job_id"],"generation":job["generation"],
            "pilot_plan_sha256":self.plan["plan_sha256"],
            "pilot_scene":1,"script_sha256":self.scripts[0],
            "recipe_id":"approved_mac_voice_model"
        }

    def verify(self,job):
        return self.coordinator.dispatch("pilot-voice-lease-check",
            self.proof(job),self.worker_id,frozenset({"voice_synthesize"}))

    def test_legacy_owner_note_is_not_fabricated(self):
        with self.q._connection() as db:
            self.assertEqual(current_script_mode(db,"colors-ar",1),
                             "AI_PRIVATE_SCRIPT")
            self.assertIsNone(db.execute("""SELECT 1 FROM studio_series_audit
                WHERE action='SCRIPT_APPROVED_BY_OWNER'""").fetchone())
        preview=observe_live_scene_plan(self.q,self.request())
        self.assertFalse(preview["model_execution_authorized"])
        self.assertFalse(preview["jobs_claimed"])
        job_id=self.queue_voice()
        job=self.claim()
        self.assertEqual(job["job_id"],job_id)
        proof=self.verify(job)
        self.assertEqual(proof["status"],
                         "PINNED_SINGLE_VOICE_LEASE_CURRENT_NOT_EXECUTED")
        self.assertEqual(proof["recipe_id"],"approved_mac_voice_model")
        self.assertFalse(proof["model_execution_authorized"])
        self.assertFalse(proof["publication_approved"])
        self.assertIsInstance(proof["server_time"],(int,float))
        self.assertEqual(self.q.get(job_id)["state"],"LEASED")

    def test_unauthorized_stale_or_forged_ai_proof_rejected(self):
        self.queue_voice()
        job=self.claim()
        with self.assertRaises(TransportError):
            self.coordinator.dispatch("pilot-voice-lease-check",
                self.proof(job),"other-worker",frozenset({"voice_synthesize"}))
        wrong=self.proof(job)
        wrong["pilot_plan_sha256"]="f"*64
        with self.assertRaises(TransportError):
            self.coordinator.dispatch("pilot-voice-lease-check",
                wrong,self.worker_id,frozenset({"voice_synthesize"}))
        with self.q._connection(write=True) as db:
            db.execute("""DELETE FROM studio_script_ai_reviews
                WHERE series_id='colors-ar'""")
        with self.assertRaises(TransportError):
            self.verify(job)
        with self.q._connection() as db:
            self.assertIsNone(current_script_mode(db,"colors-ar",1))

    def test_pause_and_stale_revision_block_at_lease(self):
        self.queue_voice()
        job=self.claim()
        self.q.set_paused(True)
        with self.assertRaises(TransportError):
            self.verify(job)
        self.q.set_paused(False)
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET revision=revision+1
                WHERE series_id='colors-ar' AND ordinal=1""")
        with self.assertRaises(TransportError):
            self.verify(job)

    def test_changed_source_blocks_m21_status_without_claim(self):
        with self.q._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET source_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",("f"*64,))
        with self.assertRaises(LivePilotError):
            observe_live_scene_plan(self.q,self.request())
        self.assertEqual(self.q.status()["counts"]["LEASED"],0)

    @unittest.skipUnless(shutil.which("openssl"),"ephemeral TLS requires openssl")
    def test_real_local_https_mac_client_observes_ai_approved_pi_lease(self):
        cert=self.root/"local.crt";key=self.root/"local.key"
        subprocess.run(["openssl","req","-x509","-newkey","rsa:2048",
            "-nodes","-sha256","-days","1","-keyout",str(key),
            "-out",str(cert),"-subj","/CN=localhost",
            "-addext","subjectAltName=DNS:localhost"],
            capture_output=True,check=True,timeout=25)
        server=ThreadingHTTPServer(("127.0.0.1",0),
                                   create_handler(self.coordinator))
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert),str(key))
        server.socket=ctx.wrap_socket(server.socket,server_side=True)
        worker_thread=threading.Thread(target=server.serve_forever,daemon=True)
        worker_thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client=RemoteClient("https://localhost:"+str(server.server_port),
            worker_id=self.worker_id,token=self.token,ca_file=str(cert))
        self.queue_voice()
        job=client.call("claim",{})["job"]
        check=client.call("pilot-voice-lease-check",self.proof(job))
        self.assertEqual(check["status"],
                         "PINNED_SINGLE_VOICE_LEASE_CURRENT_NOT_EXECUTED")
        self.assertFalse(check["publication_approved"])
        self.assertFalse(check["model_execution_authorized"])


if __name__=="__main__":
    unittest.main()
