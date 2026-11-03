import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main


class InitConflictTests(unittest.TestCase):
    def test_init_refuses_step_or_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            with self.assertRaises(SystemExit):
                main(["--init", str(path), "--step", "mac_video_export",
                      "--status", "pass"])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
