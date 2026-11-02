import unittest
from kidsstudio.owner_series_board import summarize, STAGES


class SeriesBoardTests(unittest.TestCase):
    def test_series_progress(self):
        data = {"schema_version": 1, "series": [
            {"id": "colors", "title": "الألوان", "episodes": [
                {"id": "red", "title": "الأحمر", "stage": "script"},
                {"id": "blue", "title": "الأزرق", "stage": "render"},
            ]}
        ]}
        result = summarize(data)
        self.assertEqual(result["episode_count"], 2)
        self.assertEqual(result["series"][0]["stage_counts"]["script"], 1)
        self.assertEqual(result["series"][0]["stage_counts"]["render"], 1)
        self.assertTrue(result["read_only"])

    def test_reject_duplicate_episode(self):
        entry = {"id": "a", "title": "A", "stage": "idea"}
        with self.assertRaises(ValueError):
            summarize({"schema_version": 1, "series": [
                {"id": "colors", "title": "Colors", "episodes": [entry, entry]}
            ]})

    def test_reject_unapproved_stage(self):
        with self.assertRaises(ValueError):
            summarize({"schema_version": 1, "series": [
                {"id": "colors", "title": "Colors", "episodes": [
                    {"id": "1", "title": "One", "stage": "published"}
                ]}
            ]})

    def test_all_stages_present(self):
        result = summarize({"schema_version": 1, "series": []})
        self.assertEqual(result["episode_count"], 0)
        self.assertIn("approved", STAGES)


if __name__ == "__main__":
    unittest.main()
