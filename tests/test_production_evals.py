import hashlib
import unittest

from kidsstudio.production_evals import aggregate_runs, evaluate_fixture, evaluate_script


class ProductionEvalsTests(unittest.TestCase):
    def test_pass_and_provenance(self):
        text = "Today we learn about the color blue. The sky can look blue."
        result = evaluate_script(text, language="en", required_terms=("BLUE",))
        self.assertTrue(result.passed)
        self.assertEqual(result.sha256, hashlib.sha256(text.encode()).hexdigest())

    def test_failure_is_not_auto_approved(self):
        result = evaluate_script("short", language="en", required_terms=("red",))
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["length"])
        self.assertFalse(result.checks["required_terms"])

    def test_aggregate(self):
        good = evaluate_script("A" * 50, language="en")
        bad = evaluate_script("", language="en")
        summary = aggregate_runs([good, bad])
        self.assertEqual(summary["pass_rate"], 0.5)
        self.assertEqual(summary["runs"], 2)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            aggregate_runs([])
        with self.assertRaises(ValueError):
            evaluate_script("hello", language="xx")
        with self.assertRaises(ValueError):
            evaluate_script("hello", language="ar", required_terms=("",))

    def test_arabic_normalization(self):
        self.assertTrue(evaluate_script("ﻣﺮﺣﺒﺎ " * 10, language="ar",
                                        required_terms=("مرحبا",)).passed)

    def test_blank_line_rejected(self):
        self.assertFalse(evaluate_script("A" * 45 + "\n\n" + "B" * 10,
                                         language="en").passed)

    def test_unicode_hash_is_exact(self):
        a = evaluate_script("ﻣﺮﺣﺒﺎ " * 10, language="ar")
        b = evaluate_script("مرحبا " * 10, language="ar")
        self.assertNotEqual(a.sha256, b.sha256)

    def test_fixture(self):
        result = evaluate_fixture({"text": "مرحبا " * 10, "language": "ar"})
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
