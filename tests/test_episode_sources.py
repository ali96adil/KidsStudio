"""M5 media source readiness tests without loading models or running ffprobe."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.episode_sources import EpisodeSourcePreflight, SourceError
from kidsstudio.episode_assembly import EpisodeAssembler


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def voice_probe(path:Path,executable:str)->dict:
    return {"duration":2.8,"audio_streams":1}


def video_probe(path:Path,executable:str)->dict:
    return {"duration":4.0,"width":384,"height":384,"audio_streams":1}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.script=self.root/"approved_script.txt"
        self.script.write_text("مرحبا! كرة حمراء.",encoding="utf-8")
        self.wav=self.root/"chatterbox.wav";self.wav.write_bytes(b"mock-wav-audio")
        self.a2v=self.root/"ltx_a2v.mp4";self.a2v.write_bytes(b"mock-ltx-mp4")
        self.v06=self.root/"face_v06.py";self.v06.write_text("pass\n")
        self.v07=self.root/"face_v07.py";self.v07.write_text("pass\n")
        self.file=self.root/"voice_animation_sources.json"
        self.data={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "language":"ar","private_root":str(self.root),
            "output_root":str(self.root/"renders"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(self.script),"sha256":sha(self.script)},
            "tools":{
               "ffmpeg":sys.executable,"ffprobe":sys.executable,
               "face_python":sys.executable,"face_v06":str(self.v06),
               "face_v06_sha256":sha(self.v06),
               "face_v07":str(self.v07),"face_v07_sha256":sha(self.v07)
            },
            "scenes":[{
               "scene":1,"voice_wav":str(self.wav),"voice_sha256":sha(self.wav),
               "ltx_video":str(self.a2v),"ltx_sha256":sha(self.a2v),
               "source_voice_sha256":sha(self.wav),"face_cleanup":"bunny_v07"
            }]
        }
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.data,ensure_ascii=False),
                             encoding="utf-8")

    def inspector(self):
        return EpisodeSourcePreflight(self.file,voice_prober=voice_probe,
                                       video_prober=video_probe)

    def test_source_preflight_makes_no_changes_or_inference(self):
        report=self.inspector().preflight()
        self.assertEqual(report["status"],"MEDIA_SOURCES_PROBED_AWAITING_OWNER_QA")
        self.assertFalse(report["inference_performed"])
        self.assertFalse(report["publishing_approved"])
        self.assertEqual(report["scenes"][0]["voice_identity_or_lipsync"],
                         "HUMAN_QA_REQUIRED")
        self.assertEqual(report["scenes"][0]["voice_sha256"],sha(self.wav))
        self.assertFalse((self.root/"renders").exists())

    def test_write_pinned_recipe_compatible_with_assembler(self):
        target=self.root/"recipes"/"ep01.json"
        report=self.inspector().write_assembly_recipe(target)
        self.assertEqual(report["assembly_recipe_sha256"],sha(target))
        self.assertTrue(report["owner_approval_required"])
        assembly=EpisodeAssembler(target,prober=video_probe)
        self.assertEqual(assembly.preflight()["clips"][0]["face_cleanup"],
                         "bunny_v07")
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        with self.assertRaises(SourceError):
            self.inspector().write_assembly_recipe(target)

    def test_cannot_register_wrong_voice_parent(self):
        self.data["scenes"][0]["source_voice_sha256"]="f"*64
        self.save()
        with self.assertRaises(SourceError):
            self.inspector()

    def test_changed_file_after_constructor_is_blocked(self):
        inspector=self.inspector()
        self.wav.write_bytes(b"altered voice!")
        with self.assertRaises(SourceError):
            inspector.preflight()

    def test_missing_provenance_and_disallowed_cleanup_blocked(self):
        self.data["scenes"][0]["face_cleanup"]="auto_anyface"
        self.save()
        with self.assertRaises(SourceError):
            self.inspector()

    def test_face_geometry_guard(self):
        def bad(path,exe):
            result=video_probe(path,exe)
            result["width"]=1024
            return result
        check=EpisodeSourcePreflight(self.file,voice_prober=voice_probe,
                                      video_prober=bad)
        with self.assertRaises(SourceError):
            check.preflight()

    def test_output_escape_prohibited(self):
        self.data["output_root"]=str(self.root.parent/"elsewhere")
        self.save()
        with self.assertRaises(SourceError):
            self.inspector()

    def test_changed_source_plan_after_construct_is_blocked(self):
        instance=self.inspector()
        self.file.write_text("{}")
        with self.assertRaises(SourceError):
            instance.preflight()


if __name__=="__main__":
    unittest.main()
