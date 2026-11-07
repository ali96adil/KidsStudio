from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.ai_router import AIConfig, AIRouterError, ChatRouter
from kidsstudio.local_worker import LocalAIWorker
from kidsstudio.omniroute_profile import (
    OmniRouteProfileError,
    build_omniroute_profile,
    describe_profile,
    main,
    write_private_profile,
)
from kidsstudio.studio_queue import StudioQueue


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size):
        return json.dumps({
            "choices": [{"message": {"content": "قصة أصلية تعليمية عن الألوان"}}]
        }, ensure_ascii=False).encode("utf-8")


class FakeOmniTransport:
    def __init__(self):
        self.requests = []

    def open(self, req, timeout):
        self.requests.append(req)
        return FakeResponse()


class OmniRouteProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / "private"
        self.private.mkdir(mode=0o700)
        self.path = self.private / "omniroute.json"

    def build(self, **kwargs):
        defaults = {
            "draft_model": "ollama/qwen3-local",
            "review_model": "lmstudio/gemma-local",
        }
        defaults.update(kwargs)
        return build_omniroute_profile(**defaults)

    def test_local_profile_has_explicit_non_auto_routes(self):
        profile = self.build()
        self.assertEqual(profile["schema_version"], 1)
        self.assertEqual(profile["routes"],
                         {"script_draft": ["omni_draft"],
                          "editorial_review": ["omni_review"]})
        self.assertTrue(all(p["billing"] == "free" for p in profile["providers"]))
        self.assertTrue(all(p["endpoint"] ==
                            "http://127.0.0.1:20128/v1/chat/completions"
                            for p in profile["providers"]))
        self.assertTrue(all(p["api_key_env"] == "KIDS_OMNIROUTE_KEY"
                            for p in profile["providers"]))
        self.assertFalse(describe_profile(profile, written=False)["automatic_route"])

    def test_single_draft_without_implicit_review(self):
        profile = self.build(review_model=None)
        self.assertEqual(list(profile["routes"]), ["script_draft"])
        self.assertEqual(len(profile["providers"]), 1)

    def test_external_model_must_be_explicitly_opted_in(self):
        with self.assertRaises(OmniRouteProfileError):
            self.build(draft_model="groq/example")
        profile = self.build(
            draft_model="groq/example", allow_external_profile=True)
        self.assertEqual(profile["providers"][0]["billing"], "paid")

    def test_external_profile_still_blocked_by_router_without_allow_paid(self):
        profile = self.build(
            draft_model="groq/example", review_model=None,
            allow_external_profile=True)
        write_private_profile(self.path, profile)
        router = ChatRouter(AIConfig(self.path), opener=FakeOmniTransport())
        with self.assertRaises(AIRouterError):
            router.complete(role="script_draft", system_prompt="System",
                            user_prompt="topic", allow_paid=False)

    def test_auto_and_combo_routes_disallowed(self):
        for model in ("auto/cheap", "auto/offline", "combos/cheap",
                      "combo/story", "omniroute/auto"):
            with self.subTest(model=model), self.assertRaises(OmniRouteProfileError):
                self.build(draft_model=model)

    def test_independent_review_rejects_same_upstream_prefix(self):
        with self.assertRaises(OmniRouteProfileError):
            self.build(review_model="ollama/second-local-model")

    def test_different_provider_ids_on_same_gateway(self):
        profile = self.build()
        self.assertNotEqual(profile["providers"][0]["id"],
                            profile["providers"][1]["id"])
        self.assertNotEqual(profile["providers"][0]["model"].split("/")[0],
                            profile["providers"][1]["model"].split("/")[0])

    def test_reject_malformed_model_and_limit(self):
        for model in ("", "qwen3", "ollama/", "../key",
                      "ollama/example?token=secret", "ollama/example\nHeader:bad"):
            with self.subTest(model=model), self.assertRaises(OmniRouteProfileError):
                self.build(draft_model=model)
        for limit in (0, 1201, True, "500"):
            with self.subTest(limit=limit), self.assertRaises(OmniRouteProfileError):
                self.build(max_output_tokens=limit)

    def test_explicit_private_write_and_exact_config_parse(self):
        profile = self.build(max_output_tokens=250)
        write_private_profile(self.path, profile)
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)
        loaded = AIConfig(self.path)
        self.assertEqual(loaded.providers["omni_review"]["max_output_tokens"], 250)
        self.assertNotIn("Bearer", self.path.read_text())

    def test_no_overwrite(self):
        write_private_profile(self.path, self.build())
        with self.assertRaises(FileExistsError):
            write_private_profile(self.path, self.build())
        self.assertEqual(AIConfig(self.path).routes["script_draft"], ["omni_draft"])

    def test_private_parent_required(self):
        self.private.chmod(0o755)
        with self.assertRaises(OmniRouteProfileError):
            write_private_profile(self.path, self.build())

    def test_link_path_forbidden(self):
        real = self.private / "real.json"
        real.write_text("{}")
        self.path.symlink_to(real)
        with self.assertRaises(OmniRouteProfileError):
            write_private_profile(self.path, self.build())

    def test_git_directory_forbidden(self):
        (self.private / ".git").mkdir()
        with self.assertRaises(OmniRouteProfileError):
            write_private_profile(self.path, self.build())

    def test_cli_dry_run_creates_no_file_and_does_no_network(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--draft-model", "ollama/local"])
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PROFILE_PREVIEW_ONLY")
        self.assertEqual(report["live_requests_performed"], 0)
        self.assertFalse(self.path.exists())
        self.assertFalse(report["publication_approved"])

    def test_cli_write_and_no_secrets_in_report_or_file(self):
        with patch.dict(os.environ, {"KIDS_OMNIROUTE_KEY": "SENSITIVE-TEST-KEY"}):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main([
                    "--draft-model", "ollama/local",
                    "--write-private-config", str(self.path),
                ])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "PRIVATE_PROFILE_WRITTEN")
        self.assertNotIn(str(self.private), output.getvalue())
        self.assertNotIn("SENSITIVE-TEST-KEY", output.getvalue())
        self.assertNotIn("SENSITIVE-TEST-KEY", self.path.read_text())

    def test_fake_gateway_request_is_pinned_and_bounded(self):
        write_private_profile(self.path, self.build(max_output_tokens=300))
        fake = FakeOmniTransport()
        router = ChatRouter(AIConfig(self.path), opener=fake)
        with patch.dict(os.environ, {"KIDS_OMNIROUTE_KEY": "TEST-NOT-REAL"}):
            answer = router.complete(
                role="script_draft", system_prompt="Safe original story",
                user_prompt="الألوان", max_output_tokens=1200)
            review = router.complete(
                role="editorial_review", system_prompt="Independent reviewer",
                user_prompt=answer["answer"], different_from=answer["provider_id"])
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(answer["provider_id"], "omni_draft")
        self.assertEqual(review["provider_id"], "omni_review")
        self.assertEqual(fake.requests[0].full_url,
                         "http://127.0.0.1:20128/v1/chat/completions")
        payload = json.loads(fake.requests[0].data)
        self.assertEqual(payload["model"], "ollama/qwen3-local")
        self.assertEqual(payload["max_tokens"], 300)
        self.assertEqual(json.loads(fake.requests[1].data)["model"],
                         "lmstudio/gemma-local")

    def test_fake_worker_pipeline_through_existing_router(self):
        write_private_profile(self.path, self.build())
        fake = FakeOmniTransport()
        router = ChatRouter(AIConfig(self.path), opener=fake)
        queue = StudioQueue(self.private / "queue.sqlite")
        queue.initialize()
        queue.enqueue(kind="script_draft", request_key="omni-offline-fixture",
                      payload={"language": "ar", "topic": "الألوان",
                               "auto_review": True})
        worker = LocalAIWorker(
            queue, router, self.private / "artifacts", worker_id="omni-fixture")
        with patch.dict(os.environ, {"KIDS_OMNIROUTE_KEY": "TEST-NOT-REAL"}):
            drafted = worker.run_once()
            reviewed = worker.run_once()
        self.assertEqual(drafted["state"], "COMPLETED")
        self.assertEqual(reviewed["state"], "COMPLETED")
        self.assertFalse(json.loads(drafted["result_json"])["publication_approved"])
        self.assertFalse(json.loads(reviewed["result_json"])["publication_approved"])
        self.assertEqual(len(fake.requests), 2)


if __name__ == "__main__":
    unittest.main()
