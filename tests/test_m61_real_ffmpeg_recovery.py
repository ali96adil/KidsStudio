"""Real FFmpeg integration for M61 renderer, isolated from Pi/M55 lineage.

Generates synthetic color + audio clips, exercises genuine FFmpeg montage
and complete M7 master decode. M55-M60 verification functions are mocked
ONLY to isolate this media test; their real checks have separate tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from kidsstudio.episode_assembly import _run,probe_video
from kidsstudio.recovery_render import (
    render_private_recovery_master,proof_manifest_sha
)

def sha(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "real FFmpeg/FFprobe required")
class M61RealFFmpegIntegration(unittest.TestCase):
    def test_recovered_scene_skips_reencode_but_final_master_full_decodes(self):
        with tempfile.TemporaryDirectory(prefix="kidsstudio-m61-ffmpeg-") as home:
            root=Path(home).resolve()
            output=root/"renders"
            output.mkdir()
            old="1"*32
            proposal="2"*32
            new_job="3"*32
            old_folder=output/old
            old_folder.mkdir()
            recovered=old_folder/"001_normalized.mp4"
            original=root/"original_scene_2.mp4"
            ffmpeg=shutil.which("ffmpeg")
            ffprobe=shutil.which("ffprobe")
            for target,color,size in (
                (recovered,"red","1280x720"),
                (original,"blue","384x384")):
                subprocess.run([
                    ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-y",
                    "-f","lavfi","-i",f"color=c={color}:s={size}:r=24:d=2.4",
                    "-f","lavfi","-i",
                    "sine=frequency=440:sample_rate=48000:duration=2.4",
                    "-map","0:v:0","-map","1:a:0",
                    "-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",
                    "-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
                    "-movflags","+faststart",str(target)
                ],check=True,stdout=subprocess.DEVNULL,
                  stderr=subprocess.PIPE,timeout=90)
            source_sha=sha(recovered)
            manifest={
                "proposal_id":proposal,"original_job_id":old,
                "derived_recipe_sha256":"c"*64,
                "original_script_sha256":"a"*64,
                "source_m58_contract_sha256":"b"*64,
                "recovered_candidates":1,"fallbacks":1,
                "scenes":[
                    {"scene":1,
                     "strategy":"REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"},
                    {"scene":2,
                     "strategy":"USE_ORIGINAL_APPROVED_LTX_SOURCE"},
                ],
            }
            manifest_dir=output/"_recovery_execution_manifests"
            manifest_dir.mkdir()
            manifest_file=manifest_dir/(proposal+".json")
            manifest_file.write_text(json.dumps(manifest))
            recipe={
                "private_root":str(root),"output_root":str(output),
                "tools":{"ffmpeg":ffmpeg,"ffprobe":ffprobe,
                         "face_python":"/usr/bin/python3",
                         "face_v06":"/not-needed-v06",
                         "face_v07":"/not-needed-v07"},
                "clips":[
                    {"video":str(recovered),"sha256":sha(recovered),
                     "face_cleanup":"none"},
                    {"video":str(original),"sha256":sha(original),
                     "face_cleanup":"none"},
                ],
            }
            def live():
                return {
                    "status":"M61_CURRENT_PRIVATE_RECOVERY_LEASE",
                    "job_id":new_job,"generation":1,
                    "proposal_id":proposal,"original_job_id":old,
                    "recipe_sha256":"c"*64,
                    "manifest_sha256":proof_manifest_sha(manifest),
                    "media_contract_sha256":"b"*64,
                    "script_sha256":"a"*64,
                    "render_started":False,
                    "public_release_authorized":False,
                }
            commands=[]
            def command(args,*,timeout=1800,abort_event=None):
                commands.append(args)
                return _run(args,timeout=timeout,abort_event=abort_event)
            checked={"recipe_sha256":"c"*64,
                     "manifest_file_sha256":sha(manifest_file)}
            with (patch("kidsstudio.recovery_render.verify_staged_m60_recovery",
                        return_value=checked),
                  patch("kidsstudio.recovery_render.prepare_private_recovery_recipe",
                        return_value=(recipe,manifest))):
                result=render_private_recovery_master(
                    object(),object(),original_job_id=old,
                    payload={},proposal_id=proposal,
                    job_id=new_job,generation=1,
                    lease_check=live,abort_event=threading.Event(),
                    runner=command,prober=probe_video)
            self.assertEqual(result["status"],
                             "M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW")
            self.assertIs(result["final_m7_full_decode_passed"],True)
            self.assertIs(result["publication_approved"],False)
            self.assertEqual(len(commands),2)
            self.assertTrue(commands[0][-1].endswith("002_normalized.mp4"))
            self.assertTrue(commands[1][-1].endswith("episode_qa_master.mp4"))
            first=output/new_job/"001_normalized.mp4"
            self.assertEqual(sha(first),source_sha)
            self.assertTrue((output/new_job/"episode_qa_master.mp4").exists())
            record=json.loads((output/new_job/"qa_report.json").read_text())
            self.assertEqual(record["status"],
                             "M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW")


if __name__=="__main__":
    unittest.main()
