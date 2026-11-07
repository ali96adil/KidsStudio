import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.omniroute_benchmark import (
    OmniRouteBenchmarkError, compare_text_candidates, main,
)


class OmniRouteBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name) / "private"
        self.private.mkdir(mode=0o700)
        self.fixture = self.private / "candidates.json"
        self.candidate = {
            "model": "ollama/qwen3-local",
            "language": "ar",
            "text": "هذه قصة تعليمية أصلية عن اللون الأحمر ومزج الألوان. " * 3,
            "required_terms": ["اللون", "الأحمر"],
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "latency_ms": 1234.5,
            "usd_per_m_input_tokens": "0",
            "usd_per_m_output_tokens": "0",
        }

    def save(self, candidates):
        self.fixture.write_text(
            json.dumps({"candidates": candidates}, ensure_ascii=False),
            encoding="utf-8")
        self.fixture.chmod(0o600)

    def test_local_synthetic_pass_but_not_child_safety(self):
        report = compare_text_candidates([self.candidate])
        self.assertEqual(report["status"], "OFFLINE_COMPARISON_UNVERIFIED")
        self.assertTrue(report["candidates"][0]["mechanical_passed"])
        self.assertFalse(report["child_safety_verified"])
        self.assertFalse(report["owner_publication_approved"])
        self.assertEqual(report["inference_requests_performed"], 0)
        self.assertNotIn(self.candidate["text"], str(report))
        self.assertEqual(report["total_estimated_api_cost_usd"], 0)

    def test_cost_is_estimate_from_supplied_rates(self):
        item = dict(self.candidate, model="groq/example",
                    usd_per_m_input_tokens="0.50",
                    usd_per_m_output_tokens="2.00")
        report = compare_text_candidates([item])
        self.assertAlmostEqual(
            report["candidates"][0]["estimated_api_cost_usd"],
            0.00045, places=10)
        self.assertFalse(report["real_billing_verified"])

    def test_missing_rates_produce_unknown_cost(self):
        item = dict(self.candidate)
        item.pop("usd_per_m_input_tokens")
        item.pop("usd_per_m_output_tokens")
        report = compare_text_candidates([item])
        self.assertIsNone(report["total_estimated_api_cost_usd"])

    def test_bilingual_candidates_without_automatic_ranking(self):
        other = dict(self.candidate, model="lmstudio/test", language="en",
                     text="The little bunny learns about the color red in our garden. " * 2,
                     required_terms=["red"])
        report = compare_text_candidates([self.candidate, other])
        self.assertEqual(len(report["candidates"]), 2)
        self.assertTrue(report["no_automatic_model_selection"])

    def test_invalid_token_counts(self):
        for count in (-1, 2_000_001, 4.2, True, "200"):
            with self.subTest(count=count), self.assertRaises(OmniRouteBenchmarkError):
                compare_text_candidates([dict(self.candidate, prompt_tokens=count)])

    def test_invalid_rates(self):
        for rate in ("NaN", "-1", "Infinity", {}, 10001):
            with self.subTest(rate=rate), self.assertRaises(OmniRouteBenchmarkError):
                compare_text_candidates([dict(
                    self.candidate, usd_per_m_input_tokens=rate)])

    def test_incomplete_pricing_rejected(self):
        item = dict(self.candidate)
        item.pop("usd_per_m_output_tokens")
        with self.assertRaises(OmniRouteBenchmarkError):
            compare_text_candidates([item])

    def test_unrealistic_latency_rejected(self):
        for value in (-1, float("inf"), 3_600_001, "fast"):
            with self.subTest(value=value), self.assertRaises(OmniRouteBenchmarkError):
                compare_text_candidates([dict(self.candidate, latency_ms=value)])

    def test_auto_route_rejected(self):
        with self.assertRaises(ValueError):
            compare_text_candidates([dict(self.candidate, model="auto/cheap")])

    def test_empty_and_many_candidates_rejected(self):
        with self.assertRaises(OmniRouteBenchmarkError):
            compare_text_candidates([])
        with self.assertRaises(OmniRouteBenchmarkError):
            compare_text_candidates([self.candidate] * 13)

    def test_private_cli_never_prints_text_or_path(self):
        self.save([self.candidate])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--private-fixture", str(self.fixture)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "OFFLINE_COMPARISON_UNVERIFIED")
        self.assertNotIn(self.candidate["text"], output.getvalue())
        self.assertNotIn(str(self.private), output.getvalue())

    def test_public_fixture_rejected(self):
        self.save([self.candidate])
        self.fixture.chmod(0o644)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--private-fixture", str(self.fixture)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["inference_requests_performed"], 0)

    def test_symlink_fixture_rejected(self):
        self.save([self.candidate])
        link = self.private / "link.json"
        link.symlink_to(self.fixture)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--private-fixture", str(link)]), 2)

    def test_public_parent_rejected(self):
        self.save([self.candidate])
        self.private.chmod(0o755)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--private-fixture", str(self.fixture)]), 2)

    def test_malformed_fixture_fails_closed(self):
        self.fixture.write_text("{broken", encoding="utf-8")
        self.fixture.chmod(0o600)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--private-fixture", str(self.fixture)]), 2)

    def test_no_fixture_contents_in_safe_error(self):
        self.save([dict(self.candidate, model="auto/cheap")])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--private-fixture", str(self.fixture)]), 2)
        self.assertNotIn(self.candidate["text"], out.getvalue())


if __name__ == "__main__":
    unittest.main()
