from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.ai_router import AIConfig, ChatRouter, AIRouterError
from kidsstudio.local_worker import LocalAIWorker
from kidsstudio.studio_queue import StudioQueue


class Reply:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size):
        return json.dumps({
            "choices": [{"message": {"content": "قصة تعليمية أصلية عن الألوان"}}]
        }, ensure_ascii=False).encode("utf-8")


class Transport:
    def __init__(self):
        self.requests = []
    def open(self, req, timeout):
        self.requests.append(req)
        return Reply()


class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = StudioQueue(self.root / "state.sqlite")
        self.queue.initialize()
        profile = self.root / "providers.json"
        profile.write_text(json.dumps({
            "schema_version": 1,
            "providers": [
                {"id": "creative", "endpoint": "http://127.0.0.1:9981/v1/chat/completions",
                 "model": "creator:local", "api_key_env": None, "billing": "free"},
                {"id": "critic", "endpoint": "http://127.0.0.1:9982/v1/chat/completions",
                 "model": "reviewer:local", "api_key_env": None, "billing": "free"},
            ],
            "routes": {
                "script_draft": ["creative"],
                "editorial_review": ["critic"],
            },
        }))
        self.fake = Transport()
        self.router = ChatRouter(AIConfig(profile), opener=self.fake)
        self.worker = LocalAIWorker(
            self.queue, self.router, self.root / "private_artifacts",
            worker_id="test-mac", allow_paid=False,
        )

    def test_queue_draft_to_artifact_to_ack(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="episode1-ar",
            payload={"language": "ar", "topic": "اللون الأحمر"},
        )
        result = self.worker.run_once()
        self.assertEqual(result["state"], "COMPLETED")
        data = json.loads(result["result_json"])
        self.assertEqual(data["status"], "DRAFTED_UNREVIEWED")
        self.assertFalse(data["publication_approved"])
        manifest = Path(data["artifact_manifest"])
        self.assertTrue(manifest.is_file())
        self.assertIn("قصة", (manifest.parent / "answer.txt").read_text())
        self.assertEqual(json.loads(manifest.read_text())["provider_id"], "creative")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "COMPLETED")
        self.assertEqual(self.worker.run_once(), {"status": "NO_ELIGIBLE_JOB"})
        self.assertEqual(len(self.fake.requests), 1)

    def test_review_uses_different_provider(self):
        job = self.queue.enqueue(
            kind="editorial_review", request_key="review1-ar",
            payload={
                "language": "ar",
                "script_text": "قصة أرنب يتعلم اللون الأصفر",
                "original_provider_id": "creative",
            },
        )
        result = self.worker.run_once()
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(json.loads(result["result_json"])["provider_id"], "critic")
        self.assertEqual(self.fake.requests[0].full_url,
                         "http://127.0.0.1:9982/v1/chat/completions")

    def test_illegal_worker_job_not_claimed(self):
        self.queue.enqueue(
            kind="godot_render", request_key="render1",
            payload={"project": "/private/tmp/fake"},
        )
        self.assertEqual(self.worker.run_once(), {"status": "NO_ELIGIBLE_JOB"})
        self.assertEqual(self.queue.status()["counts"]["QUEUED"], 1)

    def test_missing_independence_fails_and_records_safe_code(self):
        job = self.queue.enqueue(
            kind="editorial_review", request_key="review-bad",
            payload={
                "language": "ar",
                "script_text": "Draft",
                "original_provider_id": "critic",
            },
        )
        failed = self.worker.run_once()
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["error_code"], "AI_WORKER_ERROR")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "FAILED")
        self.assertEqual(len(self.fake.requests), 0)

    def test_no_paid_or_auto_repeat(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="bad-topic",
            payload={"language": "de", "topic": "test"},
        )
        failed = self.worker.run_once()
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(self.queue.get(job["job_id"])["attempts"], 1)
        self.assertFalse(self.queue.events(job["job_id"])[0]["event_type"] == "RETRY_SCHEDULED")

    def test_data_still_there_after_queue_reopen(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="episode-reopen",
            payload={"language": "en", "topic": "Colors in a garden"},
        )
        self.worker.run_once()
        new = StudioQueue(self.queue.path)
        self.assertEqual(new.get(job["job_id"])["state"], "COMPLETED")

    def test_pause_prevents_dispatch(self):
        self.queue.enqueue(
            kind="script_draft", request_key="paused",
            payload={"language": "ar", "topic": "الألوان"},
        )
        self.queue.set_paused(True)
        self.assertEqual(self.worker.run_once(), {"status": "NO_ELIGIBLE_JOB"})
        self.assertEqual(len(self.fake.requests), 0)


if __name__ == "__main__":
    unittest.main()
