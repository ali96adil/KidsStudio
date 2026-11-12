import hashlib
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.editorial_eval_adapter import EditorialEvalError, evaluate_local_artifact, main


class EditorialEvalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.attempt = self.root / "job" / "attempt_001"
        self.attempt.mkdir(parents=True)
        self.text = "Today we learn about colors. Red is a bright color."
        self.sha = hashlib.sha256(self.text.encode()).hexdigest()
        (self.attempt / "answer.txt").write_text(self.text)
        self.manifest = self.attempt / "result.json"
        self.manifest.write_text(json.dumps({"answer_sha256": self.sha}))

    def evaluate(self, **kwargs):
        args = dict(artifact_root=self.root, manifest_path=self.manifest,
                    expected_sha256=self.sha, language="en")
        args.update(kwargs)
        return evaluate_local_artifact(**args)

    def test_pass_never_approves_publication(self):
        result = self.evaluate(required_terms=("red",))
        self.assertEqual(result["status"], "MECHANICAL_PASS_REVIEW_REQUIRED")
        self.assertFalse(result["publication_approved"])

    def test_revision(self):
        self.assertEqual(self.evaluate(required_terms=("blue",))["status"],
                         "REVISE_REQUIRED")

    def test_answer_dominated_by_wrong_script_requires_revision(self):
        result = self.evaluate(language="ar")
        self.assertEqual(result["status"], "REVISE_REQUIRED")
        self.assertFalse(result["checks"]["language_script"])
        self.assertFalse(result["publication_approved"])

    def test_tampered_answer(self):
        (self.attempt / "answer.txt").write_text("tampered")
        with self.assertRaises(EditorialEvalError):
            self.evaluate()

    def test_tampered_manifest(self):
        self.manifest.write_text(json.dumps({"answer_sha256": "0" * 64}))
        with self.assertRaises(EditorialEvalError):
            self.evaluate()

    def test_external_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            manifest = Path(outside) / "result.json"
            manifest.write_text(json.dumps({"answer_sha256": self.sha}))
            with self.assertRaises(EditorialEvalError):
                self.evaluate(manifest_path=manifest)

    def test_invalid_sha(self):
        with self.assertRaises(EditorialEvalError):
            self.evaluate(expected_sha256="invalid")

    def test_invalid_manifest_json(self):
        self.manifest.write_text("{invalid")
        with self.assertRaises(EditorialEvalError):
            self.evaluate()

    def test_invalid_answer_encoding(self):
        raw = bytes([255]) * 45
        (self.attempt / "answer.txt").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.manifest.write_text(json.dumps({"answer_sha256": digest}))
        with self.assertRaises(EditorialEvalError):
            self.evaluate(expected_sha256=digest)

    def test_cli_pass_prints_only_metadata(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--artifact-root", str(self.root),
                           "--manifest", str(self.manifest),
                           "--sha256", self.sha, "--language", "en",
                           "--required-term", "red"])
        self.assertEqual(status, 0)
        self.assertNotIn(self.text, output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["publication_approved"])

    def test_cli_revision_exit_code(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--artifact-root", str(self.root),
                           "--manifest", str(self.manifest),
                           "--sha256", self.sha, "--language", "en",
                           "--required-term", "blue"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "REVISE_REQUIRED")

    def test_cli_error_does_not_expose_private_path(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--artifact-root", str(self.root),
                           "--manifest", str(self.root / "missing.json"),
                           "--sha256", self.sha, "--language", "en"])
        self.assertEqual(status, 2)
        self.assertNotIn(str(self.root), output.getvalue())

    def test_does_not_modify_artifacts(self):
        before = self.manifest.read_bytes(), (self.attempt / "answer.txt").read_bytes()
        self.evaluate()
        self.assertEqual(before, (self.manifest.read_bytes(),
                                  (self.attempt / "answer.txt").read_bytes()))


if __name__ == "__main__":
    unittest.main()
