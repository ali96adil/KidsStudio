from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.ai_router import AIConfig, ChatRouter, AIRouterError
from kidsstudio.editorial_eval_adapter import evaluate_local_artifact, EditorialEvalError
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

    def test_draft_artifact_can_be_evaluated_without_queue_mutation(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="eval-draft-ar",
            payload={"language": "ar", "topic": "الألوان"},
        )
        finished = self.worker.run_once()
        completion = json.loads(finished["result_json"])
        events_before = self.queue.events(job["job_id"])
        report = evaluate_local_artifact(
            artifact_root=self.worker.root,
            manifest_path=completion["artifact_manifest"],
            expected_sha256=completion["artifact_sha256"],
            language="ar", required_terms=("الألوان",),
            min_chars=10,
        )
        self.assertEqual(report["status"], "MECHANICAL_PASS_REVIEW_REQUIRED")
        self.assertFalse(report["publication_approved"])
        self.assertEqual(self.queue.get(job["job_id"])["state"], "COMPLETED")
        self.assertEqual(self.queue.events(job["job_id"]), events_before)
        self.assertEqual(len(self.fake.requests), 1)

    def test_draft_eval_rejects_wrong_queue_provenance(self):
        self.queue.enqueue(
            kind="script_draft", request_key="eval-bad-sha",
            payload={"language": "ar", "topic": "الألوان"},
        )
        finished = self.worker.run_once()
        completion = json.loads(finished["result_json"])
        with self.assertRaises(EditorialEvalError):
            evaluate_local_artifact(
                artifact_root=self.worker.root,
                manifest_path=completion["artifact_manifest"],
                expected_sha256="0" * 64, language="ar",
            )

    def test_auto_review_handoff_and_evaluation_preserve_independence(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="episode-auto-review",
            payload={"language": "ar", "topic": "الألوان",
                     "auto_review": True},
        )
        drafted = self.worker.run_once()
        self.assertEqual(drafted["state"], "COMPLETED")
        parent = json.loads(drafted["result_json"])
        review_id = parent["next_review_job_id"]
        self.assertEqual(parent["status"], "DRAFTED_UNREVIEWED")
        self.assertFalse(parent["publication_approved"])
        child = self.queue.get(review_id)
        self.assertEqual(child["state"], "QUEUED")
        self.assertEqual(child["kind"], "editorial_review")
        payload = json.loads(child["payload"])
        self.assertEqual(payload["source_job_id"], job["job_id"])
        self.assertEqual(payload["source_answer_sha256"], parent["artifact_sha256"])
        self.assertNotIn("script_text", payload)
        report = evaluate_local_artifact(
            artifact_root=self.worker.root,
            manifest_path=parent["artifact_manifest"],
            expected_sha256=parent["artifact_sha256"],
            language="ar", required_terms=("الألوان",),
            min_chars=10,
        )
        self.assertEqual(report["status"], "MECHANICAL_PASS_REVIEW_REQUIRED")
        self.assertEqual(self.queue.get(review_id)["state"], "QUEUED")
        reviewed = self.worker.run_once()
        self.assertEqual(reviewed["state"], "COMPLETED")
        review_result = json.loads(reviewed["result_json"])
        self.assertEqual(review_result["status"], "EDITORIAL_REVIEW_UNVERIFIED")
        self.assertEqual(review_result["provider_id"], "critic")
        self.assertFalse(review_result["publication_approved"])
        self.assertEqual(len(self.fake.requests), 2)
        self.assertEqual(self.fake.requests[0].full_url,
                         "http://127.0.0.1:9981/v1/chat/completions")
        self.assertEqual(self.fake.requests[1].full_url,
                         "http://127.0.0.1:9982/v1/chat/completions")

    def test_auto_review_rejects_tampered_source_before_review_provider(self):
        self.queue.enqueue(
            kind="script_draft", request_key="episode-tamper-review",
            payload={"language": "ar", "topic": "الألوان",
                     "auto_review": True},
        )
        drafted = self.worker.run_once()
        parent = json.loads(drafted["result_json"])
        review_id = parent["next_review_job_id"]
        answer = Path(parent["artifact_manifest"]).parent / "answer.txt"
        answer.write_text("tampered")
        failed = self.worker.run_once()
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(self.queue.get(review_id)["state"], "FAILED")
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
