"""Exercise the Bash launcher contract with stubbed Mac and media commands."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(shutil.which("bash"), "Bash launcher requires Bash")
class MacColorsLauncherTests(unittest.TestCase):
    def run_launcher(self, *, preflight_source="a" * 40):
        launcher = Path(__file__).resolve().parents[1] / "scripts" / "run_mac_colors_pilot.sh"
        digest = hashlib.sha256(b"original encoder output").hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            stubs = {"ffmpeg": "exit 0", "ffprobe": "exit 0", "say": "exit 0",
                     "uname": "echo Darwin", "git": 'echo "$TEST_SOURCE_SHA"'}
            for name, command in stubs.items():
                stub = home / name
                stub.write_text(f"#!/bin/sh\n{command}\n")
                stub.chmod(0o700)
            python = home / "python-stub"
            python.write_text("""#!/bin/sh
exec "$TEST_PYTHON" "$HOME/commands.py" "$@"
""")
            python.chmod(0o700)
            (home / "commands.py").write_text("""import json, os, pathlib, sys
args = sys.argv[1:]
if args[0] == "-c":
    sys.argv = [args[0], *args[2:]]
    exec(args[1])
    sys.exit()
if args[1] == "kidsstudio.mac_colors_preflight":
    print(json.dumps({"status": "MAC_COLORS_PREFLIGHT_READY",
                      "source_commit": os.environ["TEST_PREFLIGHT_SOURCE"]}))
if args[1] == "kidsstudio.first_colors_episode":
    if "--execute" not in args:
        print("COLORS_EPISODE_PREVIEW_ONLY")
        sys.exit(1)
    root = pathlib.Path(args[args.index("--output-root") + 1])
    name = args[args.index("--output-name") + 1]
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(b"replacement file")
    print(json.dumps({"status": "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED",
                      "final_mp4_sha256": os.environ["TEST_MOVIE_SHA"]}))
if args[1] == "kidsstudio.mp4_playback_preflight":
    print("QA_EXPECTED_SHA=" + args[args.index("--expected-sha256") + 1])
    sys.exit(2)
if args[1] == "kidsstudio.mac_pilot_evidence" and "collect" in args:
    print("EVIDENCE_CALLED")
""")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith("KIDSSTUDIO_")}
            env.update(HOME=str(home),
                       PATH=str(home) + os.pathsep + os.environ["PATH"],
                       TEST_PYTHON=sys.executable, TEST_MOVIE_SHA=digest,
                       TEST_SOURCE_SHA="a" * 40, TEST_PREFLIGHT_SOURCE=preflight_source,
                       KIDSSTUDIO_PYTHON=str(python), KIDSSTUDIO_SKIP_OPEN="1")
            result = subprocess.run(
                ["bash", str(launcher)], capture_output=True, text=True,
                timeout=15, env=env)
        return result, digest

    def test_qa_receives_encoder_digest_even_if_output_is_replaced(self):
        result, digest = self.run_launcher()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(f"QA_EXPECTED_SHA={digest}\n", result.stdout)
        self.assertNotIn("EVIDENCE_CALLED", result.stdout)

    def test_changed_source_after_preflight_blocks_render(self):
        result, _ = self.run_launcher(preflight_source="b" * 40)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Source commit changed before render.", result.stdout)
        self.assertNotIn("Step 2/4", result.stdout)
