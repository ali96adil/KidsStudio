"""Tests for idempotent M67 Pi transfer and safe interrupted copy."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m67_pi_transfer_resume import transfer_resumable, ResumeError


class FakeRunner:
    def __init__(self, digest, *, final_exists=False, partial_exists=False):
        self.digest = digest
        self.final_exists = final_exists
        self.partial_exists = partial_exists
        self.copied = 0

    def __call__(self, args, **kwargs):
        if args[0] == "scp":
            self.copied += 1
            self.partial_exists = True
            return SimpleNamespace(returncode=0, stdout="")
        command = args[args.index("pi@pi.local") + 1:]
        if command[:2] == ["test", "-d"]:
            code = 0
        elif command[:2] == ["test", "-f"]:
            code = 0 if self.final_exists else 1
        elif command[:2] == ["test", "-e"]:
            code = 0 if self.partial_exists else 1
        elif command[0] == "sha256sum":
            return SimpleNamespace(returncode=0, stdout=self.digest + "  file")
        elif command[:2] == ["mv", "-n"]:
            self.final_exists = True
            self.partial_exists = False
            code = 0
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=code, stdout="")


class TransferResumeTests(unittest.TestCase):
    def fixture(self, root):
        master = root / "master.mp4"
        master.write_bytes(b"transfer fixture")
        return inventory(root, master=master, episode_id="colors-ar-001")

    def test_existing_verified_file_skips_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.fixture(root)
            fake = FakeRunner(manifest["master"]["sha256"], final_exists=True)
            result = transfer_resumable(root, manifest, host="pi.local",
                        user="pi", remote_dir="/srv/inbox", runner=fake)
            self.assertEqual(result["status"], "ALREADY_TRANSFERRED_HASH_VERIFIED")
            self.assertEqual(fake.copied, 0)

    def test_partial_blocks_unsafe_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.fixture(root)
            fake = FakeRunner(manifest["master"]["sha256"], partial_exists=True)
            with self.assertRaises(ResumeError):
                transfer_resumable(root, manifest, host="pi.local",
                    user="pi", remote_dir="/srv/inbox", runner=fake)
            self.assertEqual(fake.copied, 0)

    def test_first_transfer_verifies_both_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.fixture(root)
            fake = FakeRunner(manifest["master"]["sha256"])
            result = transfer_resumable(root, manifest, host="pi.local",
                        user="pi", remote_dir="/srv/inbox", runner=fake)
            self.assertEqual(result["status"], "TRANSFERRED_TO_PI_HASH_VERIFIED")
            self.assertEqual(fake.copied, 1)
