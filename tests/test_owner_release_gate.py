import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_release_gate import OwnerReleaseGate


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.gate = OwnerReleaseGate(Path(self.temp.name) / "releases.sqlite")
        self.gate.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_default_is_hold_even_if_review_approved(self):
        self.assertEqual(self.gate.latest("red-ar"), "hold")
        self.assertFalse(self.gate.eligible("red-ar", "approved"))

    def test_release_requires_both_approvals(self):
        self.gate.record("red-ar", "release_authorized", "owner")
        self.assertFalse(self.gate.eligible("red-ar", "changes_requested"))
        self.assertTrue(self.gate.eligible("red-ar", "approved"))

    def test_hold_revokes_release(self):
        self.gate.record("red-ar", "release_authorized", "owner")
        self.gate.record("red-ar", "hold", "owner")
        self.assertFalse(self.gate.eligible("red-ar", "approved"))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.gate.record("../red", "release_authorized", "owner")
        with self.assertRaises(ValueError):
            self.gate.record("red-ar", "published", "owner")
        with self.assertRaises(ValueError):
            self.gate.record("red-ar", "release_authorized", "")


if __name__ == "__main__":
    unittest.main()
