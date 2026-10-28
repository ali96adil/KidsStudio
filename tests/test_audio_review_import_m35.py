"""M35 tests use synthetic M34 tone and MOCK audio reviewers only."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.audio_review_import import import_voice_review, AudioImportError
from kidsstudio.real_media_evidence import digest
from test_local_audio_review_m34 import AudioWorker34, executable
from test_studio_orchestrator_m32 import Orchestration32


class AudioReviewImport35(unittest.TestCase):
    def setUp(self):
        audio = AudioWorker34("test_actual_WAV_is_decoded_and_two_mock_audio_adapters_produce_signed_m28")
        audio.setUp()
        self.addCleanup(audio.doCleanups)
        self.audio = audio
        host = Orchestration32("test_plan_cannot_advertise_public_permission")
        host.setUp()
        self.addCleanup(host.doCleanups)
        self.host = host
        host.coord.pin(host.plan)
        voice = host.coord.tick(host.plan)
        self.assertEqual(voice["action"], "FIRST_AI_VOICE")
        self.job_id = voice["job_id"]
        leased = host.queue.claim(worker_id="synthetic-m35-mac",
                                  capabilities=["voice_synthesize"])
        self.assertEqual(leased["job_id"], self.job_id)
        host.queue.complete(job_id=self.job_id, worker_id="synthetic-m35-mac",
            generation=leased["generation"], result={
                "status": "VOICE_RENDERED_PENDING_QA",
                "artifact_type": "wav", "artifact_sha256": digest(audio.wav),
                "artifact_bytes": audio.wav.stat().st_size,
                "publication_approved": False})
        host.scenes.reconcile()
        # The ASR fixture transcribes the script exactly. No real ASR model
        # or child-voice competency has been tested by these tests.
        script = host.scripts[0]
        fake_whisper = executable(audio.root / "mock-m35-whisper",
            "import sys\nfrom pathlib import Path\n"
            "a=sys.argv\nPath(a[a.index('-of')+1]+'.txt').write_text("
            +repr(script.read_text(encoding="utf-8"))+",encoding='utf-8')\n")
        audio.run_review(job_id=self.job_id, script=script,
                         script_sha=digest(script),
                         whisper_binary=str(fake_whisper))
        self.folder = audio.root / "run01"

    def run_import(self, execute=False, **changes):
        args = {
            "queue": self.host.queue, "series_id": "colors-ar",
            "episode": 1, "scene": 1, "report_dir": self.folder,
            "rights_file": self.audio.rights, "runner_key": self.audio.key,
            "execute": execute,
        }
        args.update(changes)
        return import_voice_review(**args)

    def test_read_only_preflight_then_exact_signed_import_then_idempotent_replay(self):
        preview = self.run_import()
        self.assertEqual(preview["status"],
                         "M35_CURRENT_SIGNED_REPORT_PREFLIGHT_NO_WRITES")
        self.assertFalse(preview["public_release_authorized"])
        with self.host.queue._connection() as db:
            count = db.execute("SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0]
            self.assertEqual(count, 0)
        applied = self.run_import(execute=True)
        self.assertEqual(applied["status"],
                         "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY")
        self.assertEqual(self.host.coord.status(self.host.plan)["next_action"],
                         "NEXT_LTX")
        again = self.run_import(execute=True)
        self.assertEqual(again["status"],
                         "M35_ALREADY_IMPORTED_PRIVATE_STAGE_APPROVED")
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_ai_reviews").fetchone()[0], 1)

    def test_bad_hmac_is_blocked_before_technical_receipt_mutation(self):
        report = self.folder / "signed_voice_m28.json"
        doc = json.loads(report.read_text(encoding="utf-8"))
        doc["artifact_sha256"] = "f"*64
        report.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(AudioImportError):
            self.run_import(execute=True)
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0], 0)

    def test_correctly_signed_report_for_different_job_still_blocked(self):
        report = self.folder / "signed_voice_m28.json"
        doc = json.loads(report.read_text(encoding="utf-8"))
        doc["job_id"] = "f"*32
        unsigned = {k:v for k,v in doc.items() if k != "runner_attestation"}
        payload = json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        doc["runner_attestation"]["hmac_sha256"] = hmac.new(
            self.audio.key, payload, hashlib.sha256).hexdigest()
        report.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(AudioImportError):
            self.run_import(execute=True)
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0], 0)

    def test_queue_pause_blocks_import_before_any_state_change(self):
        self.host.queue.set_paused(True)
        with self.assertRaises(AudioImportError):
            self.run_import(execute=True)
        self.host.queue.set_paused(False)
        ok = self.run_import(execute=True)
        self.assertEqual(ok["status"],
                         "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY")

    def test_tampered_source_rights_and_wrong_key_fail_closed(self):
        with self.assertRaises(AudioImportError):
            self.run_import(runner_key=b"different-eligible-key-here-xxxxxxx")
        self.audio.rights.write_text("{}")
        with self.assertRaises(AudioImportError):
            self.run_import(execute=True)
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0], 0)

    def test_exact_m23_only_interrupted_import_can_resume(self):
        self.host.scenes.register_voice_technical(
            "colors-ar", 1, 1, self.folder / "voice_technical.json")
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_voice_checks").fetchone()[0], 1)
        applied = self.run_import(execute=True)
        self.assertEqual(applied["status"],
                         "M35_AI_VOICE_APPROVED_INTERNAL_PRIVATE_ONLY")
        self.assertEqual(self.host.coord.status(self.host.plan)["next_action"],
                         "NEXT_LTX")

    def test_different_preexisting_m23_receipt_does_not_overwrite(self):
        self.host.scenes.register_voice_technical(
            "colors-ar", 1, 1, self.folder / "voice_technical.json")
        with self.host.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_scene_voice_checks
                SET report_sha256=? WHERE series_id=? AND ordinal=?
                AND scene=?""", ("b"*64, "colors-ar", 1, 1))
        with self.assertRaises(AudioImportError):
            self.run_import(execute=True)
        with self.host.queue._connection() as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM studio_scene_ai_reviews").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
