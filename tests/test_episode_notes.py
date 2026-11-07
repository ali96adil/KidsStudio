from pathlib import Path
import tempfile
import unittest

from kidsstudio.episode_notes import EpisodeNotes


class EpisodeNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.db = self.root / "notes.sqlite"
        self.notes = EpisodeNotes(self.db)
        self.notes.initialize()

    def test_add_and_list_arabic_note(self):
        note_id = self.notes.add(episode_id="colors_ar_01", text="راجع صوت الأرنب")
        self.assertEqual(self.notes.list_notes(episode_id="colors_ar_01"),
                         [{"note_id": note_id, "text": "راجع صوت الأرنب",
                           "resolved": False}])

    def test_resolve_preserves_original_note(self):
        note_id = self.notes.add(episode_id="colors_ar_01", text="راجع اللون")
        self.notes.resolve(episode_id="colors_ar_01", note_id=note_id)
        self.assertTrue(self.notes.list_notes(episode_id="colors_ar_01")[0]["resolved"])

    def test_double_resolve_rejected(self):
        note_id = self.notes.add(episode_id="colors_ar_01", text="تعديل")
        self.notes.resolve(episode_id="colors_ar_01", note_id=note_id)
        with self.assertRaises(ValueError):
            self.notes.resolve(episode_id="colors_ar_01", note_id=note_id)

    def test_episode_isolation(self):
        self.notes.add(episode_id="colors_ar_01", text="ملاحظة")
        self.assertEqual(self.notes.list_notes(episode_id="colors_en_01"), [])

    def test_wrong_episode_cannot_resolve(self):
        note_id = self.notes.add(episode_id="colors_ar_01", text="ملاحظة")
        with self.assertRaises(ValueError):
            self.notes.resolve(episode_id="colors_en_01", note_id=note_id)

    def test_invalid_episode_id_rejected(self):
        with self.assertRaises(ValueError):
            self.notes.add(episode_id="../other", text="ملاحظة")

    def test_existing_database_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            self.notes.initialize()


if __name__ == "__main__":
    unittest.main()
