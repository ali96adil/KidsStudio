"""M68 vision diagnostic must not certify audio or copyright."""
import unittest
from unittest.mock import patch
from kidsstudio.m68_local_vision_diagnostic import UNOBSERVABLE, VISUAL_AXES


class VisionDiagnosticTests(unittest.TestCase):
    def test_silent_frames_never_approve_audio_or_rights(self):
        self.assertEqual(set(UNOBSERVABLE), {"audio", "copyright", "pedagogy", "source_consistency"})
        self.assertTrue(all(len(message) >= 12 for message in UNOBSERVABLE.values()))
        self.assertFalse(set(UNOBSERVABLE) & VISUAL_AXES)

    def test_all_six_review_axes_are_accounted_for(self):
        from kidsstudio.m68_short_content_review import CHECKS
        self.assertEqual(set(CHECKS), set(UNOBSERVABLE) | VISUAL_AXES)

    def test_only_directly_observed_visual_axes_can_pass(self):
        self.assertEqual(VISUAL_AXES, {"visual", "age_appropriate"})
        self.assertEqual(len(UNOBSERVABLE), 4)
