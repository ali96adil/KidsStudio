"""M8 shared compute reservation and real-run checkpoint qualification tests."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from kidsstudio.resource_gate import cooperative_compute_lock, ResourceGateError
from kidsstudio.voice_animation_stage import StagePlan
from kidsstudio.engine_qualification import EngineQualificationError


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ComputeReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()

    def test_single_compute_root_cannot_be_reserved_twice(self):
        lock=self.root/".kidsstudio_compute.lock"
        with cooperative_compute_lock(self.root):
            fd=os.open(str(lock),os.O_WRONLY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:
                os.close(fd)
        # A clean exit releases the resource reservation.
        with cooperative_compute_lock(self.root):
            self.assertTrue(lock.is_file())

    def test_symlinked_lock_rejected(self):
        target=self.root/"different"
        target.write_text("not a lock")
        (self.root/".kidsstudio_compute.lock").symlink_to(target)
        with self.assertRaises(ResourceGateError):
            with cooperative_compute_lock(self.root):
                pass


class RealRunnerQualificationTests(ComputeReservationTests):
    def test_default_execution_rejects_unqualified_models_before_adapter(self):
        script=self.root/"approved.txt";script.write_text("red")
        entry=self.root/"adapter.py"
        entry.write_text("raise RuntimeError('NEVER EXECUTED BY THIS TEST')\n")
        manifest=self.root/"engine.json"
        # The model manifest is pinned, but not yet qualified. It must NOT
        # authorize running any local Python adapter.
        manifest.write_text('{"unqualified":"no weights"}')
        plan=self.root/"stage.json"
        data={
            "schema_version":1,"kind":"voice_synthesize",
            "private_root":str(self.root),
            "output_root":str(self.root/"output"),
            "script":{"path":str(script),"sha256":sha(script)},
            "inputs":{"script":{"path":str(script),"sha256":sha(script)}},
            "runner":{
                "python":sys.executable,"python_sha256":sha(Path(sys.executable)),
                "entrypoint":str(entry),"entrypoint_sha256":sha(entry),
                "args":["--script","{script}","--engine","{engine_manifest}",
                        "--output","{output}"]
            },
            "engine_manifest":{"path":str(manifest),"sha256":sha(manifest)},
            "voice_rights":"INTERNAL_TEST_ONLY",
            "limits":{"timeout_seconds":60,"max_output_bytes":1_000_000},
            "ffprobe":sys.executable
        }
        plan.write_text(json.dumps(data))
        real=StagePlan(plan)
        with self.assertRaises(EngineQualificationError):
            real.run("f"*32)
        self.assertFalse((self.root/"output").exists())
        self.assertEqual(script.read_text(),"red")


if __name__=="__main__":
    unittest.main()
