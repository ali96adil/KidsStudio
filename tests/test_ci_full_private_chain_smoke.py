"""Unit guards for the explicitly simulated full private CI pipeline."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.ci_full_private_chain_smoke import (
    OfflineFakeYouTube, OfflineMockSSH,
    check_offline_full_private_chain,
)


class OfflineFullPrivateChainGuardTests(unittest.TestCase):
    def test_mock_google_requires_private_kids_only_metadata(self):
        fake = OfflineFakeYouTube()
        valid = {"status": {"privacyStatus": "private",
                            "selfDeclaredMadeForKids": True}}
        session = fake.start(
            token="CI_ONLY_ACCESS_TOKEN_123456789",
            metadata=valid, size=31)
        self.assertIn("upload_id=CI_ONLY", session)
        self.assertEqual(fake.total, 31)

    def test_mock_google_rejects_public_and_scheduled_uploads(self):
        for metadata in (
            {"status": {"privacyStatus": "public",
                        "selfDeclaredMadeForKids": True}},
            {"status": {"privacyStatus": "unlisted",
                        "selfDeclaredMadeForKids": True}},
            {"status": {"privacyStatus": "private",
                        "selfDeclaredMadeForKids": False}},
            {"status": {"privacyStatus": "private",
                        "selfDeclaredMadeForKids": True,
                        "publishAt": "2026-11-10T09:00:00Z"}},
        ):
            with self.subTest(metadata=metadata), self.assertRaises(AssertionError):
                OfflineFakeYouTube().start(
                    token="CI_ONLY_ACCESS_TOKEN_123456789",
                    metadata=metadata, size=31)

    def test_fake_google_rejects_missing_or_different_token(self):
        with self.assertRaises(AssertionError):
            OfflineFakeYouTube().start(
                token="ACTUAL_NOT_A_CI_TOKEN",
                metadata={"status": {"privacyStatus": "private",
                                     "selfDeclaredMadeForKids": True}},
                size=31)

    def test_mock_google_strict_chunk_positions(self):
        fake = OfflineFakeYouTube()
        fake.start(
            token="CI_ONLY_ACCESS_TOKEN_123456789",
            metadata={"status": {"privacyStatus": "private",
                                 "selfDeclaredMadeForKids": True}}, size=10)
        with self.assertRaises(AssertionError):
            fake.send_chunk(session="wrong", token="any",
                            data=b"x", start=0, total=10)
        with self.assertRaises(AssertionError):
            fake.send_chunk(
                session=fake.start(
                    token="CI_ONLY_ACCESS_TOKEN_123456789",
                    metadata={"status": {"privacyStatus": "private",
                                         "selfDeclaredMadeForKids": True}},
                    size=10),
                token="any", data=b"x", start=3, total=10)

    def test_ci_full_chain_rejects_outside_private_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            other = Path(tmp) / "other"
            base.mkdir()
            other.mkdir()
            with self.assertRaises(ValueError):
                check_offline_full_private_chain(
                    base=base, ready=other, video_name="test.mp4",
                    expected_sha256="a" * 64)
            self.assertEqual(list(base.iterdir()), [])

    def test_local_mock_ssh_never_launches_real_ssh_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = OfflineMockSSH(Path(tmp))
            with self.assertRaises(AssertionError):
                fake(["ssh", "-o", "StrictHostKeyChecking=no"], check=False)
            self.assertEqual(fake.calls, 0)


if __name__ == "__main__":
    unittest.main()
