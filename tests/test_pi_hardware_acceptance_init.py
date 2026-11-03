import json
import stat
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main, REQUIRED_STEPS


class HardwareAcceptanceInitTests(unittest.TestCase):
    def test_private_new_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acceptance.json"
            self.assertEqual(main(["--init", str(path)]), 0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            data = json.loads(path.read_text())
            self.assertEqual(set(data["steps"]), set(REQUIRED_STEPS))
            self.assertTrue(all(v == "not_tested" for v in data["steps"].values()))
            with self.assertRaises(FileExistsError):
                main(["--init", str(path)])
            self.assertEqual(json.loads(path.read_text()), data)

    def test_symlink_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.write_text("do-not-overwrite")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaises((FileExistsError, OSError)):
                main(["--init", str(link)])
            self.assertEqual(target.read_text(), "do-not-overwrite")


if __name__ == "__main__":
    unittest.main()
