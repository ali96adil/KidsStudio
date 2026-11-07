from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.host_qualification import qualify_host


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

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValueError):
            qualify_host(role="youtube-public", artifact_root=str(self.root),
                         min_free_gib=0)


if __name__ == "__main__":
    unittest.main()
