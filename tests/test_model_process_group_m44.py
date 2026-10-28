"""M44 process tree cleanup with real POSIX child/grandchild processes.

Synthetic scripts only, no ML, no Pi, no upload.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from kidsstudio.model_process_group import bounded_model_process, ModelProcessError


@unittest.skipUnless(os.name=="posix","POSIX process-group isolation required")
class ModelProcessGroup44(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="kidsstudio-m44-proc-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),
                  "HOME":str(self.root),"LANG":"C"}
        self.started=self.root/"grandchild_started.txt"
        self.done=self.root/"grandchild_survived.txt"
        self.runner=self.root/"model_launcher"
        child=(
            "from pathlib import Path\\n"
            f"Path({str(self.started)!r}).write_text('started')\\n"
            "import time;time.sleep(1.5)\\n"
            f"Path({str(self.done)!r}).write_text('orphan')\\n"
        )
        parent=(
            f"#!{sys.executable}\\n"
            "import subprocess,sys,time\\n"
            f"subprocess.Popen([sys.executable,'-c',{child!r}],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
            "stderr=subprocess.DEVNULL)\\n"
            "time.sleep(5)\\n"
        )
        self.runner.write_text(parent)
        self.runner.chmod(0o700)

    def launch(self,seconds=1):
        return bounded_model_process([str(self.runner)],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=seconds,
            env=self.env,check=False)

    def test_timeout_kills_worker_and_child_process_group(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.launch(seconds=1)
        time.sleep(1)
        self.assertTrue(self.started.exists(), "Child process did not start.")
        self.assertFalse(self.done.exists(),
                         "Detached GPU child continued after runner timeout.")

    def test_success_parent_exit_still_kills_leftover_descendants(self):
        script=self.runner.read_text()
        self.runner.write_text(script.replace("time.sleep(5)\n",
                                             "time.sleep(0.3)\n"))
        result=self.launch(seconds=3)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout,b"")
        self.assertEqual(result.stderr,b"")
        time.sleep(1.7)
        self.assertTrue(self.started.exists(), "Child process did not start.")
        self.assertFalse(self.done.exists(),
                         "Successful parent left active child model worker.")

    def test_credentials_and_unsafe_execution_protocol_refused(self):
        for env in (
            {**self.env,"KIDS_STUDIO_SCENE_QA_RUNNER_KEY":"secret"},
            {**self.env,"OPENAI_API_KEY":"not-allowed"},
            {**self.env,"GOOGLE_CLIENT_SECRET":"not-allowed"}):
            with self.assertRaises(ModelProcessError):
                bounded_model_process([str(self.runner)],
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,timeout=2,env=env,check=False)
        self.assertFalse(self.started.exists())
        with self.assertRaises(ModelProcessError):
            bounded_model_process(["/bin/echo","unsafe"],stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                timeout=0,env=self.env,check=False)


if __name__=="__main__":
    unittest.main()
