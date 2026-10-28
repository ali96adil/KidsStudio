"""M11 static handoff tests: source image import and exact cross-recipe pins."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.handoff_review import inspect_handoff, HandoffError
from kidsstudio.private_asset_intake import (
    import_bunny,preview_import,verify_import,IntakeError
)


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.root=self.base/"studio";self.root.mkdir()
        self.external=self.base/"ComfyUI-Shared";self.external.mkdir()
        self.original=self.external/"Bunny_reference.png"
        self.original.write_bytes(b"\x89PNG\r\n\x1a\n"+"OWNER_BUNNY_REFERENCE".encode())
        self.assets={}
        for role in ("approved_script","voice_wrapper","ltx_wrapper",
                     "face_v06","face_v07"):
            f=self.root/(role+".py" if "wrapper" in role else role+".txt")
            f.write_text("Owner approved "+role)
            self.assets[role]=f
        self.assets["bunny_reference"]=self.original
        self.wav=self.root/"approved_voice.wav";self.wav.write_bytes(b"approved voice" * 16)
        self.python=Path(sys.executable).resolve()
        self.ffmpeg=self.root/"ffmpeg"
        self.ffprobe=self.root/"ffprobe"
        for tool in (self.ffmpeg,self.ffprobe):
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o700)
        self.engine={}
        for kind,name in (("voice_synthesize","chatterbox_multilingual_mlx"),
                          ("ltx_animate","ltx_2_3_mlx")):
            checkpoint=self.root/(kind+"_weights.bin")
            checkpoint.write_bytes(b"synthetic weights for "+kind.encode())
            m=self.root/(kind+"_engine.json")
            m.write_text(json.dumps({
                "schema_version":1,"kind":kind,"engine":name,
                "platform":"Darwin","arch":"arm64","minimum_memory_gib":32,
                "network_required":False,
                "checkpoints":[{"role":"model","path":str(checkpoint),
                                "sha256":sha(checkpoint)}]
            }))
            self.engine[kind]=m
        self.contract_file=self.root/"mac_contract.json"
        self.contract={
            "schema_version":1,
            "private_roots":[str(self.root),str(self.external)],
            "assets":[{"role":role,"path":str(f),"sha256":sha(f)}
                      for role,f in self.assets.items()],
            "tools":[{"role":role,
                      "path":str(self.ffmpeg if role=="ffmpeg" else
                                 self.ffprobe if role=="ffprobe" else self.python),
                      "sha256":sha(self.ffmpeg if role=="ffmpeg" else
                                   self.ffprobe if role=="ffprobe" else self.python)}
                     for role in ("voice_python","ltx_python","ffprobe","ffmpeg")],
            "engine_manifests":[{"kind":k,"path":str(f),"sha256":sha(f)}
                                for k,f in self.engine.items()],
            "minimum_free_gib":20
        }
        self.voice_file=self.root/"voice_stage.json"
        self.ltx_file=self.root/"ltx_stage.json"
        self.voice_recipe=self._recipe("voice_synthesize",self.assets["approved_script"])
        self._write(self.voice_file,self.voice_recipe)
        self._write(self.contract_file,self.contract)

    def _write(self,file,obj):
        file.write_text(json.dumps(obj,ensure_ascii=False))

    def _recipe(self,kind,reference):
        approved=self.assets["approved_script"]
        runner=self.assets["voice_wrapper" if kind=="voice_synthesize" else "ltx_wrapper"]
        inputs=(
            {"script":{"path":str(approved),"sha256":sha(approved)}}
            if kind=="voice_synthesize" else
            {"voice_wav":{"path":str(self.wav),"sha256":sha(self.wav)},
             "reference_image":{"path":str(reference),"sha256":sha(reference)}}
        )
        argv=(
          ["--script","{script}","--engine","{engine_manifest}","--output","{output}"]
          if kind=="voice_synthesize" else
          ["--script","{script}","--audio","{voice_wav}","--reference",
           "{reference_image}","--engine","{engine_manifest}","--output","{output}"]
        )
        manifest=self.engine[kind]
        return {
          "schema_version":1,"kind":kind,"private_root":str(self.root),
          "output_root":str(self.root/"output"),
          "script":{"path":str(approved),"sha256":sha(approved)},
          "inputs":inputs,
          "runner":{"python":str(self.python),"python_sha256":sha(self.python),
                    "entrypoint":str(runner),"entrypoint_sha256":sha(runner),
                    "args":argv},
          "engine_manifest":{"path":str(manifest),"sha256":sha(manifest)},
          "voice_rights":"INTERNAL_TEST_ONLY",
          "limits":{"timeout_seconds":1800,"max_output_bytes":1_000_000},
          "ffprobe":str(self.ffprobe)
        }

    def check(self,ltx=False):
        return inspect_handoff(
            self.contract_file,self.voice_file,
            ltx_recipe=self.ltx_file if ltx else None,
            system="Darwin",arch="arm64",
            memory_bytes=48*1024**3,free_bytes=110*1024**3)

    def import_reference(self):
        return import_bunny(self.original,
              approved_source_root=self.external,private_root=self.root,
              asset_id="bunny_front_v01",original_sha256=sha(self.original))

    def test_voice_handoff_without_ltx_file_has_honest_pending_status(self):
        report=self.check()
        self.assertEqual(report["status"],"VOICE_READY_LTX_RECIPE_PENDING_APPROVED_WAV")
        self.assertIsNone(report["ltx"])
        self.assertFalse(report["models_executed"])
        self.assertFalse(report["actual_wrapper_api_tested"])
        self.assertFalse((self.root/"output").exists())
        self.assertNotIn(str(self.base),json.dumps(report))

    def test_import_is_non_destructive_and_not_implicit(self):
        before=self.original.read_bytes()
        preview=preview_import(self.original,
              approved_source_root=self.external,private_root=self.root,
              asset_id="bunny_front_v01",original_sha256=sha(self.original))
        self.assertFalse(preview["import_performed"])
        self.assertFalse((self.root/"assets").exists())
        self.import_reference()
        result=verify_import(self.root,"bunny_front_v01",sha(self.original))
        self.assertEqual(result["status"],"PRIVATE_REFERENCE_COPY_VERIFIED")
        self.assertEqual(self.original.read_bytes(),before)
        with self.assertRaises(IntakeError):
            self.import_reference()

    def test_full_static_handoff_requires_versioned_import(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        self.ltx_recipe=self._recipe("ltx_animate",reference)
        self._write(self.ltx_file,self.ltx_recipe)
        report=self.check(ltx=True)
        self.assertEqual(report["status"],"STAGE_MANIFESTS_MATCH_NOT_RUN")
        self.assertEqual(report["ltx"]["voice_sha256"],sha(self.wav))
        self.assertFalse(report["youtube_uploaded"])
        self.assertFalse((self.root/"output").exists())

    def test_unverified_copy_blocked(self):
        bogus=self.root/"bunny_copy.png"
        bogus.write_bytes(self.original.read_bytes())
        self._write(self.ltx_file,self._recipe("ltx_animate",bogus))
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_wrong_wrapper_in_ltx_stage_rejected(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        plan=self._recipe("ltx_animate",reference)
        plan["runner"]["entrypoint"]=str(self.assets["voice_wrapper"])
        plan["runner"]["entrypoint_sha256"]=sha(self.assets["voice_wrapper"])
        self._write(self.ltx_file,plan)
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_script_drift_in_ltx_blocked(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        other=self.root/"not_owner_script.txt";other.write_text("incorrect script")
        plan=self._recipe("ltx_animate",reference)
        plan["script"]={"path":str(other),"sha256":sha(other)}
        self._write(self.ltx_file,plan)
        with self.assertRaises(HandoffError):
            self.check(ltx=True)

    def test_missing_import_or_tampered_import_fails(self):
        self.import_reference()
        reference=self.root/"assets"/"imports"/"bunny_front_v01"/"bunny_reference.png"
        plan=self._recipe("ltx_animate",reference)
        self._write(self.ltx_file,plan)
        reference.write_bytes(b"tampered")
        with self.assertRaises(Exception):
            self.check(ltx=True)

    # M19: unlike M11's whole-episode handoff, each independently authored
    # scene requires a different pinned source script and voice recipe.
    def build_two_scene_pilot(self):
        from kidsstudio.two_scene_preflight import inspect_two_scene_voice_pilot
        scripts = []
        recipes = []
        records = []
        for number, color in ((1, "red"), (2, "blue")):
            script = self.root / f"scene_{number:02d}_approved.txt"
            script.write_text(f"Original scene {number}: recognize {color}.\\n",
                              encoding="utf-8")
            recipe = self._recipe("voice_synthesize", self.assets["approved_script"])
            recipe["script"] = {"path": str(script), "sha256": sha(script)}
            recipe["inputs"]["script"] = {"path": str(script), "sha256": sha(script)}
            path = self.root / f"voice_scene_{number:02d}.json"
            self._write(path, recipe)
            scripts.append(script)
            recipes.append(path)
            records.append({
                "scene": number,
                "script_sha256": sha(script),
                "objective": f"Recognize the {color} color in a familiar object",
            })
        plan = self.root / "m13_two_scene_plan.json"
        self._write(plan, {
            "schema_version": 1,
            "series_id": "colors-ar",
            "episode_number": 1,
            "episode_script_sha256": sha(self.assets["approved_script"]),
            "scenes": records,
        })
        plan_sha = sha(plan)
        def check():
            return inspect_two_scene_voice_pilot(
                self.contract_file, plan,
                expected_plan_sha256=plan_sha,
                scene_scripts=tuple(scripts),
                voice_recipes=tuple(recipes),
                system="Darwin", arch="arm64",
                memory_bytes=48*1024**3,
                free_bytes=110*1024**3,
            )
        return check, plan, scripts, recipes

    def test_m19_two_scene_handoff_accepts_distinct_pinned_scripts_without_execution(self):
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        before = {str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}
        report = check()
        after = {str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(report["status"], "TWO_SCENE_VOICE_CONFIG_PINNED_NOT_RUN")
        self.assertEqual(report["scene_count"], 2)
        self.assertNotEqual(report["scenes"][0]["scene_script_sha256"],
                            report["scenes"][1]["scene_script_sha256"])
        self.assertEqual(report["parent_script_sha256"],
                         sha(self.assets["approved_script"]))
        self.assertIs(report["canonical_pi_scene_approval_verified"], False)
        self.assertIs(report["actual_wrapper_api_tested"], False)
        self.assertIs(report["voice_or_animation_generated"], False)
        self.assertIs(report["public_release_authorized"], False)
        self.assertEqual(before, after)
        self.assertFalse((self.root / "output").exists())
        self.assertNotIn(str(self.base), json.dumps(report))

    def test_m19_swapped_voice_recipes_blocked(self):
        from kidsstudio.two_scene_preflight import (
            inspect_two_scene_voice_pilot, HandoffError,
        )
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        with self.assertRaises(HandoffError):
            inspect_two_scene_voice_pilot(
                self.contract_file, plan,
                expected_plan_sha256=sha(plan),
                scene_scripts=tuple(scripts),
                voice_recipes=(recipes[1], recipes[0]),
                system="Darwin", arch="arm64",
                memory_bytes=48*1024**3, free_bytes=110*1024**3,
            )
        self.assertFalse((self.root / "output").exists())

    def test_m19_tampered_scene_or_parent_and_duplicate_scene_are_denied(self):
        from kidsstudio.two_scene_preflight import PilotPreflightError
        from kidsstudio.episode_assembly import EpisodeAssemblyError
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        scripts[1].write_text("An unauthorized changed scene")
        with self.assertRaises(EpisodeAssemblyError):
            check()
        scripts[1].write_text("Original scene 2: recognize blue.\\n")
        data = json.loads(plan.read_text())
        data["episode_script_sha256"] = "b" * 64
        self._write(plan, data)
        with self.assertRaises(PilotPreflightError):
            check()
        data["episode_script_sha256"] = sha(self.assets["approved_script"])
        data["scenes"][1]["script_sha256"] = data["scenes"][0]["script_sha256"]
        self._write(plan, data)
        with self.assertRaises(PilotPreflightError):
            check()

    def test_m19_legacy_m11_still_does_not_accept_scene_script_as_parent(self):
        from kidsstudio.handoff_review import HandoffError
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        with self.assertRaises(HandoffError):
            self._check_invalid_m19_recipe_with_legacy_handoff(recipes[0])
        self.assertEqual(check()["status"], "TWO_SCENE_VOICE_CONFIG_PINNED_NOT_RUN")

    def _check_invalid_m19_recipe_with_legacy_handoff(self, recipe):
        return inspect_handoff(
            self.contract_file, recipe, system="Darwin", arch="arm64",
            memory_bytes=48*1024**3, free_bytes=110*1024**3
        )

    def test_m19_requires_pinned_owner_plan_sha_even_with_consistent_files(self):
        from kidsstudio.two_scene_preflight import PilotPreflightError
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        data = json.loads(plan.read_text())
        data["scenes"][0]["objective"] = "A changed objective after owner approval"
        self._write(plan, data)
        with self.assertRaises(PilotPreflightError):
            check()

    def prepare_m20_snapshot(self, *, owner_audit=True):
        import sqlite3
        from kidsstudio.studio_queue import StudioQueue
        from kidsstudio.series_manager import SeriesManager
        from kidsstudio.studio_scenes import SceneLedger
        from kidsstudio.m13_snapshot_gate import verify_two_scene_snapshot

        _, plan, scripts, recipes = self.build_two_scene_pilot()
        queue = StudioQueue(self.root / "m20_live_source.sqlite")
        queue.initialize()
        manager = SeriesManager(queue)
        manager.initialize()
        manager.create_series("colors-ar", "Learning colors", "ar",
            [{"title": "The red ball", "objective": "Identify a red ball"}],
            activate=True)
        with queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                source_sha256=?, owner_review_note=? WHERE
                series_id='colors-ar' AND ordinal=1""",
                (sha(self.assets["approved_script"]),
                 "Owner listened and read both original scene scripts"))
            if owner_audit:
                manager._audit(db, "colors-ar", 1, "SCRIPT_APPROVED_BY_OWNER")
        ledger = SceneLedger(queue)
        ledger.initialize()
        ledger.register_plan(plan)
        snapshot = self.root / "m20_offline_backup.sqlite"
        # SQLite online backup gives a consistent, WAL-free, closed file.
        with sqlite3.connect(queue.path) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        pinned_backup_sha = sha(snapshot)
        pinned_plan_sha = sha(plan)

        def check(*, snapshot_sha=None, plan_sha=None):
            return verify_two_scene_snapshot(
                self.contract_file, plan,
                expected_plan_sha256=plan_sha or pinned_plan_sha,
                scene_scripts=tuple(scripts),
                voice_recipes=tuple(recipes),
                pi_snapshot=snapshot,
                pi_snapshot_sha256=snapshot_sha or pinned_backup_sha,
                system="Darwin", arch="arm64",
                memory_bytes=48*1024**3, free_bytes=110*1024**3,
            )
        return check, queue, plan, scripts, recipes, snapshot

    def test_m20_offline_registered_m13_records_match_mac_without_any_execution(self):
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        before = {str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}
        result = check()
        after = {str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(result["status"],
                         "OFFLINE_M13_SNAPSHOT_MATCH_NOT_LIVE_PI_ATTESTED")
        self.assertEqual(result["scene_count"], 2)
        self.assertTrue(result["owner_approval_record_found_in_snapshot"])
        self.assertTrue(result["offline_scene_records_match"])
        self.assertFalse(result["snapshot_freshness_verified"])
        self.assertFalse(result["live_pi_state_verified"])
        self.assertFalse(result["model_inference_performed"])
        self.assertFalse(result["any_worker_jobs_queued"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(before, after)
        self.assertNotIn(str(self.base), json.dumps(result))
        self.assertFalse((self.root / "output").exists())

    def test_m20_rejects_modified_snapshot_bytes_and_stale_plan(self):
        from kidsstudio.m13_snapshot_gate import SnapshotGateError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        backup.write_bytes(backup.read_bytes() + b"offline-copy-tampered")
        with self.assertRaises(SnapshotGateError):
            check()
    def test_m20_rejects_a_re_pinned_snapshot_with_different_scene_objective(self):
        import sqlite3
        from kidsstudio.m13_snapshot_gate import SnapshotGateError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        with sqlite3.connect(backup) as db:
            db.execute("""UPDATE studio_scenes SET objective='Altered after approval'
                WHERE series_id='colors-ar' AND ordinal=1 AND scene=2""")
        with self.assertRaises(SnapshotGateError):
            check(snapshot_sha=sha(backup))

    def test_m20_requires_owner_audit_not_just_episode_state(self):
        from kidsstudio.m13_snapshot_gate import SnapshotGateError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot(
            owner_audit=False)
        with self.assertRaises(SnapshotGateError):
            check()

    def test_m20_rejects_in_progress_stage_even_when_approved_plan_matches(self):
        from kidsstudio.studio_scenes import SceneLedger
        from kidsstudio.m13_snapshot_gate import SnapshotGateError
        import sqlite3
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        SceneLedger(queue).queue_stage(
            "colors-ar", 1, 1, "voice_synthesize", "voice_scene_01")
        with sqlite3.connect(queue.path) as src:
            with sqlite3.connect(backup) as dst:
                src.backup(dst)
        with self.assertRaises(SnapshotGateError):
            check(snapshot_sha=sha(backup))

    def test_m20_rejects_wal_or_shm_snapshot_sidecars_without_writing(self):
        from kidsstudio.m13_snapshot_gate import SnapshotGateError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        journal = self.root / (backup.name + "-wal")
        journal.write_bytes(b"unexpected live database log")
        with self.assertRaises(SnapshotGateError):
            check()
        self.assertEqual(journal.read_bytes(), b"unexpected live database log")

    def _start_m21_local_tls(self, queue):
        from http.server import ThreadingHTTPServer
        import ssl
        import subprocess
        import threading
        from kidsstudio.coordinator_api import Coordinator, create_handler
        from kidsstudio.remote_worker import RemoteClient

        cert = self.root / "m21-local-test.crt"
        key = self.root / "m21-local-test.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-nodes", "-sha256", "-days", "1",
            "-keyout", str(key), "-out", str(cert),
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost",
        ], check=True, capture_output=True, timeout=20)
        token = "m21-test-secret-" + "v" * 40
        service = Coordinator(queue, self.root / "m21_vault",
            {"mac-voice-01": (token, {"voice_synthesize"}),
             "mac-editorial-01": ("e" * 40, {"script_draft"})})
        http = ThreadingHTTPServer(
            ("127.0.0.1", 0), create_handler(service))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        http.socket = ctx.wrap_socket(http.socket, server_side=True)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        base = f"https://localhost:{http.server_port}"
        return RemoteClient(base, worker_id="mac-voice-01",
                            token=token, ca_file=str(cert)), base, cert

    def _check_m21(self, client, plan, scripts, recipes, snapshot):
        from kidsstudio.live_m13_preflight import verify_live_two_scene_pilot
        return verify_live_two_scene_pilot(
            client, self.contract_file, plan,
            expected_plan_sha256=sha(plan),
            scene_scripts=tuple(scripts),
            voice_recipes=tuple(recipes),
            pi_snapshot=snapshot, pi_snapshot_sha256=sha(snapshot),
            system="Darwin", arch="arm64",
            memory_bytes=48*1024**3, free_bytes=110*1024**3,
        )

    @unittest.skipUnless(__import__("shutil").which("openssl"),
                         "ephemeral loopback TLS test needs openssl")
    def test_m21_real_tls_current_pi_matches_offline_snapshot_no_job_claimed(self):
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        client, base, cert = self._start_m21_local_tls(queue)
        self.assertEqual(check()["scene_count"], 2)
        original_db_sha = sha(queue.path)
        response = self._check_m21(client, plan, scripts, recipes, backup)
        self.assertEqual(response["status"],
            "OFFLINE_AND_LIVE_M13_AGREE_OWNER_EXECUTION_NOT_AUTHORIZED")
        self.assertTrue(response["live_pi_observed_over_authenticated_tls"])
        self.assertTrue(response["target_episode_matches_offline_at_observation"])
        self.assertFalse(response["whole_snapshot_freshness_proven"])
        self.assertFalse(response["worker_job_claimed"])
        self.assertFalse(response["model_execution_performed"])
        self.assertFalse(response["public_release_authorized"])
        self.assertEqual(sha(queue.path), original_db_sha)
        with queue._connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
        self.assertNotIn(str(self.base), json.dumps(response))

    @unittest.skipUnless(__import__("shutil").which("openssl"),
                         "ephemeral loopback TLS test needs openssl")
    def test_m21_stale_live_pi_rejected_after_pause_or_stage_queue(self):
        from kidsstudio.remote_worker import RemoteWorkerError
        from kidsstudio.series_manager import SeriesManager
        from kidsstudio.studio_scenes import SceneLedger
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        client, base, cert = self._start_m21_local_tls(queue)
        self._check_m21(client, plan, scripts, recipes, backup)
        SeriesManager(queue).pause("colors-ar", "Owner temporarily paused scene pilot")
        with self.assertRaises(RemoteWorkerError):
            self._check_m21(client, plan, scripts, recipes, backup)
        SeriesManager(queue).activate("colors-ar")
        SceneLedger(queue).queue_stage(
            "colors-ar", 1, 1, "voice_synthesize", "test_scene_01_voice")
        with self.assertRaises(RemoteWorkerError):
            self._check_m21(client, plan, scripts, recipes, backup)

    @unittest.skipUnless(__import__("shutil").which("openssl"),
                         "ephemeral loopback TLS test needs openssl")
    def test_m21_unauthorized_tls_and_wrong_capability_rejected(self):
        from kidsstudio.remote_worker import RemoteClient, RemoteWorkerError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        client, base, cert = self._start_m21_local_tls(queue)
        bad = RemoteClient(base, worker_id="mac-voice-01",
                           token="wrong-" + "x" * 40, ca_file=str(cert))
        with self.assertRaises(RemoteWorkerError):
            self._check_m21(bad, plan, scripts, recipes, backup)
        editorial = RemoteClient(base, worker_id="mac-editorial-01",
                                 token="e"*40, ca_file=str(cert))
        with self.assertRaises(RemoteWorkerError):
            self._check_m21(editorial, plan, scripts, recipes, backup)
        untrusted = RemoteClient(base, worker_id="mac-voice-01",
                                 token=client.token)
        with self.assertRaises(RemoteWorkerError):
            self._check_m21(untrusted, plan, scripts, recipes, backup)

    @unittest.skipUnless(__import__("shutil").which("openssl"),
                         "ephemeral loopback TLS test needs openssl")
    def test_m21_nonce_mismatch_rejected_even_after_valid_tls(self):
        from kidsstudio.remote_worker import RemoteClient
        from kidsstudio.live_m13_preflight import LivePreflightError
        check, queue, plan, scripts, recipes, backup = self.prepare_m20_snapshot()
        client, base, cert = self._start_m21_local_tls(queue)
        class MutatingClient(RemoteClient):
            def call(self, operation, body):
                r = super().call(operation, body)
                if operation == "pilot-readiness":
                    r["nonce"] = "0"*32 if body["nonce"] != "0"*32 else "1"*32
                return r
        fake = MutatingClient(base, worker_id=client.worker_id,
                              token=client.token, ca_file=str(cert))
        with self.assertRaises(LivePreflightError):
            self._check_m21(fake, plan, scripts, recipes, backup)

    def prepare_m22_voice_lease(self):
        from kidsstudio.studio_scenes import SceneLedger
        from kidsstudio.coordinator_api import Coordinator
        from kidsstudio.media_worker import MediaRecipes, MediaJournal, RemoteMediaWorker
        from kidsstudio.remote_worker import RemoteWorkerError
        from kidsstudio.coordinator_api import TransportError
        import time

        _, queue, plan, scripts, voice_recipes, backup = self.prepare_m20_snapshot()
        ledger=SceneLedger(queue)
        job_id=ledger.queue_first_voice_pilot(
            "colors-ar",1,"m22_voice_scene01",sha(plan),
            "Owner expressly queued scene one synthetic voice qualification")
        class Pi:
            def __init__(self, api):
                self.api=api
                self.reject_proof=False
            def call(self, action, request):
                try:
                    result=self.api.dispatch(action,request,"mac-voice-01",
                                             frozenset({"voice_synthesize"}))
                    result["server_time"]=time.time()
                    if action=="pilot-voice-lease-check" and self.reject_proof:
                        result["script_sha256"]="0"*64
                    return result
                except (TransportError, ValueError) as exc:
                    raise RemoteWorkerError("Synthetic Pi rejected request") from exc
        service=Coordinator(queue,self.root/"m22_vault",
            {"mac-voice-01":("m22-test-"+"z"*40,{"voice_synthesize"})})
        pi=Pi(service)
        recipe_catalogue=self.root/"m22_recipes.json"
        self._write(recipe_catalogue,{
            "schema_version":1,
            "recipes":{"m22_voice_scene01":{
                "kind":"voice_synthesize",
                "output_root":str(self.root/"output"),
                "inputs":{"stage_recipe":str(voice_recipes[0])},
                "sha256":{"stage_recipe":sha(voice_recipes[0])},
            }}
        })
        class FakeVoice:
            def __init__(self):
                self.calls=[]
            def execute(self,kind,recipe_id,job):
                self.calls.append((kind,recipe_id,job))
                return {
                    "result_status":"VOICE_RENDERED_PENDING_QA",
                    "artifact_sha256":"a"*64,"artifact_bytes":1024,
                    "artifact_type":"wav","publication_approved":False,
                }
        fake=FakeVoice()
        journal=MediaJournal(self.root/"m22_journal.sqlite")
        worker=RemoteMediaWorker(pi,MediaRecipes(recipe_catalogue),
                                 journal,executor=fake)
        return queue,plan,job_id,service,pi,fake,worker,journal

    def test_m22_queues_exact_first_scene_once_never_two_jobs(self):
        from kidsstudio.studio_scenes import SceneLedger, SceneError
        _, queue, plan, scripts, recipes, snapshot = self.prepare_m20_snapshot()
        ledger=SceneLedger(queue)
        with self.assertRaises(SceneError):
            ledger.queue_first_voice_pilot("colors-ar",1,"m22_voice_scene01",
                "b"*64,"Owner requested the first voice only")
        job_id=ledger.queue_first_voice_pilot(
            "colors-ar",1,"m22_voice_scene01",sha(plan),
            "Owner explicitly approves a first scene pilot for testing")
        with self.assertRaises(SceneError):
            ledger.queue_first_voice_pilot(
                "colors-ar",1,"m22_voice_scene01",sha(plan),
                "Owner second click must never create another stage job")
        with queue._connection() as db:
            rows=db.execute("SELECT job_id,payload,max_attempts FROM jobs").fetchall()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["job_id"],job_id)
            self.assertEqual(rows[0]["max_attempts"],1)
            self.assertEqual(json.loads(rows[0]["payload"])["pilot_scene"],1)

    def test_m22_matching_live_lease_synthetic_worker_runs_only_once(self):
        queue,plan,job_id,service,pi,fake,worker,journal=self.prepare_m22_voice_lease()
        result=worker.run_once()
        self.assertEqual(result["status"],"COMPLETED")
        self.assertEqual(len(fake.calls),1)
        self.assertEqual(fake.calls[0],("voice_synthesize","m22_voice_scene01",job_id))
        self.assertEqual(queue.get(job_id)["state"],"COMPLETED")
        self.assertEqual(worker.run_once()["status"],"NO_ELIGIBLE_JOB")
        self.assertEqual(len(fake.calls),1)

    def test_m22_stale_or_mutated_live_plan_blocks_before_journal_or_voice(self):
        queue,plan,job_id,service,pi,fake,worker,journal=self.prepare_m22_voice_lease()
        with queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_plans SET plan_sha256=?
                WHERE series_id='colors-ar' AND ordinal=1""",("f"*64,))
        self.assertEqual(worker.run_once()["status"],"PILOT_LEASE_REJECTED")
        self.assertEqual(fake.calls,[])
        self.assertEqual(queue.get(job_id)["state"],"FAILED")
        import sqlite3
        with sqlite3.connect(journal.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],0)

    def test_m22_pi_proof_tamper_prevents_synthetic_model_invocation(self):
        queue,plan,job_id,service,pi,fake,worker,journal=self.prepare_m22_voice_lease()
        pi.reject_proof=True
        self.assertEqual(worker.run_once()["status"],"PILOT_LEASE_REJECTED")
        self.assertEqual(fake.calls,[])
        self.assertEqual(queue.get(job_id)["state"],"FAILED")

    def test_m22_pause_rejects_at_preexecution_check_and_no_retry(self):
        from kidsstudio.series_manager import SeriesManager
        queue,plan,job_id,service,pi,fake,worker,journal=self.prepare_m22_voice_lease()
        original_call=pi.call
        def call_then_pause(action,request):
            if action=="pilot-voice-lease-check":
                SeriesManager(queue).pause("colors-ar",
                    "Owner paused pilot immediately after job claim")
            return original_call(action,request)
        pi.call=call_then_pause
        self.assertEqual(worker.run_once()["status"],"PILOT_LEASE_REJECTED")
        self.assertEqual(fake.calls,[])
        self.assertEqual(queue.get(job_id)["state"],"FAILED")

    def test_m22_revoked_lease_rejected_before_voice(self):
        queue,plan,job_id,service,pi,fake,worker,journal=self.prepare_m22_voice_lease()
        original=pi.call
        def cancel_just_before_proof(action,request):
            if action=="pilot-voice-lease-check":
                queue.cancel(job_id)
            return original(action,request)
        pi.call=cancel_just_before_proof
        self.assertEqual(worker.run_once()["status"],"PILOT_LEASE_REJECTED")
        self.assertEqual(fake.calls,[])
        self.assertEqual(queue.get(job_id)["state"],"CANCELLED")

    def test_m19_wrong_stage_wrapper_is_blocked_even_if_script_matches(self):
        from kidsstudio.handoff_review import HandoffError
        check, plan, scripts, recipes = self.build_two_scene_pilot()
        content = json.loads(recipes[1].read_text())
        content["runner"]["entrypoint"] = str(self.assets["ltx_wrapper"])
        content["runner"]["entrypoint_sha256"] = sha(self.assets["ltx_wrapper"])
        self._write(recipes[1], content)
        with self.assertRaises(HandoffError):
            check()




if __name__=="__main__":
    unittest.main()
