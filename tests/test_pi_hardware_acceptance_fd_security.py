import os
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main


class HardwareAcceptanceFdSecurityTests(unittest.TestCase):
    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((ValueError, OSError)):
                main(["--evidence", tmp])

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            self.assertEqual(main(["--init", str(path)]), 0)
            link = Path(tmp) / "link.json"
            link.symlink_to(path)
            with self.assertRaises((ValueError, OSError)):
                main(["--evidence", str(link)])

    def test_private_regular_file_still_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            self.assertEqual(main(["--init", str(path)]), 0)
            self.assertEqual(main(["--evidence", str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
