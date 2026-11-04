"""M67 local ComfyUI worker security and completion tests."""
import unittest
from unittest.mock import patch

from kidsstudio.m67_comfy_worker import _endpoint, run_workflow, ComfyWorkerError


class M67ComfyWorkerTests(unittest.TestCase):
    def test_reject_remote_endpoint(self):
        for endpoint in ("https://example.org:8188", "http://192.168.1.4:8188",
                         "http://localhost:8188/other"):
            with self.assertRaises(ComfyWorkerError):
                _endpoint(endpoint)

    def test_reject_missing_save_node(self):
        with self.assertRaises(ComfyWorkerError):
            run_workflow({"1": {"class_type": "KSampler"}})

    def test_local_workflow_completes_without_qa_pass(self):
        responses = iter([
            {"prompt_id": "abc"},
            {"abc": {"status": {"status_str": "success"},
                     "outputs": {"2": {"images": [
                         {"filename": "test.png", "type": "output"}]}}}},
        ])
        with patch("kidsstudio.m67_comfy_worker._request",
                   side_effect=lambda *args, **kwargs: next(responses)):
            result = run_workflow({"2": {"class_type": "SaveImage"}},
                                  poll_seconds=0, max_wait_seconds=5)
        self.assertEqual(result["status"], "COMFY_OUTPUT_PENDING_VALIDATION")
        self.assertEqual(result["visual_qa"], "PENDING")


if __name__ == "__main__":
    unittest.main()
