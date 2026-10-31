"""Tests for series educational status aggregation."""
import unittest

from kidsstudio.m68_series_dashboard_summary import summarize_series


def row(episode, stage, attempts):
    return {"source_episode_id": episode, "stage": stage,
            "revision_attempts": attempts,
            "next_action": "Review pending findings",
            "media_quality_verified": False,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


class SeriesDashboardSummaryTests(unittest.TestCase):
    def test_mixed_series_counts(self):
        result = summarize_series("colors", [
            row("e1", "EDUCATIONAL_SCRIPT_MODEL_PASS", 1),
            row("e2", "EDUCATIONAL_REVIEW_NEEDS_TRIAGE", 3),
            row("e3", "EDUCATIONAL_REVIEW_TECHNICAL_FAILURE", 0)])
        self.assertEqual(result["total_episodes"], 3)
        self.assertEqual(result["educational_script_pass"], 1)
        self.assertEqual(result["needs_triage"], 1)
        self.assertEqual(result["technical_failures"], 1)
        self.assertFalse(result["public_release_authorized"])

    def test_duplicate_episode_rejected(self):
        with self.assertRaises(ValueError):
            summarize_series("colors", [
                row("e1", "EDUCATIONAL_SCRIPT_MODEL_PASS", 0),
                row("e1", "EDUCATIONAL_SCRIPT_MODEL_PASS", 0)])

    def test_fake_release_flag_rejected(self):
        bad = row("e1", "EDUCATIONAL_SCRIPT_MODEL_PASS", 0)
        bad["youtube_upload_authorized"] = True
        with self.assertRaises(ValueError):
            summarize_series("colors", [bad])

    def test_empty_series(self):
        result = summarize_series("colors", [])
        self.assertEqual(result["total_episodes"], 0)
