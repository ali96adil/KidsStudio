"""Unit tests for Mac immutable pilot evidence; no real Mac, SSH or upload."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.mac_pilot_evidence import (
    MacPilotEvidenceError, collect_mac_pilot_evidence,
    record_mac_pilot_review, main, prepare_launcher_dirs,
)

SHA = "a" * 40


class MacPilotEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.video_root = self.base / "videos"
        self.evidence_root = self.base / "evidence"
        self.video_root.mkdir(mode=0o700)
        self.evidence_root.mkdir(mode=0o700)
        self.video = self.video_root / "colors_ar_01_test.mp4"
        self.video.write_bytes(b"synthetic test bytes, not a real MP4")
        self.video.chmod(0o600)
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.evidence_name = "colors_ar_01_test.evidence.json"
        self.collect_args = dict(
            episode_id="colors_ar_01", video_root=str(self.video_root),
            video_name=self.video.name, expected_sha256=self.sha,
            evidence_root=str(self.evidence_root), evidence_name=self.evidence_name,
        )

    def test_launcher_creates_private_destinations_and_reuses_them(self):
        base = self.base / "kidsstudio-private"
        for _ in range(2):
            prepare_launcher_dirs(str(self.base))
            for directory in (base, base / "ready", base / "qualification"):
                self.assertTrue(directory.is_dir())
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_launcher_rejects_symlinked_qualification_before_making_ready(self):
        base = self.base / "kidsstudio-private"
        base.mkdir(mode=0o700)
        self.evidence_root.chmod(0o755)
        (base / "qualification").symlink_to(self.evidence_root, target_is_directory=True)
        with self.assertRaises(MacPilotEvidenceError):
            prepare_launcher_dirs(str(self.base))
        self.assertEqual(self.evidence_root.stat().st_mode & 0o777, 0o755)
        self.assertFalse((base / "ready").exists())

    def test_launcher_rejects_symlinked_parent_without_writing_to_target(self):
        base = self.base / "kidsstudio-private"
        base.symlink_to(self.evidence_root, target_is_directory=True)
        with self.assertRaises(MacPilotEvidenceError):
            prepare_launcher_dirs(str(self.base))
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_launcher_rejects_existing_nonprivate_dir_without_chmod(self):
        base = self.base / "kidsstudio-private"
        base.mkdir(mode=0o700)
        ready = base / "ready"
        ready.mkdir()
        ready.chmod(0o755)
        with self.assertRaises(MacPilotEvidenceError):
            prepare_launcher_dirs(str(self.base))
        self.assertEqual(ready.stat().st_mode & 0o777, 0o755)
        self.assertFalse((base / "qualification").exists())

    @staticmethod
    def host(*, clean=True, status="SUPERVISED_TESTS_READY", revision=SHA):
        return {
            "status": status, "host_system": "Darwin",
            "source_commit": revision, "source_checkout_clean": clean,
            "synthetic_review_pipeline": "OFFLINE_REVIEW_PIPELINE_PASS",
        }

    @staticmethod
    def playback():
        return {
            "status": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
            "video_bytes": len(b"synthetic test bytes, not a real MP4"),
            "duration_seconds": 24.0,
            "faststart_moov_before_mdat": True,
            "video_samples_decoded": 3,
            "audio_samples_decoded": 2,
        }

    def collect(self, *, host=None, playback=None, **overrides):
        with patch("kidsstudio.mac_pilot_evidence.platform.system",
                   return_value="Darwin"), patch(
                    "kidsstudio.mac_pilot_evidence.qualify_host",
                    return_value=self.host() if host is None else host) as host_probe, patch(
                    "kidsstudio.mac_pilot_evidence.inspect_mp4_playback",
                    return_value=self.playback() if playback is None else playback) as media_probe:
            out = collect_mac_pilot_evidence(**{**self.collect_args, **overrides})
        host_probe.assert_called_once()
        media_probe.assert_called_once()
        return out

    def review(self, *, outcome="REVISION_REQUIRED", notes="fix pronunciation",
               watched=False, listened=False):
        return record_mac_pilot_review(
            evidence_root=str(self.evidence_root),
            evidence_name=self.evidence_name,
            video_root=str(self.video_root), video_name=self.video.name,
            expected_sha256=self.sha, review_outcome=outcome,
            reviewer_notes=notes, reviewed_full_video=watched,
            reviewed_arabic_voice=listened)

    def test_collect_persists_private_immutable_sha_bound_metadata(self):
        result = self.collect(expected_source_commit=SHA)
        self.assertEqual(result["status"],
                         "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING")
        self.assertTrue(result["owner_review_pending"])
        evidence = self.evidence_root / self.evidence_name
        data = json.loads(evidence.read_text())
        self.assertEqual(evidence.stat().st_mode & 0o077, 0)
        self.assertEqual(data["source_commit"], SHA)
        self.assertEqual(data["video_sha256"], self.sha)
        self.assertEqual(data["video_samples_decoded"], 3)
        self.assertEqual(data["audio_samples_decoded"], 2)
        self.assertTrue(data["full_video_owner_review_pending"])
        self.assertFalse(data["actual_host_identity_authenticated"])
        self.assertFalse(data["publication_approved"])
        self.assertFalse(data["production_approved"])
        self.assertFalse(result["youtube_upload_performed"])
        self.assertNotIn(str(self.video_root), evidence.read_text())

    def test_non_mac_blocks_evidence(self):
        with patch("kidsstudio.mac_pilot_evidence.platform.system",
                   return_value="Linux"):
            with self.assertRaises(MacPilotEvidenceError):
                collect_mac_pilot_evidence(**self.collect_args)
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_internal_mux_candidate_cannot_receive_pilot_evidence(self):
        with self.assertRaises(MacPilotEvidenceError):
            self.collect(video_name="verified-candidate.mp4")
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_dirty_or_missing_source_blocks(self):
        for host in (self.host(clean=False),
                     self.host(revision=None),
                     self.host(revision="0" * 39),
                     self.host(status="SUPERVISED_TESTS_BLOCKED")):
            with self.subTest(host=host), self.assertRaises(MacPilotEvidenceError):
                self.collect(host=host)
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_clean_but_different_source_commit_blocks_sidecar(self):
        with self.assertRaisesRegex(MacPilotEvidenceError, "source commit changed"):
            self.collect(host=self.host(revision="b" * 40), expected_source_commit=SHA)
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_codec_gate_failure_does_not_persist(self):
        with self.assertRaises(MacPilotEvidenceError):
            self.collect(playback={"status": "MP4_PLAYBACK_PREFLIGHT_BLOCKED"})
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_same_evidence_filename_never_replaced(self):
        self.collect()
        original = (self.evidence_root / self.evidence_name).read_bytes()
        with self.assertRaises(FileExistsError):
            self.collect()
        self.assertEqual((self.evidence_root / self.evidence_name).read_bytes(),
                         original)

    def test_review_revision_required_records_distinct_private_file(self):
        self.collect()
        result = self.review(notes="الأحمر يحتاج إعادة")
        self.assertEqual(result["review_outcome"], "REVISION_REQUIRED")
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["reviewer_identity_authenticated"])
        name = result["review_evidence_name"]
        self.assertNotEqual(name, self.evidence_name)
        stored = self.evidence_root / name
        self.assertEqual(stored.stat().st_mode & 0o077, 0)
        data = json.loads(stored.read_text())
        self.assertEqual(data["reviewer_notes"], "الأحمر يحتاج إعادة")
        self.assertEqual(data["video_sha256"], self.sha)
        self.assertFalse(data["reported_full_video_reviewed"])
        self.assertFalse(data["publication_approved"])

    def test_private_acceptance_requires_full_video_and_voice_claims(self):
        self.collect()
        for watched, listened in ((False, False), (True, False), (False, True)):
            with self.subTest(watched=watched, listened=listened):
                with self.assertRaises(MacPilotEvidenceError):
                    self.review(outcome="ACCEPTED_PRIVATE", watched=watched,
                                listened=listened)
        self.assertEqual(len(list(self.evidence_root.iterdir())), 1)
        result = self.review(outcome="ACCEPTED_PRIVATE",
                             watched=True, listened=True, notes="sounds correct")
        self.assertEqual(result["review_outcome"], "ACCEPTED_PRIVATE")
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])
        report = json.loads((self.evidence_root /
                             result["review_evidence_name"]).read_text())
        self.assertTrue(report["reported_full_video_reviewed"])
        self.assertTrue(report["reported_arabic_voice_reviewed"])
        self.assertFalse(report["reviewer_identity_authenticated"])
        self.assertFalse(report["local_acceptance_is_upload_permission"])

    def test_video_changed_after_collect_blocks_review(self):
        self.collect()
        self.video.write_bytes(b"the file changed")
        with self.assertRaises(MacPilotEvidenceError):
            self.review()
        self.assertEqual(len(list(self.evidence_root.iterdir())), 1)

    def test_evidence_modified_or_wrong_hash_blocks_review(self):
        self.collect()
        path = self.evidence_root / self.evidence_name
        data = json.loads(path.read_text())
        data["video_sha256"] = "0" * 64
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        with self.assertRaises(MacPilotEvidenceError):
            self.review()

    def test_two_reviews_append_and_preserve_original(self):
        self.collect()
        initial = (self.evidence_root / self.evidence_name).read_bytes()
        first = self.review(notes="first")
        second = self.review(notes="second")
        self.assertNotEqual(first["review_evidence_name"],
                            second["review_evidence_name"])
        self.assertEqual((self.evidence_root / self.evidence_name).read_bytes(),
                         initial)
        self.assertEqual(len(list(self.evidence_root.iterdir())), 3)

    def test_review_without_evidence_fails_closed(self):
        with self.assertRaises((OSError, ValueError)):
            self.review()

    def test_public_evidence_dir_rejected(self):
        self.evidence_root.chmod(0o755)
        with self.assertRaises(MacPilotEvidenceError):
            self.collect()

    def test_evidence_symlink_rejected(self):
        self.collect()
        link = self.evidence_root / "linked.evidence.json"
        link.symlink_to(self.evidence_root / self.evidence_name)
        self.evidence_name = link.name
        with self.assertRaises(ValueError):
            self.review()

    def test_unsafe_name_rejected_without_any_writes(self):
        self.collect_args["evidence_name"] = "../escaped.json"
        with self.assertRaises(MacPilotEvidenceError):
            self.collect()
        self.assertEqual(list(self.evidence_root.iterdir()), [])

    def test_empty_or_too_long_review_notes_rejected(self):
        self.collect()
        with self.assertRaises(MacPilotEvidenceError):
            self.review(notes="n" * 2001)
        self.assertEqual(len(list(self.evidence_root.iterdir())), 1)

    def test_cli_blocked_redacts_paths_and_defaults_no_actions(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "review", "--evidence-root", str(self.evidence_root),
                "--evidence-name", self.evidence_name,
                "--video-root", str(self.video_root),
                "--video-name", self.video.name,
                "--expected-sha256", self.sha,
                "--review-outcome", "ACCEPTED_PRIVATE",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "MAC_PILOT_EVIDENCE_BLOCKED")
        self.assertNotIn(str(self.video_root), output.getvalue())

    def test_video_name_and_sha_validated_before_source_probe(self):
        self.collect_args["video_name"] = "../escape.mp4"
        with patch("kidsstudio.mac_pilot_evidence.qualify_host") as probe:
            with self.assertRaises(MacPilotEvidenceError):
                self.collect()
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
