"""M54 safe local subprocess cancellation, quarantine, and exact run IDs.

Tests use synthetic files/Python sleeps only; no real owner media, GPU, AI
models, TLS server, account, publication or external network.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from kidsstudio.episode_assembly import (
    EpisodeAssembler, EpisodeAssemblyError, _run
)


def sha(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


class M54AbortTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="kidsstudio-m54-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()

    def test_m54_revoked_lease_terminates_running_subprocess(self):
        marker=self.root/"partial.txt"
        cancel=threading.Event()
        result=[]
        command=[sys.executable,"-c",
                 "from pathlib import Path; import sys,time; "
                 "Path(sys.argv[1]).write_text('partial preserved');"
                 "time.sleep(15)",str(marker)]
        def process():
            try:
                _run(command,timeout=6,abort_event=cancel)
            except EpisodeAssemblyError as exc:
                result.append(str(exc))
        thread=threading.Thread(target=process,daemon=True)
        thread.start()
        deadline=time.monotonic()+4
        while not marker.exists() and time.monotonic()<deadline:
            time.sleep(0.02)
        self.assertTrue(marker.exists(),"Synthetic subprocess never started")
        cancel.set()
        thread.join(timeout=4)
        self.assertFalse(thread.is_alive(),"Subprocess not interrupted promptly")
        self.assertEqual(marker.read_text(),"partial preserved")
        self.assertEqual(len(result),1)
        self.assertIn("lease lost",result[0].lower())

    def test_m54_abort_after_first_scene_keeps_private_failed_manifest(self):
        script=self.root/"script.txt"
        script.write_text("Synthetic episode")
        video=self.root/"scene.mp4"
        video.write_bytes(b"synthetic protected source video")
        tool=self.root/"face.py"
        tool.write_text("# fake face tool, never executed\n")
        recipe={
            "schema_version":1,"series_id":"colors-ar","episode_number":1,
            "private_root":str(self.root),
            "output_root":str(self.root/"renders"),
            "voice_rights":"INTERNAL_TEST_ONLY",
            "script":{"path":str(script),"sha256":sha(script)},
            "tools":{"ffmpeg":sys.executable,"ffprobe":sys.executable,
                     "face_python":sys.executable,
                     "face_v06":str(tool),"face_v06_sha256":sha(tool),
                     "face_v07":str(tool),"face_v07_sha256":sha(tool)},
            "clips":[{"video":str(video),"sha256":sha(video),
                      "face_cleanup":"none"}]
        }
        recipe_path=self.root/"recipe.json"
        recipe_path.write_text(json.dumps(recipe))
        cancel=threading.Event()
        calls=[]
        def fake_runner(args,*,timeout=1200):
            calls.append(args)
            Path(args[-1]).write_bytes(b"private partial mp4: test only")
            cancel.set()
        def fake_prober(path,executable):
            return {"width":384,"height":384,"duration":1.5,"audio_streams":1}
        assembler=EpisodeAssembler(recipe_path,runner=fake_runner,
                                   prober=fake_prober)
        run_id="0"*32  # Actual queue UUID may begin with a digit.
        with self.assertRaisesRegex(EpisodeAssemblyError,"lease lost"):
            assembler.execute(run_id=run_id,abort_event=cancel)
        self.assertEqual(len(calls),1)
        report_path=self.root/"renders"/run_id/"qa_report.json"
        self.assertTrue(report_path.is_file())
        report=json.loads(report_path.read_text())
        self.assertEqual(report["status"],
                         "FAILED_REQUIRES_MANUAL_RECONCILIATION")
        self.assertFalse(report.get("publication_approved"))
        self.assertFalse((self.root/"renders"/run_id/
                          "episode_qa_master.mp4").exists())
        self.assertTrue((self.root/"renders"/run_id/
                         "001_normalized.mp4").is_file())
        self.assertEqual(sha(video),recipe["clips"][0]["sha256"])
        with self.assertRaises(EpisodeAssemblyError):
            assembler.execute(run_id=run_id,abort_event=threading.Event())


if __name__=="__main__":
    unittest.main()
