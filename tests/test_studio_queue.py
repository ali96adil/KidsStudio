"""Offline deterministic SQLite safety and durability tests for Studio Director."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import QueueError, StudioQueue
from kidsstudio.studio_cli import main as studioctl


class Clock:
    def __init__(self, value: float = 10000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.path = self.root / "studio.sqlite"
        self.q = StudioQueue(self.path, clock=self.clock)
        self.q.initialize()

    def add(self, key="episode-001:character"):
        return self.q.enqueue(
            kind="character_generate", request_key=key,
            payload={"character_id": "bunny_v02", "blueprint": "bunny_v02"},
            max_attempts=2,
        )

    def claim(self, worker="Mac-01", lease=120):
        return self.q.claim(
            worker_id=worker, capabilities=["character_generate"],
            lease_seconds=lease,
        )

    def test_initialize_without_overwriting(self):
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.q.status()["counts"]["QUEUED"], 0)
        with self.assertRaises(FileExistsError):
            self.q.initialize()

    def test_idempotency_same_key_same_request(self):
        a = self.add()
        b = self.add()
        self.assertEqual(a["job_id"], b["job_id"])
        self.assertEqual(len(self.q.events(a["job_id"])), 1)
        self.assertEqual(self.q.status()["counts"]["QUEUED"], 1)

    def test_conflicting_idempotency_key_is_blocked(self):
        self.add()
        with self.assertRaises(QueueError):
            self.q.enqueue(kind="rig_review", request_key="episode-001:character",
                           payload={"reference_id": "different"})

    def test_unauthorized_job_type_blocked(self):
        with self.assertRaises(QueueError):
            self.q.enqueue(kind="execute_shell", request_key="no", payload={})

    def test_secret_fields_blocked_at_any_depth(self):
        for value in (
            {"access_token": "private"},
            {"nested": [{"private_key": "data"}]},
            {"apiKey": "do-not-store"},
        ):
            with self.subTest(value=value), self.assertRaises(QueueError):
                self.q.enqueue(kind="rig_review", request_key="sensitive",
                               payload=value)
        self.assertEqual(self.q.status()["counts"]["QUEUED"], 0)

    def test_lease_claim_and_complete_with_generation(self):
        job = self.add()
        claimed = self.claim()
        self.assertEqual(claimed["job_id"], job["job_id"])
        self.assertEqual(claimed["state"], "LEASED")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(claimed["generation"], 1)
        self.assertEqual(self.q.claim(
            worker_id="OtherMac", capabilities=["character_generate"]
        ), None)
        done = self.q.complete(
            job_id=job["job_id"], worker_id="Mac-01",
            generation=claimed["generation"],
            result={"status": "QA_PENDING", "artifact_sha256": "test"},
        )
        self.assertEqual(done["state"], "COMPLETED")
        self.assertEqual(json.loads(done["result_json"])["status"], "QA_PENDING")
        self.assertEqual(self.q.status()["counts"]["COMPLETED"], 1)

    def test_wrong_worker_or_generation_cannot_complete(self):
        job = self.add()
        leased = self.claim()
        for who, generation in (("OtherMac", 1), ("Mac-01", 0), ("Mac-01", 2)):
            with self.assertRaises(QueueError):
                self.q.complete(
                    job_id=job["job_id"], worker_id=who,
                    generation=generation, result={"ok": True},
                )
        self.assertEqual(self.q.get(job["job_id"])["state"], "LEASED")

    def test_expired_lease_is_reissued_with_new_fence(self):
        job = self.add()
        old = self.claim(lease=10)
        self.clock.tick(11)
        new = self.claim(worker="Mac-02", lease=10)
        self.assertEqual(new["job_id"], old["job_id"])
        self.assertEqual(new["attempts"], 2)
        self.assertGreater(new["generation"], old["generation"])
        with self.assertRaises(QueueError):
            self.q.complete(job_id=job["job_id"], worker_id="Mac-01",
                            generation=old["generation"], result={"ok": True})
        done = self.q.complete(job_id=job["job_id"], worker_id="Mac-02",
                               generation=new["generation"], result={"ok": True})
        self.assertEqual(done["state"], "COMPLETED")
        types = [e["event_type"] for e in self.q.events(job["job_id"])]
        self.assertIn("LEASE_EXPIRED_REQUEUED", types)

    def test_two_expired_leases_exhaust_budget(self):
        job = self.add()
        self.claim(lease=10)
        self.clock.tick(11)
        self.claim(worker="Mac-02", lease=10)
        self.clock.tick(11)
        self.assertIsNone(self.claim(worker="Mac-03", lease=10))
        after = self.q.get(job["job_id"])
        self.assertEqual(after["state"], "FAILED")
        self.assertEqual(after["error_code"], "LEASE_EXHAUSTED")

    def test_heartbeat_extends_owned_lease(self):
        job = self.add()
        leased = self.claim(lease=10)
        self.clock.tick(5)
        refreshed = self.q.heartbeat(
            job_id=job["job_id"], worker_id="Mac-01",
            generation=leased["generation"], lease_seconds=120,
        )
        self.assertEqual(refreshed["lease_expires"], self.clock.value + 120)
        self.clock.tick(20)
        self.assertIsNone(self.claim(worker="Mac-02", lease=10))

    def test_expired_lease_cannot_be_renewed(self):
        job = self.add()
        leased = self.claim(lease=10)
        self.clock.tick(10)
        with self.assertRaises(QueueError):
            self.q.heartbeat(job_id=job["job_id"], worker_id="Mac-01",
                             generation=leased["generation"])

    def test_retryable_failure_uses_backoff_and_final_failure(self):
        job = self.add()
        first = self.claim()
        again = self.q.fail(
            job_id=job["job_id"], worker_id="Mac-01",
            generation=first["generation"], error_code="COMFY_TEMP_UNAVAILABLE",
            retryable=True,
        )
        self.assertEqual(again["state"], "QUEUED")
        self.assertEqual(again["available_at"], self.clock.value + 20)
        self.assertIsNone(self.claim(worker="Mac-02"))
        self.clock.tick(20)
        second = self.claim(worker="Mac-02")
        self.assertEqual(second["attempts"], 2)
        failed = self.q.fail(
            job_id=job["job_id"], worker_id="Mac-02",
            generation=second["generation"], error_code="COMFY_FAILURE",
            retryable=True,
        )
        self.assertEqual(failed["state"], "FAILED")
        self.assertIsNone(self.claim())

    def test_pausing_does_not_kill_lease_but_stops_new_jobs(self):
        first = self.add("first")
        self.clock.tick(1)
        second = self.add("second")
        worker = self.claim()
        self.q.set_paused(True)
        self.assertIsNone(self.claim(worker="Mac-02"))
        self.q.heartbeat(job_id=worker["job_id"], worker_id="Mac-01",
                         generation=worker["generation"])
        self.q.set_paused(False)
        other = self.claim(worker="Mac-02")
        self.assertEqual(other["job_id"], second["job_id"])
        self.assertNotEqual(first["job_id"], other["job_id"])

    def test_cancel_revokes_leased_fence(self):
        job = self.add()
        leased = self.claim()
        cancelled = self.q.cancel(job["job_id"])
        self.assertEqual(cancelled["state"], "CANCELLED")
        with self.assertRaises(QueueError):
            self.q.complete(job_id=job["job_id"], worker_id="Mac-01",
                            generation=leased["generation"], result={"ok": True})
        self.assertEqual(self.q.cancel(job["job_id"])["state"], "CANCELLED")

    def test_parallel_claim_never_returns_same_lease_to_two_workers(self):
        job = self.add()
        def take(who):
            separate = StudioQueue(self.path, clock=self.clock)
            return separate.claim(worker_id=who, capabilities=["character_generate"])
        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(take, ["A", "B", "C", "D"]))
        claimed = [o for o in outcomes if o is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["job_id"], job["job_id"])

    def test_reopen_database_does_not_lose_jobs(self):
        job = self.add()
        independent = StudioQueue(self.path, clock=self.clock)
        self.assertEqual(independent.get(job["job_id"])["request_key"],
                         "episode-001:character")
        self.assertEqual(len(independent.list_jobs()), 1)

    def test_oversized_payload_and_nan_are_rejected(self):
        with self.assertRaises(QueueError):
            self.q.enqueue(kind="rig_review", request_key="big",
                           payload={"item": "x" * 40_000})
        with self.assertRaises(QueueError):
            self.q.enqueue(kind="rig_review", request_key="nan",
                           payload={"item": float("nan")})

    def test_cli_status_and_enqueue_no_worker_side_effects(self):
        payload = self.root / "payload.json"
        payload.write_text(json.dumps({"character_id": "bunny_v02"}))
        self.assertEqual(studioctl([
            "--db", str(self.path), "enqueue",
            "--kind", "character_generate", "--key", "demo:key",
            "--payload-file", str(payload),
        ]), 0)
        self.assertEqual(studioctl(["--db", str(self.path), "status"]), 0)
        self.assertEqual(self.q.status()["counts"]["QUEUED"], 1)

    def test_private_file_mode_on_unix(self):
        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
