"""M68 composite pipeline gate tests: no upload authorization is created."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_short_pipeline_gate import assess_pipeline


class PipelineGateTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "colors-short-01",
                        "master": {"sha256": "a" * 64}}
        self.kwargs = dict(handoff=self.handoff, transfer_receipt={},
                           registry_record={}, render_job_id="b" * 32,
                           master="master.mp4", plan="plan.json",
                           readiness="readiness.json")

    def run_gate(self):
        return assess_pipeline(None, "/pi/inbox", "/journal.sqlite",
                               **self.kwargs)

    def test_missing_receipts_stops_before_pi(self):
        with patch("kidsstudio.m68_short_pipeline_gate.assess_short_import",
                   return_value={"status": "M68_SHORT_M65_IMPORT_BLOCKED",
                                 "checks": {"m65_receipts_consistent": False}}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_pi") as pi:
            result = self.run_gate()
        pi.assert_not_called()
        self.assertEqual(result["status"], "SHORT_PIPELINE_BLOCKED_AT_RECEIPTS")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_pi_unapproved_stops_before_journal(self):
        with patch("kidsstudio.m68_short_pipeline_gate.assess_short_import",
                   return_value={"status": "M68_SHORT_READY_FOR_M65_POLICY_VERIFICATION",
                                 "checks": {}}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_pi",
                return_value={"status": "SHORT_NOT_ACCEPTED_BY_M65"}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_short_upload") as journal:
            result = self.run_gate()
        journal.assert_not_called()
        self.assertEqual(result["status"], "SHORT_PIPELINE_BLOCKED_AT_PI")

    def test_existing_attempt_requires_reconciliation(self):
        with patch("kidsstudio.m68_short_pipeline_gate.assess_short_import",
                   return_value={"status": "M68_SHORT_READY_FOR_M65_POLICY_VERIFICATION",
                                 "checks": {}}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_pi",
                return_value={"status": "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED"}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_short_upload",
                return_value={"status": "EXISTING_UPLOAD_ATTEMPT_REQUIRES_M65_RECONCILIATION"}):
            result = self.run_gate()
        self.assertEqual(result["status"], "SHORT_PIPELINE_EXISTING_UPLOAD_RECONCILIATION")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_all_prechecks_pass_but_upload_stays_blocked(self):
        with patch("kidsstudio.m68_short_pipeline_gate.assess_short_import",
                   return_value={"status": "M68_SHORT_READY_FOR_M65_POLICY_VERIFICATION",
                                 "checks": {}}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_pi",
                return_value={"status": "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED"}), patch(
                "kidsstudio.m68_short_pipeline_gate.audit_short_upload",
                return_value={"status": "NO_UPLOAD_ATTEMPT_M65_APPROVAL_REQUIRED"}):
            result = self.run_gate()
        self.assertEqual(result["status"],
                         "SHORT_PIPELINE_PRECHECK_PASSED_M65_POLICY_REQUIRED")
        self.assertFalse(result["youtube_upload_authorized"])
