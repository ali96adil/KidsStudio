import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main, REQUIRED_STEPS


class EvidenceSecurityTests(unittest.TestCase):
    def test_private_file_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps({
                "version": 1,
                "steps": {step: "not_tested" for step in REQUIRED_STEPS},
            }))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                main(["--evidence", str(path)])
            path.chmod(0o600)
            self.assertEqual(main(["--evidence", str(path)]), 2)

    def test_symlink_and_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "evidence.json"
            path.write_text("x" * 16385)
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                main(["--evidence", str(path)])
            link = root / "linked.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                main(["--evidence", str(link)])


if __name__ == "__main__":
    unittest.main()
