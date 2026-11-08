from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kidsstudio.host_qualification import _source_checkout, qualify_host


class HostQualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)

    def test_mac_host_ready_for_supervised_tests(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness:
            readiness.return_value = {
                "ready_for_supervised_tests": True, "host_system": "Darwin",
                "machine": "arm64", "checks": {"artifact_root_private": True}}
            report = qualify_host(role="mac-render", artifact_root=str(self.root),
                                  min_free_gib=0)
        self.assertEqual(report["status"], "SUPERVISED_TESTS_READY")
        self.assertEqual(report["real_mac_pi_transfer_test"], "NOT_RUN")
        self.assertFalse(report["production_approved"])

    def test_pi_host_blocked_if_private_root_missing(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness:
            readiness.return_value = {
                "ready_for_supervised_tests": False, "host_system": "Linux",
                "machine": "aarch64", "checks": {"artifact_root_private": False}}
            report = qualify_host(role="pi-private-handoff", artifact_root=str(self.root),
                                  min_free_gib=0)
        self.assertEqual(report["status"], "SUPERVISED_TESTS_BLOCKED")
        self.assertFalse(report["publication_approved"])

    def test_linux_arm_machine_cannot_claim_mac_role(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness:
            readiness.return_value = {
                "ready_for_supervised_tests": True, "host_system": "Linux",
                "machine": "aarch64", "checks": {"artifact_root_private": True}}
            report = qualify_host(role="mac-render", artifact_root=str(self.root),
                                  min_free_gib=0)
        self.assertFalse(report["checks"]["role_matches_os_machine"])
        self.assertEqual(report["status"], "SUPERVISED_TESTS_BLOCKED")

    def test_non_pi_linux_arm_machine_blocked(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness, patch("kidsstudio.host_qualification._raspberry_pi_model_present",
                   return_value=False):
            readiness.return_value = {
                "ready_for_supervised_tests": True, "host_system": "Linux",
                "machine": "aarch64", "checks": {"artifact_root_private": True}}
            report = qualify_host(role="pi-private-handoff",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertFalse(report["checks"]["raspberry_pi_model_confirmed"])
        self.assertEqual(report["status"], "SUPERVISED_TESTS_BLOCKED")

    def test_pi_hardware_confirmed_but_not_production_approved(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness, patch("kidsstudio.host_qualification._raspberry_pi_model_present",
                   return_value=True):
            readiness.return_value = {
                "ready_for_supervised_tests": True, "host_system": "Linux",
                "machine": "aarch64", "checks": {"artifact_root_private": True}}
            report = qualify_host(role="pi-private-handoff",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertTrue(report["checks"]["raspberry_pi_model_confirmed"])
        self.assertEqual(report["status"], "SUPERVISED_TESTS_READY")
        self.assertFalse(report["production_approved"])
        self.assertEqual(report["real_mac_pi_transfer_test"], "NOT_RUN")

    def test_wrong_os_for_pi_role_rejected(self):
        with patch("kidsstudio.host_qualification.inspect_host") as readiness:
            readiness.return_value = {
                "ready_for_supervised_tests": True, "host_system": "Darwin",
                "machine": "arm64", "checks": {"artifact_root_private": True}}
            report = qualify_host(role="pi-private-handoff",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertFalse(report["checks"]["role_matches_os_machine"])
        self.assertEqual(report["status"], "SUPERVISED_TESTS_BLOCKED")

    def test_dirty_mac_checkout_is_not_ready_even_when_media_tests_pass(self):
        with patch("kidsstudio.host_qualification.inspect_host",
                   return_value={
                       "ready_for_supervised_tests": True,
                       "host_system": "Darwin", "machine": "arm64",
                       "checks": {"artifact_root_private": True},
                   }), patch("kidsstudio.host_qualification._source_checkout",
                             return_value=("a" * 40, False)), patch(
                                 "kidsstudio.host_qualification.run_review_pipeline_qualification",
                                 return_value={"status": "OFFLINE_REVIEW_PIPELINE_PASS"}):
            result = qualify_host(role="mac-render",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertEqual(result["status"], "SUPERVISED_TESTS_BLOCKED")
        self.assertTrue(result["checks"]["source_commit_sha40"])
        self.assertFalse(result["checks"]["source_checkout_clean"])

    def test_pi_missing_commit_blocks_even_with_true_hardware(self):
        with patch("kidsstudio.host_qualification.inspect_host",
                   return_value={
                       "ready_for_supervised_tests": True,
                       "host_system": "Linux", "machine": "aarch64",
                       "checks": {"artifact_root_private": True},
                   }), patch("kidsstudio.host_qualification._raspberry_pi_model_present",
                             return_value=True), patch(
                                 "kidsstudio.host_qualification._source_checkout",
                                 return_value=(None, False)), patch(
                                     "kidsstudio.host_qualification.run_review_pipeline_qualification",
                                     return_value={"status": "OFFLINE_REVIEW_PIPELINE_PASS"}):
            result = qualify_host(role="pi-private-handoff",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertEqual(result["status"], "SUPERVISED_TESTS_BLOCKED")
        self.assertFalse(result["checks"]["source_commit_sha40"])
        self.assertFalse(result["checks"]["source_checkout_clean"])

    def test_malformed_sha_blocks_even_if_git_claims_clean(self):
        with patch("kidsstudio.host_qualification.inspect_host",
                   return_value={
                       "ready_for_supervised_tests": True,
                       "host_system": "Darwin", "machine": "arm64",
                       "checks": {"artifact_root_private": True},
                   }), patch("kidsstudio.host_qualification._source_checkout",
                             return_value=("not-a-commit", True)), patch(
                                 "kidsstudio.host_qualification.run_review_pipeline_qualification",
                                 return_value={"status": "OFFLINE_REVIEW_PIPELINE_PASS"}):
            result = qualify_host(role="mac-render",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertEqual(result["status"], "SUPERVISED_TESTS_BLOCKED")
        self.assertFalse(result["checks"]["source_commit_sha40"])

    def test_clean_commit_is_necessary_but_not_production_approval(self):
        with patch("kidsstudio.host_qualification.inspect_host",
                   return_value={
                       "ready_for_supervised_tests": True,
                       "host_system": "Darwin", "machine": "arm64",
                       "checks": {"artifact_root_private": True},
                   }), patch("kidsstudio.host_qualification._source_checkout",
                             return_value=("a" * 40, True)), patch(
                                 "kidsstudio.host_qualification.run_review_pipeline_qualification",
                                 return_value={"status": "OFFLINE_REVIEW_PIPELINE_PASS"}):
            result = qualify_host(role="mac-render",
                                  artifact_root=str(self.root), min_free_gib=0)
        self.assertEqual(result["status"], "SUPERVISED_TESTS_READY")
        self.assertTrue(result["checks"]["source_commit_sha40"])
        self.assertTrue(result["checks"]["source_checkout_clean"])
        self.assertFalse(result["publication_approved"])

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValueError):
            qualify_host(role="youtube-public", artifact_root=str(self.root),
                         min_free_gib=0)


    def test_source_checkout_checks_entire_repo_including_scripts_and_untracked(self):
        checkout = Path(self.tmp.name) / "checkout"
        (checkout / ".git").mkdir(parents=True)
        source_path = checkout / "kidsstudio" / "host_qualification.py"
        source_path.parent.mkdir()
        seen = []

        def fake_git(args, **kwargs):
            seen.append(args)
            if "rev-parse" in args:
                return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n")
            self.assertIn("--porcelain=v1", args)
            self.assertIn("--untracked-files=all", args)
            self.assertNotIn("--", args)
            return SimpleNamespace(returncode=0, stdout="?? scripts/other.py\n")

        with patch("kidsstudio.host_qualification.__file__", str(source_path)), \
             patch("kidsstudio.host_qualification.subprocess.run",
                   side_effect=fake_git):
            revision, clean = _source_checkout()
        self.assertEqual(revision, "a" * 40)
        self.assertFalse(clean)
        self.assertEqual(len(seen), 2)
        self.assertIn("HEAD^{commit}", seen[0])

    def test_source_checkout_clean_only_if_complete_status_empty(self):
        checkout = Path(self.tmp.name) / "checkout_clean"
        (checkout / ".git").mkdir(parents=True)
        source_path = checkout / "kidsstudio" / "host_qualification.py"
        source_path.parent.mkdir()
        answers = [
            SimpleNamespace(returncode=0, stdout="b" * 40 + "\n"),
            SimpleNamespace(returncode=0, stdout=""),
        ]
        with patch("kidsstudio.host_qualification.__file__", str(source_path)), \
             patch("kidsstudio.host_qualification.subprocess.run",
                   side_effect=answers):
            self.assertEqual(_source_checkout(), ("b" * 40, True))

    def test_source_checkout_without_git_fails_closed(self):
        source_path = Path(self.tmp.name) / "nogit" / "kidsstudio" / "module.py"
        with patch("kidsstudio.host_qualification.__file__", str(source_path)), \
             patch("kidsstudio.host_qualification.subprocess.run") as git:
            self.assertEqual(_source_checkout(), (None, False))
        git.assert_not_called()

    def test_source_checkout_invalid_commit_or_failed_status_fails_closed(self):
        checkout = Path(self.tmp.name) / "checkout_bad"
        (checkout / ".git").mkdir(parents=True)
        source_path = checkout / "kidsstudio" / "host_qualification.py"
        source_path.parent.mkdir()
        for sha, code, expected in [
            ("not-a-sha", 0, (None, False)),
            ("c" * 40, 1, ("c" * 40, False)),
            ("c" * 40, 0, ("c" * 40, True)),
        ]:
            with self.subTest(sha=sha, code=code), patch(
                "kidsstudio.host_qualification.__file__", str(source_path)
            ), patch(
                "kidsstudio.host_qualification.subprocess.run",
                side_effect=[
                    SimpleNamespace(returncode=0, stdout=sha + "\n"),
                    SimpleNamespace(returncode=code, stdout=""),
                ],
            ):
                self.assertEqual(_source_checkout(), expected)


if __name__ == "__main__":
    unittest.main()
