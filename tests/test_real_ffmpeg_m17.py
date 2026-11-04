"""M17 actual FFmpeg/FFprobe integration — NO Chatterbox/LTX or Mac deployment.

These tests invoke real FFmpeg on a GitHub CI runner to generate *synthetic*
color-and-tone clips, then execute the actual Kids Studio M4 assembler and
M6 MediaExecutor. They validate the audiovisual media pipeline, NOT the
quality, licensing, voice, lip-sync or validity of AI model output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from kidsstudio.episode_assembly import EpisodeAssembler, EpisodeAssemblyError, probe_video
from kidsstudio.media_worker import MediaRecipes, MediaExecutor


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealFFmpegPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="kidsstudio-real-ffmpeg-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        # Missing system binaries are integration failures; do NOT silently
        # skip a test and later report it as a successful real FFmpeg run.
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        self.assertIsNotNone(self.ffmpeg,"Install ffmpeg on the CI runner.")
        self.assertIsNotNone(self.ffprobe,"Install ffprobe on the CI runner.")
        self.private=self.root/"private"
        self.private.mkdir()
        self.script=self.private/"approved_script.txt"
        self.script.write_text("Original synthetic educational pilot: red and blue.",encoding="utf-8")
        self.v06=self.private/"face_v06.py"
        self.v07=self.private/"face_v07.py"
        self.v06.write_text("# Not invoked in no-face-cleanup integration test.\n")
        self.v07.write_text("# Not invoked in no-face-cleanup integration test.\n")
        self.recipe_file=self.private/"recipe.json"

    def _clip(self,name,color,freq,*,audio=True):
        path=self.private/(name+".mp4")
        command=[
            self.ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-y",
            "-f","lavfi","-i",f"color=c={color}:s=384x384:r=24:d=1.2",
        ]
        if audio:
            command += [
                "-f","lavfi","-i",
                f"sine=frequency={freq}:sample_rate=48000:duration=1.2",
                "-map","0:v:0","-map","1:a:0",
            ]
        command += ["-t","1.2","-c:v","libx264","-preset","ultrafast",
                    "-pix_fmt","yuv420p"]
        if audio:
            command += ["-c:a","aac","-b:a","96k"]
        command += ["-movflags","+faststart",str(path)]
        subprocess.run(command,check=True,timeout=60,capture_output=True)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size,200)
        return path

    def _make_recipe(self,clips):
        data={
            "schema_version":1,
            "series_id":"colors-ar",
            "episode_number":1,
            "private_root":str(self.private),
            "output_root":str(self.private/"rendered"),
            "script":{"path":str(self.script),"sha256":sha(self.script)},
            "voice_rights":"INTERNAL_TEST_ONLY",
            "tools":{
                "ffmpeg":self.ffmpeg,"ffprobe":self.ffprobe,
                "face_python":sys.executable,
                "face_v06":str(self.v06),
                "face_v06_sha256":sha(self.v06),
                "face_v07":str(self.v07),
                "face_v07_sha256":sha(self.v07)
            },
            "clips":[{
                "video":str(clip),"sha256":sha(clip),
                "face_cleanup":"none"
            } for clip in clips]
        }
        self.recipe_file.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
        return data

    def test_real_two_scene_ffmpeg_video_and_audio_assembly(self):
        red=self._clip("scene_red","red",440)
        blue=self._clip("scene_blue","blue",660)
        recipe=self._make_recipe([red,blue])
        original=(sha(red),sha(blue))
        engine=EpisodeAssembler(self.recipe_file)
        readiness=engine.preflight()
        self.assertEqual(readiness["status"],"READY_FOR_LOCAL_ASSEMBLY")
        self.assertEqual(len(readiness["clips"]),2)
        self.assertFalse((self.private/"rendered").exists())
        report=engine.execute(run_id="pilot-m17-ffmpeg")
        self.assertEqual(report["status"],"RENDERED_PENDING_HUMAN_AV_QA")
        self.assertEqual(report["clips_built"],2)
        self.assertFalse(report["publication_approved"])
        master=Path(report["final_media_path"])
        self.assertEqual(master,self.private/"rendered"/"pilot-m17-ffmpeg"/"episode_qa_master.mp4")
        info=probe_video(master,self.ffprobe)
        self.assertEqual((info["width"],info["height"]),(1280,720))
        self.assertEqual(info["audio_streams"],1)
        self.assertAlmostEqual(info["duration"],2.4,delta=.5)
        self.assertEqual(sha(master),report["final_media_sha256"])
        self.assertEqual((sha(red),sha(blue)),original)
        self.assertEqual(len(list(master.parent.glob("*_normalized.mp4"))),2)
        self.assertTrue((master.parent/"qa_report.json").is_file())
        with self.assertRaises(EpisodeAssemblyError):
            engine.execute(run_id="pilot-m17-ffmpeg")

    def test_real_ffprobe_blocks_synthetic_video_without_audio(self):
        clip=self._clip("silent","red",440,audio=False)
        self._make_recipe([clip])
        with self.assertRaises(EpisodeAssemblyError):
            EpisodeAssembler(self.recipe_file).preflight()
        self.assertFalse((self.private/"rendered").exists())

    def test_real_media_executor_emits_sha_verified_pending_qa_receipt(self):
        clip=self._clip("scene_red","red",440)
        recipe=self._make_recipe([clip])
        catalogue_file=self.private/"catalogue.json"
        catalogue_file.write_text(json.dumps({
            "schema_version":1,
            "recipes":{"single_scene_ci":{
                "kind":"episode_assemble",
                "output_root":recipe["output_root"],
                "inputs":{"episode_recipe":str(self.recipe_file)},
                "sha256":{"episode_recipe":sha(self.recipe_file)},
            }}
        }))
        recipes=MediaRecipes(catalogue_file)
        executor=MediaExecutor(recipes)
        identifier="a"*32
        result=executor.execute("episode_assemble","single_scene_ci",identifier)
        self.assertEqual(result["result_status"],"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW")
        self.assertEqual(result["artifact_type"],"mp4")
        self.assertEqual(result["publication_approved"],False)
        file=self.private/"rendered"/identifier/"episode_qa_master.mp4"
        self.assertTrue(file.is_file())
        self.assertEqual(result["artifact_sha256"],sha(file))
        self.assertGreater(result["artifact_bytes"],1000)
        with self.assertRaises(Exception):
            executor.execute("episode_assemble","single_scene_ci",identifier)


if __name__=="__main__":
    unittest.main()
