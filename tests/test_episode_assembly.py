"""Offline M4 episode assembly contract tests; synthetic files only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.episode_assembly import EpisodeAssembler, EpisodeAssemblyError


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeMedia:
    """No ffmpeg, Chatterbox, LTX or network call is made in these tests."""
    def __init__(self, fail_at=0):
        self.calls=[]
        self.fail_at=fail_at

    def run(self, args, *, timeout=1200):
        self.calls.append(args)
        if self.fail_at and len(self.calls) == self.fail_at:
            raise EpisodeAssemblyError("Fake stage failure")
        if "--output" in args:
            dest=Path(args[args.index("--output")+1])
        else:
            dest=Path(args[-1])
        dest.write_bytes(b"fake-video-bytes" + str(len(self.calls)).encode())

    def probe(self,path,cmd):
        if not path.is_file() or not path.stat().st_size:
            raise EpisodeAssemblyError("missing synthetic media")
        final=path.name=="episode_qa_master.mp4"
        normalized="normalized" in path.name
        return {"width":1280 if (final or normalized) else 384,
                "height":720 if (final or normalized) else 384,
                "duration":8.0 if final else 4.0,
                "audio_streams":1}


class EpisodeAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        (self.root/"private").mkdir()
        self.assets=self.root/"private"
        self.script=self.assets/"script.txt"
        self.script.write_text("كرتي حمراء",encoding="utf-8")
        self.video=self.assets/"scene.mp4"
        self.video.write_bytes(b"source-artifact")
        self.v06=self.assets/"v06.py"
        self.v07=self.assets/"v07.py"
        self.v06.write_text("pass\n")
        self.v07.write_text("pass\n")
        self.recipe=self.assets/"episode.json"
        self.data={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.assets),"output_root":str(self.assets/"runs"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(self.script),"sha256":sha(self.script)},
            "tools":{
                "ffmpeg":sys.executable,"ffprobe":sys.executable,
                "face_python":sys.executable,
                "face_v06":str(self.v06),"face_v06_sha256":sha(self.v06),
                "face_v07":str(self.v07),"face_v07_sha256":sha(self.v07),
            },
            "clips":[
                {"video":str(self.video),"sha256":sha(self.video),
                 "face_cleanup":"bunny_v07"},
                {"video":str(self.video),"sha256":sha(self.video),
                 "face_cleanup":"none"}
            ]
        }
        self.save()

    def save(self):
        self.recipe.write_text(json.dumps(self.data),encoding="utf-8")

    def engine(self, media=None):
        media=media or FakeMedia()
        return EpisodeAssembler(self.recipe,runner=media.run,prober=media.probe)

    def test_preflight_is_readonly(self):
        media=FakeMedia()
        engine=self.engine(media)
        result=engine.preflight()
        self.assertEqual(result["source_duration_seconds"],8)
        self.assertEqual(result["status"],"READY_FOR_LOCAL_ASSEMBLY")
        self.assertFalse(result["publication_approved"])
        self.assertFalse((self.assets/"runs").exists())
        self.assertEqual(media.calls,[])

    def test_two_scenes_one_approved_face_path_and_immutable_result(self):
        media=FakeMedia()
        engine=self.engine(media)
        result=engine.execute(run_id="colors-ep01-preview")
        self.assertEqual(result["status"],"RENDERED_PENDING_HUMAN_AV_QA")
        self.assertFalse(result["publication_approved"])
        self.assertEqual(result["clips_built"],2)
        self.assertEqual(len(media.calls),5) # v06,v07, normalize x2, concat
        self.assertIn("v06.py",media.calls[0][1])
        self.assertIn("v07.py",media.calls[1][1])
        self.assertEqual(sha(self.video),self.data["clips"][0]["sha256"])
        run=self.assets/"runs"/"colors-ep01-preview"
        self.assertTrue((run/"qa_report.json").is_file())
        self.assertEqual(len((run/"concat.ffconcat").read_text().splitlines()),3)
        with self.assertRaises(EpisodeAssemblyError):
            engine.execute(run_id="colors-ep01-preview")

    def test_changed_source_hash_is_rejected_before_execution(self):
        engine=self.engine(FakeMedia())
        self.video.write_bytes(b"substituted-video")
        with self.assertRaises(EpisodeAssemblyError):
            engine.preflight()
        self.assertFalse((self.assets/"runs").exists())

    def test_reject_invalid_profile_and_escape(self):
        self.data["clips"][0]["face_cleanup"]="unknown"
        self.save()
        with self.assertRaises(EpisodeAssemblyError):
            self.engine()
        self.data["clips"][0]["face_cleanup"]="none"
        self.data["output_root"]=str(self.root/"untrusted")
        self.save()
        with self.assertRaises(EpisodeAssemblyError):
            self.engine()

    def test_media_stage_failure_is_not_auto_retried(self):
        media=FakeMedia(fail_at=3)
        engine=self.engine(media)
        with self.assertRaises(EpisodeAssemblyError):
            engine.execute(run_id="fail-once")
        report=json.loads((self.assets/"runs"/"fail-once"/"qa_report.json").read_text())
        self.assertEqual(report["status"],"FAILED_REQUIRES_MANUAL_RECONCILIATION")
        count=len(media.calls)
        with self.assertRaises(EpisodeAssemblyError):
            engine.execute(run_id="fail-once")
        self.assertEqual(len(media.calls),count)

    def test_face_cleanup_geometry_guard(self):
        media=FakeMedia()
        def bad_probe(path,cmd):
            result=media.probe(path,cmd)
            if path==self.video:
                result["width"]=1024
                result["height"]=1024
            return result
        engine=EpisodeAssembler(self.recipe,runner=media.run,prober=bad_probe)
        with self.assertRaises(EpisodeAssemblyError):
            engine.preflight()
        self.assertEqual(media.calls,[])

    def test_empty_audio_stream_rejected_by_real_probe_parser(self):
        from kidsstudio.episode_assembly import probe_video
        from unittest.mock import patch
        from types import SimpleNamespace
        fake=json.dumps({"streams":[{"codec_type":"video",
             "width":384,"height":384}],"format":{"duration":"4.0"}})
        with patch("kidsstudio.episode_assembly.subprocess.run",
             return_value=SimpleNamespace(stdout=fake.encode(),stderr=b"",returncode=0)):
            with self.assertRaises(EpisodeAssemblyError):
                probe_video(self.video,sys.executable)


if __name__=="__main__":
    unittest.main()
