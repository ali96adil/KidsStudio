"""Authenticated HTTPS two-process integration tests, no paid model calls."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest

from kidsstudio.coordinator_api import Coordinator, create_handler, TransportError
from kidsstudio.remote_worker import RemoteClient, RemoteAIWorker, RemoteWorkerError
from kidsstudio.studio_queue import StudioQueue


class FakeAI:
    def __init__(self):
        self.roles = []
    def complete(self, **kwargs):
        role = kwargs["role"]
        self.roles.append((role, kwargs["different_from"]))
        value = "تعلم الأرنب الألوان في الحديقة" if role == "script_draft" else (
            "REVISE: add more concrete child learning activity"
        )
        return {
            "provider_id": "writer" if role == "script_draft" else "critic",
            "model": "mock-model",
            "answer": value,
        }


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = StudioQueue(self.root / "pi.sqlite")
        self.queue.initialize()
        self.token = "only-for-local-unit-test-" + "s" * 40
        self.service = Coordinator(
            self.queue, self.root / "vault",
            {"mac-ai-01": (self.token, {"script_draft", "editorial_review"})},
        )

    def dispatch(self, kind, payload=None, worker_id="mac-ai-01"):
        return self.service.dispatch(kind, payload or {}, worker_id,
                                     frozenset({"script_draft", "editorial_review"}))

    def test_claim_complete_then_handoff_review_source_and_finish(self):
        self.queue.enqueue(
            kind="script_draft", request_key="episode-01",
            payload={"language": "ar", "topic": "الألوان", "auto_review": True},
        )
        first = self.dispatch("claim")["job"]
        self.assertEqual(first["kind"], "script_draft")
        response = self.dispatch("complete", {
            "job_id": first["job_id"], "generation": first["generation"],
            "answer": "أرنب يتعلم اللون الأصفر",
            "provider_id": "writer", "model": "local-draft",
        })
        self.assertEqual(response["status"], "COMPLETED")
        self.assertTrue((self.root / "vault" / first["job_id"] /
                         "generation_001.txt").exists())
        follow = self.dispatch("claim")["job"]
        self.assertEqual(follow["kind"], "editorial_review")
        self.assertNotIn("script_text", follow["payload"])
        source = self.dispatch("review-source", {
            "job_id": follow["job_id"], "generation": follow["generation"],
        })
        self.assertEqual(source["script_text"], "أرنب يتعلم اللون الأصفر")
        with self.assertRaises(TransportError):
            self.dispatch("complete", {
                "job_id": follow["job_id"], "generation": follow["generation"],
                "answer": "Self review", "provider_id": "writer", "model": "model",
            })
        done = self.dispatch("complete", {
            "job_id": follow["job_id"], "generation": follow["generation"],
            "answer": "REVISE: story is too brief", "provider_id": "critic",
            "model": "review-model",
        })
        self.assertEqual(done["status"], "COMPLETED")
        self.assertIsNone(self.dispatch("claim")["job"])

    def test_unauthorized_and_wrong_capability(self):
        self.assertIsNone(self.service.authorize("mac-ai-01", "Bearer invalid"))
        self.assertIsNone(self.service.authorize("unknown-worker", "Bearer " + self.token))
        self.assertEqual(self.service.authorize(
            "mac-ai-01", "Bearer " + self.token
        ), frozenset({"script_draft", "editorial_review"}))
        self.queue.enqueue(kind="godot_render", request_key="render1", payload={})
        self.assertIsNone(self.dispatch("claim")["job"])
        self.assertEqual(self.queue.status()["counts"]["QUEUED"], 1)

    def test_cancelled_job_cannot_publish_after_fence(self):
        job = self.queue.enqueue(
            kind="script_draft", request_key="cancelled",
            payload={"language": "ar", "topic": "color"},
        )
        claimed = self.dispatch("claim")["job"]
        self.queue.cancel(job["job_id"])
        with self.assertRaises(TransportError):
            self.dispatch("complete", {
                "job_id": claimed["job_id"], "generation": claimed["generation"],
                "answer": "Late result", "provider_id": "writer", "model": "local",
            })
        self.assertFalse((self.root / "vault" / job["job_id"]).exists())

    def test_review_source_refuses_changed_file(self):
        self.queue.enqueue(
            kind="script_draft", request_key="tamper",
            payload={"language": "ar", "topic": "ألوان", "auto_review": True},
        )
        first = self.dispatch("claim")["job"]
        self.dispatch("complete", {
            "job_id": first["job_id"], "generation": first["generation"],
            "answer": "original", "provider_id": "writer", "model": "local",
        })
        child = self.dispatch("claim")["job"]
        source = self.root / "vault" / first["job_id"] / "generation_001.txt"
        source.write_text("tampered", encoding="utf-8")
        with self.assertRaises(TransportError):
            self.dispatch("review-source", {
                "job_id": child["job_id"], "generation": child["generation"],
            })

    def test_only_allowlisted_worker_can_claim(self):
        with self.assertRaises(TransportError):
            Coordinator(self.queue, self.root / "vault2", {
                "mac-ai-01": ("short", {"script_draft"})
            })


@unittest.skipUnless(shutil.which("openssl"), "openssl required for ephemeral TLS certificate")
class NativeTLSIntegrationTests(CoordinatorTests):
    """Start genuine local HTTPS + transport; no external network or models."""

    def setUp(self):
        super().setUp()
        cert = self.root / "localhost.crt"
        key = self.root / "localhost.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-nodes", "-sha256", "-days", "1",
            "-keyout", str(key), "-out", str(cert),
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost",
        ], capture_output=True, check=True, timeout=20)
        self.http = ThreadingHTTPServer(
            ("127.0.0.1", 0), create_handler(self.service)
        )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        self.http.socket = ctx.wrap_socket(self.http.socket, server_side=True)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.base = "https://localhost:" + str(self.http.server_port)
        self.client = RemoteClient(
            self.base, worker_id="mac-ai-01", token=self.token,
            ca_file=str(cert),
        )

    def test_https_full_draft_review_cycle(self):
        self.queue.enqueue(
            kind="script_draft", request_key="episode-tls",
            payload={"language": "ar", "topic": "الألوان", "auto_review": True},
        )
        ai = FakeAI()
        worker = RemoteAIWorker(self.client, ai)
        result = worker.run_once()
        self.assertEqual(result["status"], "COMPLETED")
        child = worker.run_once()
        self.assertEqual(child["status"], "COMPLETED")
        self.assertEqual(ai.roles, [
            ("script_draft", None),
            ("editorial_review", "writer"),
        ])
        self.assertEqual(self.queue.status()["counts"]["COMPLETED"], 2)

    def test_wrong_bearer_token_cannot_claim(self):
        bad = RemoteClient(self.base, worker_id="mac-ai-01",
                           token="wrong-token-" + "x" * 35,
                           ca_file=str(self.root / "localhost.crt"))
        with self.assertRaises(RemoteWorkerError):
            bad.call("claim", {})
        self.assertEqual(self.queue.status()["counts"]["LEASED"], 0)

    def test_untrusted_certificate_fails_closed(self):
        bad = RemoteClient(self.base, worker_id="mac-ai-01", token=self.token)
        with self.assertRaises(RemoteWorkerError):
            bad.call("claim", {})

    def test_non_https_and_redirects_forbidden(self):
        with self.assertRaises(RemoteWorkerError):
            RemoteClient("http://127.0.0.1:8765",
                         worker_id="mac-ai-01", token=self.token)

    def test_https_media_only_worker_can_complete_pinned_video_metadata(self):
        from kidsstudio.remote_worker import RemoteClient
        self.service.workers["mac-media-01"] = (
            "media-secret-" + "m" * 40,
            frozenset({"godot_render"})
        )
        media = RemoteClient(
            self.base, worker_id="mac-media-01",
            token="media-secret-" + "m" * 40,
            ca_file=str(self.root / "localhost.crt"),
        )
        self.queue.enqueue(
            kind="godot_render", request_key="tls-media-01",
            payload={"recipe_id": "bunny_video_v1"},
        )
        claimed = media.call("claim", {})["job"]
        self.assertEqual(claimed["kind"], "godot_render")
        self.assertEqual(claimed["payload"], {"recipe_id": "bunny_video_v1"})
        result = media.call("complete-media", {
            "job_id": claimed["job_id"],
            "generation": claimed["generation"],
            "result_status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "artifact_sha256": "a" * 64,
            "artifact_bytes": 12345,
            "artifact_type": "mp4",
            "publication_approved": False,
        })
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(
            json.loads(self.queue.get(claimed["job_id"])["result_json"])[
                "publication_approved"
            ], False
        )

    def test_https_editorial_worker_cannot_complete_media_task(self):
        self.queue.enqueue(
            kind="godot_render", request_key="tls-media-02",
            payload={"recipe_id": "bunny_video_v1"},
        )
        self.assertIsNone(self.client.call("claim", {})["job"])
        self.assertEqual(self.queue.status()["counts"]["QUEUED"], 1)

    def test_cancelled_lease_rejects_remote_result(self):
        self.queue.enqueue(
            kind="script_draft", request_key="fenced-tls",
            payload={"language": "ar", "topic": "ألوان"},
        )
        claim = self.client.call("claim", {})["job"]
        self.queue.cancel(claim["job_id"])
        with self.assertRaises(RemoteWorkerError):
            self.client.call("complete", {
                "job_id": claim["job_id"], "generation": claim["generation"],
                "provider_id": "writer", "model": "local", "answer": "Late",
            })


if __name__ == "__main__":
    unittest.main()
