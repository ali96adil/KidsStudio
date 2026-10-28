"""M39 read-only Mac/Pi pilot audit: synthetic SQLite and Mac metadata.

Even a simulated perfect Mac contract MUST NOT enable a real device job.
No actual Pi, Mac, trained model or YouTube action is taken by these tests.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from kidsstudio.studio_pilot_readiness import audit_pilot
from test_studio_orchestrator_m32 import Orchestration32


class OfflinePilotReadiness39(unittest.TestCase):
    def setUp(self):
        h=Orchestration32("test_plan_cannot_advertise_public_permission")
        h.setUp()
        self.addCleanup(h.doCleanups)
        self.h=h

    def audit(self,**changes):
        kwargs=dict(queue=self.h.queue,plan_file=self.h.plan,
            parent_script=self.h.parent,
            scene_scripts=tuple(self.h.scripts))
        kwargs.update(changes)
        return audit_pilot(**kwargs)

    def assert_hardware_blocked(self,result):
        self.assertFalse(result["pi_live_contacted"])
        self.assertFalse(result["model_inference_performed"])
        self.assertFalse(result["mac_pi_hardware_qualified"])
        self.assertFalse(result["actual_model_capability_qualified"])
        self.assertFalse(result["private_upload_permitted"])
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertTrue(result["owner_post_private_review_required"])
        gates={item["id"]:item for item in result["gates"]}
        self.assertEqual(len(gates),11)
        self.assertEqual(gates["LIVE_PI_TLS_CLOCK"]["state"],
                         "NOT_YET_QUALIFIED")
        self.assertEqual(gates["REAL_INDEPENDENT_AUDIO_AV_QA"]["state"],
                         "NOT_YET_QUALIFIED")

    def test_unpinned_pi_never_says_ready(self):
        before=self.h.queue.status()["counts"].copy()
        report=self.audit()
        self.assertEqual(report["status"],"M39_PILOT_READINESS_BLOCKED")
        self.assertEqual(report["offline_gate_count_passed"],2)
        self.assertIn("PI_TWO_SCENE_ORCHESTRATOR",report["blockers"])
        self.assertIn("OWNER_MAC_MODEL_FILES",report["blockers"])
        self.assertEqual(self.h.queue.status()["counts"],before)
        self.assert_hardware_blocked(report)

    def test_pinned_pi_and_sources_pass_three_offline_not_hardware(self):
        self.h.coord.pin(self.h.plan)
        first=self.audit()
        second=self.audit()
        self.assertEqual(first,second)
        self.assertEqual(first["offline_gate_count_passed"],3)
        self.assertTrue(first["source_hashes_verified"])
        self.assertEqual(first["gates"][0]["state"],"PASS_OFFLINE")
        self.assertEqual(first["status"],"M39_PILOT_READINESS_BLOCKED")
        self.assert_hardware_blocked(first)

    def test_even_mock_positive_mac_file_report_does_not_authorize_pilot(self):
        self.h.coord.pin(self.h.plan)
        # Do NOT simulate model execution or Pi contact. This patch is
        # intentionally a false-positive local-file check.
        with patch("kidsstudio.studio_pilot_readiness.check_mac_contract",
                   return_value={"status":"CHECKPOINT_BYTES_ONLY"}):
            result=self.audit(mac_contract=self.h.root/"mock_mac.json")
        self.assertEqual(result["offline_gate_count_passed"],4)
        self.assertEqual(result["next_phase"],
                         "M21_AUTHENTICATED_LIVE_PI_PREFLIGHT")
        self.assertEqual(result["status"],
            "M39_OFFLINE_PREREQUISITES_MET_LIVE_PILOT_NOT_AUTHORIZED")
        self.assert_hardware_blocked(result)

    def test_paused_or_leased_job_blocks_local_preflight(self):
        self.h.coord.pin(self.h.plan)
        self.h.queue.set_paused(True)
        result=self.audit()
        self.assertIn("STUDIO_IDLE_AND_NOT_PAUSED",result["blockers"])
        self.assertIn("PI_TWO_SCENE_ORCHESTRATOR",result["blockers"])
        self.h.queue.set_paused(False)
        job=self.h.coord.tick(self.h.plan)
        self.assertEqual(job["action"],"FIRST_AI_VOICE")
        result=self.audit()
        self.assertIn("STUDIO_IDLE_AND_NOT_PAUSED",result["blockers"])
        self.assertIn("PI_TWO_SCENE_ORCHESTRATOR",result["blockers"])
        self.assert_hardware_blocked(result)

    def test_parent_or_scene_byte_swap_blocks_even_if_pi_is_pinned(self):
        self.h.coord.pin(self.h.plan)
        self.h.scripts[1].write_text("Different script still present on the Mac")
        result=self.audit()
        self.assertEqual(result["gates"][0]["state"],"BLOCKED")
        self.assertEqual(result["gates"][0]["requirement"],
                         "HASH_MISMATCH_OR_MISSING")
        self.assertFalse(result["source_hashes_verified"])
        self.assert_hardware_blocked(result)
        result=self.audit(parent_script=None,scene_scripts=None)
        self.assertEqual(result["gates"][0]["requirement"],"NOT_SUPPLIED")
        self.assert_hardware_blocked(result)

    def test_bad_mac_contract_never_claims_resource_readiness(self):
        self.h.coord.pin(self.h.plan)
        result=self.audit(mac_contract=self.h.root/"missing_mac.json")
        self.assertFalse(result["mac_contract_files_checked"])
        self.assertEqual(result["offline_gate_count_passed"],3)
        self.assertIn("OWNER_MAC_MODEL_FILES",result["blockers"])
        self.assert_hardware_blocked(result)


if __name__=="__main__":
    unittest.main()
