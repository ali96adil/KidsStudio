"""Offline Mac model-stage integration contracts with synthetic artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.voice_animation_stage import StagePlan, StageError


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeEngine:
    def __init__(self, *, error=False, symlink=False):
        self.calls=[]
        self.error=error
        self.symlink=symlink

    def __call__(self, argv, timeout, env):
        self.calls.append((argv,timeout,env))
        if self.error:
            raise StageError("Synthetic GPU failure")
        out=Path(argv[argv.index("--output")+1])
        if self.symlink:
            out.symlink_to(Path(argv[argv.index("--script")+1]))
        else:
            out.write_bytes(b"synthetic-media-only" * 20)


def audio_probe(path, executable):
    return {"duration":3.2, "audio_streams":1}


def video_probe(path, executable):
    return {"duration":3.3, "audio_streams":1, "width":384, "height":384}


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.script=self.root/"approved_ar.txt"
        self.script.write_text("الكرة حمراء!",encoding="utf-8")
        self.voice=self.root/"narration.wav";self.voice.write_bytes(b"previous-approved-voice")
        self.reference=self.root/"bunny.png";self.reference.write_bytes(b"synthetic-original-identity")
        self.engine=self.root/"engine.json"
        self.engine.write_text('{"models":"manually pinned later"}')
        self.runner=self.root/"owner_adapter.py"
        self.runner.write_text("raise SystemExit('fake; never directly executed')\n")
        self.plan=self.root/"stage.json"
        self.base={
          "schema_version":1,"kind":"voice_synthesize",
          "private_root":str(self.root),
          "output_root":str(self.root/"stage_outputs"),
          "script":{"path":str(self.script),"sha256":sha(self.script)},
          "inputs":{"script":{"path":str(self.script),"sha256":sha(self.script)}},
          "runner":{"python":sys.executable,"python_sha256":sha(Path(sys.executable)),
                    "entrypoint":str(self.runner),"entrypoint_sha256":sha(self.runner),
                    "args":["--script","{script}","--engine","{engine_manifest}",
                            "--output","{output}"]},
          "engine_manifest":{"path":str(self.engine),"sha256":sha(self.engine)},
          "voice_rights":"INTERNAL_TEST_ONLY",
          "limits":{"timeout_seconds":60,"max_output_bytes":1000000},
          "ffprobe":sys.executable
        }
        self.save()

    def save(self):
        self.plan.write_text(json.dumps(self.base,ensure_ascii=False),encoding="utf-8")

    def stage(self, fake):
        return StagePlan(self.plan,execute=fake,voice_probe=audio_probe,video_probe=video_probe)

    def test_readonly_preflight_no_model_call(self):
        fake=FakeEngine()
        stage=self.stage(fake)
        report=stage.preflight()
        self.assertEqual(report["status"],"LOCAL_ENGINE_CONFIG_READY_NOT_RUN")
        self.assertFalse(report["inference_performed"])
        self.assertFalse(report["model_weights_verified"])
        self.assertEqual(fake.calls,[])
        self.assertFalse((self.root/"stage_outputs").exists())

    def test_voice_output_receipt_is_private_and_immutable(self):
        fake=FakeEngine()
        stage=self.stage(fake)
        job="a"*32
        r=stage.run(job)
        self.assertEqual(r["status"],"VOICE_RENDERED_PENDING_QA")
        self.assertEqual(r["artifact_type"],"wav")
        self.assertFalse(r["publication_approved"])
        self.assertEqual(len(fake.calls),1)
        self.assertEqual(fake.calls[0][2]["KIDS_STUDIO_OFFLINE"],"1")
        with self.assertRaises(StageError):
            stage.run(job)
        self.assertEqual(len(fake.calls),1)
        self.assertTrue((self.root/"stage_outputs"/job/"stage_receipt.json").exists())

    def test_animation_requires_pinned_audio_and_image(self):
        self.base["kind"]="ltx_animate"
        self.base["inputs"]={
          "voice_wav":{"path":str(self.voice),"sha256":sha(self.voice)},
          "reference_image":{"path":str(self.reference),"sha256":sha(self.reference)}
        }
        self.base["runner"]["args"]=[
          "--script","{script}","--audio","{voice_wav}",
          "--reference","{reference_image}","--engine","{engine_manifest}",
          "--output","{output}"
        ]
        self.save()
        fake=FakeEngine()
        stage=self.stage(fake)
        report=stage.run("b"*32)
        self.assertEqual(report["status"],"A2V_RENDERED_PENDING_QA")
        self.assertEqual(report["source_voice_sha256"],sha(self.voice))
        self.assertEqual(report["artifact_type"],"mp4")

    def test_source_modified_after_loading_fails_closed(self):
        fake=FakeEngine();stage=self.stage(fake)
        self.script.write_text("A different unreviewed script")
        with self.assertRaises(Exception):
            stage.run("c"*32)
        self.assertEqual(fake.calls,[])

    def test_untrusted_arg_or_script_unpinned_is_rejected(self):
        self.base["runner"]["args"].insert(0,"$(curl malicious)")
        self.save()
        with self.assertRaises(StageError):
            self.stage(FakeEngine())
        self.base["runner"]["args"]=self.base["runner"]["args"][1:]
        self.base["runner"]["entrypoint_sha256"]="0"*64
        self.save()
        with self.assertRaises(Exception):
            self.stage(FakeEngine())

    def test_output_symlink_blocked_and_manual_reconciliation(self):
        engine=FakeEngine(symlink=True)
        stage=self.stage(engine)
        job="d"*32
        with self.assertRaises(StageError):
            stage.run(job)
        report=json.loads((self.root/"stage_outputs"/job/"stage_receipt.json").read_text())
        self.assertEqual(report["status"],"FAILED_REQUIRES_MANUAL_RECONCILIATION")
        with self.assertRaises(StageError):
            stage.run(job)
        self.assertEqual(len(engine.calls),1)

    def test_execution_failure_leaves_immutable_failed_attempt(self):
        fake=FakeEngine(error=True)
        stage=self.stage(fake)
        with self.assertRaises(StageError):
            stage.run("e"*32)
        self.assertEqual(len(fake.calls),1)
        self.assertTrue((self.root/"stage_outputs"/("e"*32)).is_dir())


if __name__=="__main__":
    unittest.main()
