import unittest

from kidsstudio.transcript_qa import compare_transcript, normalize


class TranscriptQATests(unittest.TestCase):
    def test_arabic_diacritics_and_hamza(self):
        self.assertEqual(normalize("أَحْمَرُ، إِنَّهُ أحمر!"), ["احمر", "انه", "احمر"])

    def test_exact_arabic_match(self):
        result = compare_transcript("هذا لون أحمر", "هذا لون احمر")
        self.assertEqual(result.status, "TEXT_MATCH_CANDIDATE")
        self.assertEqual(result.word_error_rate, 0)

    def test_missing_word_requires_review(self):
        self.assertEqual(compare_transcript("one two three four", "one two four").status,
                         "REVIEW_REQUIRED_MISMATCH")

    def test_empty_never_passes(self):
        self.assertEqual(compare_transcript("", "").status, "REVIEW_REQUIRED_EMPTY_SCRIPT")
        self.assertEqual(compare_transcript("hello", "").status, "REVIEW_REQUIRED_EMPTY_TRANSCRIPT")

    def test_threshold_validation(self):
        with self.assertRaises(ValueError):
            compare_transcript("hello", "hello", max_wer=2)
