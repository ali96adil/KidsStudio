from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.comfy import (
    ComfySafetyError, prepare_submission, queue_on_local_comfy,
    validate_local_base_url,
)


class DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return b'{"prompt_id": "job-123"}'


class ComfySafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workflow_file = self.root / "workflow_api.json"
        self.profile_file = self.root / "profile.json"
        self.workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "PLACEHOLDER"}},
            "2": {"class_type": "UNETLoader", "inputs": {
                "unet_name": "flux-2-klein-base-4b.safetensors"}},
            "3": {"class_type": "SaveImage", "inputs": {
                "images": ["1", 0], "filename_prefix": "ComfyUI"}},
        }
        self._write()

    def _write(self):
        raw = json.dumps(self.workflow).encode("utf-8")
        self.workflow_file.write_bytes(raw)
        self.profile = {
            "approved_workflow_sha256": hashlib.sha256(raw).hexdigest(),
            "allowed_node_classes": [
                "CLIPTextEncode", "UNETLoader", "SaveImage"],
            "approved_model_names": ["flux-2-klein-base-4b.safetensors"],
            "prompt_node_id": "1",
            "filename_node_id": "3",
        }
        self.profile_file.write_text(json.dumps(self.profile))

    def run_prepare(self):
        return prepare_submission(
            self.workflow_file, self.profile_file,
            prompt_text="Draw an original isolated bunny arm.",
            filename_prefix="KidsStudio/bunny/arm_left",
        )

    def test_approved_workflow_can_be_prepared_without_submission(self):
        prepared = self.run_prepare()
        self.assertEqual(prepared["status"], "READY_NOT_SUBMITTED")
        self.assertEqual(
            prepared["prompt"]["1"]["inputs"]["text"],
            "Draw an original isolated bunny arm."
        )
        self.assertEqual(
            self.workflow["1"]["inputs"]["text"], "PLACEHOLDER"
        )

    def test_checksum_rejects_unapproved_mutation(self):
        self.workflow["2"]["inputs"]["unet_name"] = "unknown.safetensors"
        self.workflow_file.write_text(json.dumps(self.workflow))
        with self.assertRaises(ComfySafetyError):
            self.run_prepare()

    def test_model_allowlist_enforced(self):
        self.profile["approved_model_names"] = []
        self.profile_file.write_text(json.dumps(self.profile))
        with self.assertRaises(ComfySafetyError):
            self.run_prepare()

    def test_remote_node_rejected_even_when_in_profile(self):
        self.workflow["3"]["class_type"] = "OpenAIImageAPI"
        self._write()
        self.profile["allowed_node_classes"].append("OpenAIImageAPI")
        self.profile_file.write_text(json.dumps(self.profile))
        with self.assertRaises(ComfySafetyError):
            self.run_prepare()

    def test_unsafe_prefix_fails(self):
        with self.assertRaises(ComfySafetyError):
            prepare_submission(
                self.workflow_file, self.profile_file,
                prompt_text="hi", filename_prefix="../secrets"
            )

    def test_nonlocal_endpoint_rejected(self):
        for url in ("https://127.0.0.1:8188", "http://example.com:8188",
                    "http://127.0.0.1:8188/path", "http://localhost"):
            with self.subTest(url=url), self.assertRaises(ComfySafetyError):
                validate_local_base_url(url)

    def test_submit_calls_local_endpoint_only(self):
        prepared = self.run_prepare()
        with patch("kidsstudio.comfy.request.urlopen", return_value=DummyResponse()) as mock:
            result = queue_on_local_comfy(prepared)
        self.assertEqual(result, {"status": "QUEUED", "prompt_id": "job-123"})
        self.assertEqual(mock.call_args.args[0].full_url, "http://127.0.0.1:8188/prompt")


if __name__ == "__main__":
    unittest.main()
