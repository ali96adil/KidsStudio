import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.host_pair_report import (
    _read_private_report,
    compare_host_reports,
    main,
)


_COMMON = (
    "python_3_11_plus",
    "artifact_root_exists",
    "artifact_root_outside_git",
    "artifact_root_not_symlink",
    "artifact_root_no_symlink_components",
    "artifact_root_owned_by_user",
    "artifact_root_private",
    "free_space_threshold",
    "role_matches_os_machine",
)
_DB = (
    "database_exists",
    "database_outside_git",
    "database_no_symlink_components",
    "database_parent_private",
    "database_parent_owned_by_user",
    "database_regular_file",
    "database_private_permissions",
    "database_owned_by_user",
)


def host(role, *, with_db=False):
    pi = role == "pi-private-handoff"
    checks = {name: True for name in _COMMON}
    if pi:
        checks["raspberry_pi_model_confirmed"] = True
    if with_db:
        checks.update({name: True for name in _DB})
    return {
        "schema_version": 2,
        "role": role,
        "host_system": "Linux" if pi else "Darwin",
        "machine": "aarch64" if pi else "arm64",
        "checks": checks,
        "status": "SUPERVISED_TESTS_READY",
        "synthetic_review_pipeline": "OFFLINE_REVIEW_PIPELINE_PASS",
        "real_mac_pi_transfer_test": "NOT_RUN",
        "real_youtube_upload_test": "NOT_RUN",
        "production_approved": False,
        "publication_approved": False,
    }


class HostPairReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name) / "private"
        self.private.mkdir(mode=0o700)
        self.mac = host("mac-render")
        self.pi = host("pi-private-handoff")
        self.mac_path = self.private / "mac.json"
        self.pi_path = self.private / "pi.json"

    def save(self):
        self.mac_path.write_text(json.dumps(self.mac), encoding="utf-8")
        self.pi_path.write_text(json.dumps(self.pi), encoding="utf-8")
        self.mac_path.chmod(0o600)
        self.pi_path.chmod(0o600)

    def test_happy_path_reports_still_unverified(self):
        result = compare_host_reports(self.mac, self.pi)
        self.assertEqual(result["status"], "OFFLINE_REPORT_PAIR_CONSISTENT_UNVERIFIED")
        self.assertFalse(result["source_reports_authenticated"])
        self.assertFalse(result["same_code_revision_proven"])
        self.assertFalse(result["production_approved"])
        self.assertFalse(result["publication_approved"])

    def test_database_check_group_supported(self):
        result = compare_host_reports(host("mac-render", with_db=True),
                                      host("pi-private-handoff", with_db=True))
        self.assertEqual(result["mac_issues"], [])
        self.assertEqual(result["pi_issues"], [])

    def test_wrong_role_rejected(self):
        result = compare_host_reports(self.pi, self.mac)
        self.assertEqual(result["status"], "OFFLINE_REPORT_PAIR_BLOCKED")
        self.assertIn("incorrect_role", result["mac_issues"])

    def test_missing_required_check_rejected(self):
        self.mac["checks"].pop("artifact_root_private")
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("required_checks_missing", result["mac_issues"])

    def test_false_check_rejected_even_if_status_says_ready(self):
        self.pi["checks"]["raspberry_pi_model_confirmed"] = False
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("checks_not_all_true_booleans", result["pi_issues"])

    def test_string_boolean_rejected(self):
        self.mac["checks"]["artifact_root_private"] = "true"
        result = compare_host_reports(self.mac, self.pi)
        self.assertEqual(result["status"], "OFFLINE_REPORT_PAIR_BLOCKED")

    def test_missing_database_subcheck_rejected(self):
        self.mac["checks"]["database_exists"] = True
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("incomplete_database_checks", result["mac_issues"])

    def test_unexpected_publication_approval_rejected(self):
        self.mac["publication_approved"] = True
        self.assertIn("publication_approved_must_be_false",
                      compare_host_reports(self.mac, self.pi)["mac_issues"])

    def test_unexpected_transfer_claim_rejected(self):
        self.pi["real_mac_pi_transfer_test"] = "PASS"
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("real_mac_pi_transfer_test_unexpected", result["pi_issues"])

    def test_wrong_schema_rejected(self):
        self.mac["schema_version"] = 1
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("incompatible_schema", result["mac_issues"])

    def test_invalid_mac_hardware_rejected(self):
        self.mac["machine"] = "aarch64"
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("host_platform_mismatch", result["mac_issues"])

    def test_malformed_machine_array_fails_closed(self):
        self.mac["machine"] = ["arm64"]
        result = compare_host_reports(self.mac, self.pi)
        self.assertIn("host_platform_mismatch", result["mac_issues"])

    def test_cli_malformed_json_rejected_without_contents(self):
        self.save()
        self.pi_path.write_text('{"machine":', encoding="utf-8")
        self.pi_path.chmod(0o600)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--mac-report", str(self.mac_path),
                         "--pi-report", str(self.pi_path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "OFFLINE_REPORT_PAIR_ERROR")

    def test_missing_input_rejected(self):
        result = compare_host_reports(None, self.pi)
        self.assertIn("invalid_report_object", result["mac_issues"])

    def test_cli_private_files_and_digests(self):
        self.save()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--mac-report", str(self.mac_path),
                         "--pi-report", str(self.pi_path)])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["mac_report_sha256"]), 64)
        self.assertNotIn(str(self.private), output.getvalue())
        self.assertFalse(result["production_approved"])

    def test_cli_public_file_permission_rejected(self):
        self.save()
        self.mac_path.chmod(0o644)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--mac-report", str(self.mac_path),
                         "--pi-report", str(self.pi_path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "OFFLINE_REPORT_PAIR_ERROR")

    def test_cli_symlink_rejected(self):
        self.save()
        link = self.private / "linked.json"
        link.symlink_to(self.mac_path)
        with self.assertRaises(ValueError):
            _read_private_report(str(link))

    def test_cli_public_parent_rejected(self):
        self.save()
        self.private.chmod(0o755)
        with self.assertRaises(ValueError):
            _read_private_report(str(self.mac_path))

    def test_cli_oversized_report_rejected(self):
        self.save()
        self.mac_path.write_bytes(b" " * 65537)
        self.mac_path.chmod(0o600)
        with self.assertRaises(ValueError):
            _read_private_report(str(self.mac_path))


if __name__ == "__main__":
    unittest.main()
