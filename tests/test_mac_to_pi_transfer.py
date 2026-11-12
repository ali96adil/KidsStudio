from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shlex
import tempfile
import types
import unittest

from kidsstudio.mac_to_pi_transfer import (
    MacPiTransferError, main, make_transfer_plan, transfer_private_video,
)
from kidsstudio.optional_tool_evidence import ToolEvidenceError
from kidsstudio.pi_transfer_receive import receive_private_video


class MockSSHRunner:
    """Mock SSH process: receiver executes locally with the same stdin bytes."""
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.force_failure = False
        self.bad_receipt = False
        self.missing_privacy_receipt = False
        self.on_stream = None

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        self_key = argv[-1]
        remote_tokens = shlex.split(self_key)
        assert remote_tokens[:3] == [
            "python3", "-m", "kidsstudio.pi_transfer_receive",
        ]
        assert kwargs.get("stderr") is not None
        assert kwargs.get("check") is False
        assert kwargs.get("timeout", 0) > 0
        assert kwargs["stdin"].readable()
        if self.force_failure:
            return types.SimpleNamespace(returncode=255)
        filename = remote_tokens[remote_tokens.index("--destination-name") + 1]
        sha = remote_tokens[remote_tokens.index("--expected-sha256") + 1]
        size = int(remote_tokens[remote_tokens.index("--expected-bytes") + 1])
        result = receive_private_video(
            destination_root=self.root, destination_name=filename,
            expected_sha256=sha, expected_bytes=size,
            source=kwargs["stdin"])
        if self.on_stream:
            self.on_stream()
        if self.bad_receipt:
            result["sha256"] = "0" * 64
        if self.missing_privacy_receipt:
            result.pop("private_inbox_verified_at_receive", None)
        kwargs["stdout"].write(json.dumps(result).encode("utf-8"))
        return types.SimpleNamespace(returncode=0)


class MacToPiTransferTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.mac = self.root / "mac"
        self.pi = self.root / "pi"
        self.mac.mkdir(mode=0o700)
        self.pi.mkdir(mode=0o700)
        self.video = self.mac / "episode.mp4"
        self.content = b"synthetic Mac rig episode 1280x720" * 8000
        self.video.write_bytes(self.content)
        self.video.chmod(0o600)
        self.sha = hashlib.sha256(self.content).hexdigest()
        self.runner = MockSSHRunner(self.pi)

    def transfer(self, **updates):
        args = dict(
            video_root=str(self.mac), relative_path=self.video.name,
            expected_sha256=self.sha, destination_name="colors_ar_001.mp4",
            pi_host="pi.local", pi_user="pi", ssh_port=22,
            remote_python="python3", runner=self.runner,
        )
        args.update(updates)
        return transfer_private_video(**args)

    def test_default_preview_has_no_remote_execution(self):
        report = self.transfer()
        self.assertEqual(report["status"], "MAC_PI_TRANSFER_PREVIEW_ONLY")
        self.assertEqual(report["sha256"], self.sha)
        self.assertFalse(report["ssh_connection_performed"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(list(self.pi.iterdir()), [])

    def test_private_episode_attempt_candidate_is_not_transferable(self):
        attempt = self.mac / "colors_ar_01-pilot-sources-0123456789abcdef"
        attempt.mkdir(mode=0o700)
        candidate = attempt / "verified-candidate.mp4"
        candidate.write_bytes(b"candidate awaiting final audio gate")
        candidate.chmod(0o600)
        root_candidate = self.mac / candidate.name
        root_candidate.write_bytes(candidate.read_bytes())
        root_candidate.chmod(0o600)
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        for path in (
            attempt.name + "/" + candidate.name,
            attempt.name + "\\" + candidate.name,
            candidate.name,
        ):
            with self.subTest(path=path), self.assertRaises(MacPiTransferError):
                make_transfer_plan(
                    video_root=str(self.mac), relative_path=path,
                    expected_sha256=digest, destination_name="candidate.mp4",
                    pi_host="pi.local", pi_user="pi")
        self.assertEqual(self.runner.calls, [])

    def test_real_stream_mocked_receiver_and_ssh_host_checks(self):
        report = self.transfer(execute=True)
        self.assertEqual(report["status"], "MAC_PI_PRIVATE_TRANSFER_VERIFIED")
        self.assertEqual(report["sha256"], self.sha)
        self.assertFalse(report["youtube_upload_submitted"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual((self.pi / "colors_ar_001.mp4").read_bytes(), self.content)
        self.assertEqual(len(self.runner.calls), 1)
        argv, options = self.runner.calls[0]
        self.assertEqual(argv[0:2], ["ssh", "-T"])
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("ClearAllForwardings=yes", argv)
        self.assertEqual(argv[-2], "pi@pi.local")
        self.assertEqual(argv[-1].count("--expected-sha256"), 1)
        self.assertNotIn(str(self.mac), argv[-1])

    def test_identical_resend_receipt_is_idempotent(self):
        self.transfer(execute=True)
        first_inode = (self.pi / "colors_ar_001.mp4").stat().st_ino
        report = self.transfer(execute=True)
        self.assertEqual(report["pi_receiver_status"], "PI_INBOX_ALREADY_VERIFIED")
        self.assertEqual((self.pi / "colors_ar_001.mp4").stat().st_ino, first_inode)

    def test_existing_different_destination_never_overwritten(self):
        stored = self.pi / "colors_ar_001.mp4"
        stored.write_bytes(b"not the same episode")
        stored.chmod(0o600)
        with self.assertRaises(Exception):
            self.transfer(execute=True)
        self.assertEqual(stored.read_bytes(), b"not the same episode")

    def test_wrong_sha_stops_before_ssh(self):
        with self.assertRaises(MacPiTransferError):
            self.transfer(execute=True, expected_sha256="0" * 64)
        self.assertEqual(self.runner.calls, [])

    def test_changed_source_after_remote_receive_blocks_claim(self):
        def mutate():
            self.video.write_bytes(b"modified while sending")
        self.runner.on_stream = mutate
        with self.assertRaises(MacPiTransferError):
            self.transfer(execute=True)

    def test_bad_remote_receipt_rejected(self):
        self.runner.bad_receipt = True
        with self.assertRaises(MacPiTransferError):
            self.transfer(execute=True)

    def test_missing_private_receiver_assertion_rejected(self):
        self.runner.missing_privacy_receipt = True
        with self.assertRaises(MacPiTransferError):
            self.transfer(execute=True)

    def test_nonzero_ssh_exit_blocks(self):
        self.runner.force_failure = True
        with self.assertRaises(MacPiTransferError):
            self.transfer(execute=True)

    def test_unsafe_ssh_hosts_and_users_rejected_without_exec(self):
        for host, user in (
            ("-oProxyCommand=evil", "pi"), ("pi;touch/tmp/evil", "pi"),
            ("pi@otherhost", "pi"), ("host..local", "pi"),
            ("pi.local", "pi user"), ("pi.local", "pi;echo"),
            ("pi.local", "-baduser"),
        ):
            with self.subTest(host=host, user=user):
                with self.assertRaises(MacPiTransferError):
                    self.transfer(execute=True, pi_host=host, pi_user=user)
        self.assertEqual(self.runner.calls, [])

    def test_unsafe_remote_python_rejected(self):
        for value in ("python3;echo", "../python3", "~/venv/bin/python",
                      "/bin/../python3", "python3 -c evil"):
            with self.subTest(remote=value), self.assertRaises(MacPiTransferError):
                self.transfer(remote_python=value, execute=True)
        self.assertEqual(self.runner.calls, [])

    def test_invalid_ssh_port_and_timeout_rejected(self):
        for port in (0, 65536, True):
            with self.assertRaises(MacPiTransferError):
                self.transfer(ssh_port=port, execute=True)
        for timeout in (0, 8000, True):
            with self.assertRaises(MacPiTransferError):
                self.transfer(timeout_seconds=timeout, execute=True)

    def test_symlink_and_public_source_rejected(self):
        self.video.chmod(0o644)
        with self.assertRaises(ToolEvidenceError):
            self.transfer(execute=True)
        self.video.chmod(0o600)
        link = self.mac / "linked.mp4"
        link.symlink_to(self.video)
        with self.assertRaises(ToolEvidenceError):
            self.transfer(relative_path="linked.mp4", execute=True)

    def test_cli_without_execute_flag_is_safe(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main([
                "--video-root", str(self.mac),
                "--relative-path", "episode.mp4",
                "--expected-sha256", self.sha,
                "--destination-name", "colors_ar_001.mp4",
                "--pi-host", "pi.local", "--pi-user", "pi",
            ])
        self.assertEqual(status, 1)
        data = json.loads(output.getvalue())
        self.assertEqual(data["status"], "MAC_PI_TRANSFER_PREVIEW_ONLY")
        self.assertFalse(data["ssh_connection_performed"])
        self.assertNotIn(str(self.mac), output.getvalue())


if __name__ == "__main__":
    unittest.main()
