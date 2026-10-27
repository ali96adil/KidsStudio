"""Media-queue side-effect fencing: fake render, real Pi SQLite state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.coordinator_api import Coordinator, TransportError
from kidsstudio.media_worker import (
    MediaJournal, MediaRecipes, RemoteMediaWorker, MediaError,
)
from kidsstudio.remote_worker import RemoteWorkerError
from kidsstudio.studio_queue import StudioQueue


class ManualClock:
    def __init__(self): self.now = 10000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class FakePi:
    def __init__(self, server: Coordinator, worker_id="mac-media-01"):
        self.server = server
        self.worker_id = worker_id
        self.calls = []
        self.drop_next_ack = False

    def call(self, action, payload):
        self.calls.append((action, payload))
        if action == "complete-media" and self.drop_next_ack:
            self.drop_next_ack = False
            raise RemoteWorkerError("Simulated network interruption BEFORE Pi commit")
        try:
            return self.server.dispatch(
                action, payload, self.worker_id,
                frozenset({"character_generate", "godot_render"})
            )
        except (TransportError, ValueError) as exc:
            raise RemoteWorkerError("Pi rejected request") from exc


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.fail = False

    def execute(self, kind, recipe_id, job_id):
        self.calls.append((kind, recipe_id, job_id))
        if self.fail: raise RuntimeError("Interrupted local render")
        return {
            "result_status": (
                "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
                if kind == "godot_render" else
                "INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION"
            ),
            "artifact_sha256": "a" * 64,
            "artifact_bytes": 1024,
            "artifact_type": "mp4" if kind == "godot_render" else "rig_report",
            "publication_approved": False,
        }


class MediaJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = ManualClock()
        self.queue = StudioQueue(self.root / "pi.sqlite", clock=self.clock)
        self.queue.initialize()
        self.server = Coordinator(
            self.queue, self.root / "vault",
            {"mac-media-01": ("secret-token-" + "z" * 40,
                              {"godot_render", "character_generate"})}
        )
        self.pi = FakePi(self.server)
        self.source = self.root / "export_report.json"
        self.source.write_text('{"status":"PREVIEW_ONLY_UNAPPROVED"}')
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.file = self.root / "media_recipes.json"
        self.file.write_text(json.dumps({
            "schema_version": 1,
            "recipes": {
                "bunny_clip_01": {
                    "kind": "godot_render",
                    "output_root": str(self.root / "local_outputs"),
                    "inputs": {"project_report": str(self.source)},
                    "sha256": {"project_report": digest},
                }
            }
        }))
        self.recipes = MediaRecipes(self.file)
        self.journal = MediaJournal(self.root / "mac_receipts.sqlite")
        self.executor = FakeExecutor()
        self.worker = RemoteMediaWorker(
            self.pi, self.recipes, self.journal, executor=self.executor
        )

    def enqueue(self, key="one"):
        return self.queue.enqueue(
            kind="godot_render", request_key=key,
            payload={"recipe_id": "bunny_clip_01"}, max_attempts=2,
        )

    def test_media_job_completes_and_records_local_receipt(self):
        job = self.enqueue()
        state = self.worker.run_once()
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "COMPLETED")
        result = json.loads(self.queue.get(job["job_id"])["result_json"])
        self.assertEqual(result["artifact_sha256"], "a" * 64)
        self.assertTrue(result["artifact_stored_on_mac"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(len(self.executor.calls), 1)

    def test_missing_remote_source_path_is_not_taken_from_job(self):
        self.queue.enqueue(
            kind="godot_render", request_key="wrong",
            payload={"recipe_id": "bunny_clip_01",
                     "project_path": "/etc/passwd"}
        )
        with self.assertRaises(MediaError):
            self.worker.run_once()
        self.assertEqual(self.executor.calls, [])

    def test_failed_media_execution_is_quarantined_never_auto_rerun(self):
        job = self.enqueue()
        self.executor.fail = True
        state = self.worker.run_once()
        self.assertEqual(state["status"], "BLOCKED_RECONCILIATION")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "FAILED")
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(self.worker.run_once()["status"], "NO_ELIGIBLE_JOB")

    def test_reconnect_after_lost_ack_replays_receipt_not_render(self):
        job = self.enqueue()
        self.pi.drop_next_ack = True
        first = self.worker.run_once()
        self.assertEqual(first["status"], "PENDING_ACK")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "LEASED")
        self.clock.advance(601)
        second = self.worker.run_once()
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(self.queue.get(job["job_id"])["state"], "COMPLETED")
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(self.queue.get(job["job_id"])["attempts"], 2)

    def test_preexisting_started_record_blocks_reexecution(self):
        job = self.enqueue()
        digest = hashlib.sha256(json.dumps(
            {"kind": "godot_render", "payload": {"recipe_id": "bunny_clip_01"}},
            sort_keys=True
        ).encode()).hexdigest()
        self.journal.begin(job["job_id"], digest, "godot_render", "bunny_clip_01")
        result = self.worker.run_once()
        self.assertEqual(result["status"], "BLOCKED_RECONCILIATION")
        self.assertEqual(self.executor.calls, [])

    def test_cancelled_lease_cannot_complete_media(self):
        job = self.enqueue()
        lease = self.pi.call("claim", {})["job"]
        self.queue.cancel(job["job_id"])
        with self.assertRaises(RemoteWorkerError):
            self.pi.call("complete-media", {
                "job_id": job["job_id"], "generation": lease["generation"],
                "result_status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
                "artifact_sha256": "b" * 64,
                "artifact_bytes": 400,
                "artifact_type": "mp4",
                "publication_approved": False,
            })

    def test_server_rejects_unsafe_status_and_publication(self):
        self.enqueue()
        lease = self.pi.call("claim", {})["job"]
        standard = {
            "job_id": lease["job_id"], "generation": lease["generation"],
            "result_status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "artifact_sha256": "a" * 64, "artifact_bytes": 5000,
            "artifact_type": "mp4", "publication_approved": False,
        }
        for mutate in (
            {"result_status": "PUBLISHED_TO_YOUTUBE"},
            {"publication_approved": True},
            {"artifact_sha256": "fake"},
            {"artifact_type": "shell"},
            {"artifact_bytes": 0},
        ):
            with self.subTest(mutate=mutate), self.assertRaises(RemoteWorkerError):
                self.pi.call("complete-media", {**standard, **mutate})
        self.assertEqual(self.queue.get(lease["job_id"])["state"], "LEASED")

    def test_same_id_different_payload_not_reused(self):
        ident = "a" * 32
        d1 = "1" * 64
        self.assertEqual(
            self.journal.begin(ident, d1, "godot_render", "bunny_clip_01")[0],
            "NEW",
        )
        with self.assertRaises(MediaError):
            self.journal.begin(ident, "2" * 64, "godot_render", "bunny_clip_01")

    def test_modified_local_pinned_recipe_file_blocks_work(self):
        self.enqueue()
        self.source.write_text('{"status":"EDITED"}')
        state = self.worker.run_once()
        self.assertEqual(state["status"], "CONFIG_REJECTED")
        self.assertEqual(len(self.executor.calls), 0)
        self.assertEqual(self.queue.status()["counts"]["FAILED"], 1)
        self.assertEqual(self.queue.status()["counts"]["FAILED"], 1)


if __name__ == "__main__":
    unittest.main()
