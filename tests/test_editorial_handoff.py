"""Review handoff is atomic, source-pinned and publication-safe."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue, QueueError
from kidsstudio.local_worker import LocalAIWorker
from kidsstudio.ai_router import AIConfig, ChatRouter


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size):
        return json.dumps({
            "choices": [{"message": {"content": self.value}}]
        }, ensure_ascii=False).encode("utf-8")


class Transport:
    def __init__(self):
        self.requests = []
    def open(self, req, timeout):
        self.requests.append(req)
        if ":9002" in req.full_url:
            return Response("REVISE: Improve the child's learning objective.")
        return Response("أرنبنا يتعلم لون الشمس عبر المغامرة")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = StudioQueue(self.root / "brain.sqlite")
        self.queue.initialize()
        cfg = self.root / "providers.json"
        cfg.write_text(json.dumps({
            "schema_version": 1,
            "providers": [
                {"id": "writer", "endpoint": "http://127.0.0.1:9001/v1/chat/completions",
                 "model": "test-writer", "billing": "free"},
                {"id": "critic", "endpoint": "http://127.0.0.1:9002/v1/chat/completions",
                 "model": "test-critic", "billing": "free"},
            ],
            "routes": {
                "script_draft": ["writer"],
                "editorial_review": ["critic"]
            }
        }))
        self.transport = Transport()
        self.worker = LocalAIWorker(
            self.queue,
            ChatRouter(AIConfig(cfg), opener=self.transport),
            self.root / "artifacts", worker_id="mac-local-01",
        )

    def _create(self):
        return self.queue.enqueue(
            kind="script_draft",
            request_key="bunny-yellow-ar-v1",
            payload={
                "language": "ar",
                "topic": "اللون الأصفر",
                "auto_review": True,
            },
        )

    def test_two_stage_draft_review_is_fenced_and_no_public_approval(self):
        job = self._create()
        first = self.worker.run_once()
        self.assertEqual(first["state"], "COMPLETED")
        parent = json.loads(first["result_json"])
        child_id = parent["next_review_job_id"]
        child = self.queue.get(child_id)
        self.assertEqual(child["state"], "QUEUED")
        review_input = json.loads(child["payload"])
        self.assertNotIn("script_text", review_input)
        self.assertEqual(review_input["source_job_id"], job["job_id"])
        self.assertEqual(review_input["original_provider_id"], "writer")

        second = self.worker.run_once()
        self.assertEqual(second["state"], "COMPLETED")
        self.assertEqual(second["job_id"], child_id)
        report = json.loads(second["result_json"])
        self.assertEqual(report["provider_id"], "critic")
        self.assertEqual(report["status"], "EDITORIAL_REVIEW_UNVERIFIED")
        self.assertFalse(report["publication_approved"])
        self.assertEqual(len(self.transport.requests), 2)
        self.assertEqual(
            self.worker.run_once(), {"status": "NO_ELIGIBLE_JOB"}
        )

    def test_draft_tampering_blocks_editorial_review(self):
        self._create()
        first = self.worker.run_once()
        body = json.loads(first["result_json"])
        child_id = body["next_review_job_id"]
        artifact = Path(body["artifact_manifest"]).parent / "answer.txt"
        artifact.write_text("Someone edited the script.", encoding="utf-8")
        fail = self.worker.run_once()
        self.assertEqual(fail["status"], "FAILED")
        self.assertEqual(self.queue.get(child_id)["state"], "FAILED")
        self.assertEqual(len(self.transport.requests), 1)

    def test_no_duplicate_review_after_restart(self):
        self._create()
        first = self.worker.run_once()
        revived = StudioQueue(self.queue.path)
        self.assertEqual(len(revived.list_jobs()), 2)
        child = json.loads(first["result_json"])["next_review_job_id"]
        self.assertEqual(revived.get(child)["state"], "QUEUED")
        self.assertEqual(self.worker.run_once()["state"], "COMPLETED")
        self.assertEqual(len(revived.list_jobs()), 2)

    def test_transaction_rolls_back_with_wrong_language(self):
        parent = self.queue.enqueue(
            kind="script_draft", request_key="other",
            payload={"language": "ar", "topic": "ألوان"}
        )
        lease = self.queue.claim(
            worker_id="mac-local-01", capabilities=["script_draft"]
        )
        fake = {
            "status": "DRAFTED_UNREVIEWED",
            "provider_id": "writer",
            "artifact_sha256": "a" * 64,
            "publication_approved": False
        }
        with self.assertRaises(QueueError):
            self.queue.complete_draft_and_enqueue_review(
                job_id=parent["job_id"], worker_id="mac-local-01",
                generation=lease["generation"], result=fake, language="en"
            )
        self.assertEqual(self.queue.get(parent["job_id"])["state"], "LEASED")
        self.assertEqual(len(self.queue.list_jobs()), 1)
        self.queue.complete_draft_and_enqueue_review(
            job_id=parent["job_id"], worker_id="mac-local-01",
            generation=lease["generation"], result=fake, language="ar"
        )
        self.assertEqual(len(self.queue.list_jobs()), 2)

    def test_attempted_second_handoff_is_rejected(self):
        parent = self._create()
        first = self.worker.run_once()
        with self.assertRaises(QueueError):
            self.queue.complete_draft_and_enqueue_review(
                job_id=parent["job_id"], worker_id="mac-local-01",
                generation=first["generation"], result={
                    "status": "DRAFTED_UNREVIEWED",
                    "provider_id": "writer",
                    "artifact_sha256": "a" * 64,
                    "publication_approved": False,
                }, language="ar"
            )
        self.assertEqual(len(self.queue.list_jobs()), 2)


if __name__ == "__main__":
    unittest.main()
