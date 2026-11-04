"""Initial Mac discovery is read-only, no downloads or engine execution."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kidsstudio.mac_quick_probe import inspect_owner_mac,ASSETS


class MacProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)

    def test_missing_assets_reported_without_creating_any_files(self):
        report=inspect_owner_mac(self.home,system="Darwin",machine="arm64",
                                  tool_lookup=lambda name:None)
        self.assertEqual(report["status"],"MAC_DISCOVERY_INCOMPLETE_NO_CHANGES")
        self.assertEqual(len(report["missing_asset_roles"]),len(ASSETS))
        self.assertFalse(report["files_modified"])
        self.assertFalse(report["network_requests"])
        self.assertFalse(report["model_execution_performed"])
        self.assertFalse(report["api_keys_read"])
        self.assertEqual(list(self.home.iterdir()),[])
        self.assertNotIn(str(self.home),str(report))

    def test_all_found_does_not_count_as_engine_qualification(self):
        for relative,kind in ASSETS.values():
            file=self.home/relative
            file.parent.mkdir(parents=True,exist_ok=True)
            if kind=="dir": file.mkdir(exist_ok=True)
            else: file.write_bytes(b"synthetic test file")
        report=inspect_owner_mac(self.home,system="Darwin",machine="arm64",
                                  tool_lookup=lambda name:"/test/"+name)
        self.assertEqual(report["status"],"MAC_PATHS_FOUND_ENGINE_API_NOT_QUALIFIED")
        self.assertFalse(report["model_execution_performed"])
        self.assertFalse(report["voice_and_model_license_verified"])
        self.assertFalse(report["public_release_authorized"])

    def test_non_mac_never_claims_ready(self):
        report=inspect_owner_mac(self.home,system="Linux",machine="x86_64",
                                 tool_lookup=lambda name:"/bin/"+name)
        self.assertEqual(report["status"],"NOT_APPLE_SILICON_MAC")
        self.assertFalse(report["apple_silicon_mac"])


if __name__=="__main__":
    unittest.main()
