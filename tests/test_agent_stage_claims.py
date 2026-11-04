import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kidsstudio.agent_stage_claims import claim_stage, read_claims, release_stage, validate_claim, renew_claim
from kidsstudio.episode_stage_checkpoints import initialize, transition


class StageClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        initialize(self.root, "colors_001", "animated_explainer")

    def test_exclusive_claim_release_and_private_file(self):
        claim = claim_stage(self.root, "colors_001", "curriculum", "writer-a")
        self.assertEqual(claim["agent_id"], "writer-a")
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "curriculum", "writer-b")
        with self.assertRaises(ValueError):
            release_stage(self.root, "colors_001", "curriculum", "writer-b")
        self.assertTrue(release_stage(self.root, "colors_001", "curriculum", "writer-a"))
        self.assertEqual(claim_stage(self.root, "colors_001", "curriculum", "writer-b")["agent_id"], "writer-b")
        path = self.root / "colors_001.checkpoints.claims.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(read_claims(self.root, "colors_001")["public_release_authorized"])\n        self.assertNotIn("fencing_token", read_claims(self.root, "colors_001")["claims"]["curriculum"])

    def test_parallel_claim_only_one_wins(self):
        def attempt(i):
            try:
                claim_stage(self.root, "colors_001", "curriculum", "agent-" + str(i))
                return "won"
            except ValueError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(results.count("won"), 1)
        self.assertEqual(results.count("blocked"), 7)

    def test_not_ready_stage_rejected(self):
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "script", "writer-a")
        transition(self.root, "colors_001", "curriculum", "running")
        transition(self.root, "colors_001", "curriculum", "passed")
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "curriculum", "writer-a")
        self.assertEqual(claim_stage(self.root, "colors_001", "script", "writer-a")["stage"], "script")

    def test_fencing_token_and_renewal(self):
        first = claim_stage(self.root, "colors_001", "curriculum", "writer-a")
        token = first["fencing_token"]
        self.assertTrue(validate_claim(self.root, "colors_001", "curriculum", "writer-a", token))
        renewed = renew_claim(self.root, "colors_001", "curriculum", "writer-a", token, 1200)
        self.assertEqual(renewed["fencing_token"], token)
        with self.assertRaises(ValueError):
            validate_claim(self.root, "colors_001", "curriculum", "writer-a", "0" * 32)
        release_stage(self.root, "colors_001", "curriculum", "writer-a")
        second = claim_stage(self.root, "colors_001", "curriculum", "writer-a")
        self.assertNotEqual(second["fencing_token"], token)
        with self.assertRaises(ValueError):
            renew_claim(self.root, "colors_001", "curriculum", "writer-a", token)
        self.assertTrue(validate_claim(self.root, "colors_001", "curriculum", "writer-a", second["fencing_token"]))

    def test_invalid_agent_duration_and_symlink(self):
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "curriculum", "../bad")
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "curriculum", "writer", lease_seconds=0)
        path = self.root / "colors_001.checkpoints.claims.json"
        path.symlink_to(self.root / "colors_001.checkpoints.json")
        with self.assertRaises(ValueError):
            claim_stage(self.root, "colors_001", "curriculum", "writer")


if __name__ == "__main__":
    unittest.main()
