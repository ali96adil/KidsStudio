from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from kidsstudio.ai_router import AIConfig, AIRouterError, ChatRouter


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, amount):
        return self.body


class FakeOpener:
    def __init__(self, *, break_on=None):
        self.calls = []
        self.break_on = break_on
    def open(self, request, timeout):
        self.calls.append(request)
        if self.break_on and self.break_on in request.full_url:
            raise URLError("fake temporary connection failure")
        answer = "مراجعة مستقلة" if "review.example" in request.full_url else "قصة أصلية"
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": answer}}]
        }, ensure_ascii=False).encode("utf-8"))


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "providers.json"
        self.config = {
            "schema_version": 1,
            "providers": [
                {"id": "writing", "endpoint": "https://writing.example/v1/chat/completions",
                 "model": "test-free", "api_key_env": "KIDS_AI_WRITER_KEY",
                 "billing": "free", "max_output_tokens": 900},
                {"id": "reviewer", "endpoint": "https://review.example/v1/chat/completions",
                 "model": "test-paid", "api_key_env": "KIDS_AI_REVIEW_KEY",
                 "billing": "paid", "max_output_tokens": 1100},
                {"id": "backup", "endpoint": "http://127.0.0.1:12345/v1/chat/completions",
                 "model": "local", "api_key_env": None, "billing": "free",
                 "max_output_tokens": 700},
            ],
            "routes": {
                "script_draft": ["writing", "backup"],
                "editorial_review": ["reviewer", "backup"],
            },
        }
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.config), encoding="utf-8")

    def call(self, **kwargs):
        opener = kwargs.pop("opener", FakeOpener())
        router = ChatRouter(AIConfig(self.file), opener=opener)
        return router.complete(role="script_draft", system_prompt="Be safe",
                               user_prompt="Original educational bunny", **kwargs)

    def test_nonpaid_first_provider_and_no_plain_secret_in_response(self):
        with patch.dict(os.environ, {"KIDS_AI_WRITER_KEY": "secret-test-key"}):
            opener = FakeOpener()
            result = self.call(opener=opener)
        self.assertEqual(result["provider_id"], "writing")
        self.assertEqual(result["billing_policy"], "free")
        self.assertTrue(result["answer_sha256"])
        self.assertFalse(result["failover_used"])
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0].get_header("Authorization"),
                         "Bearer secret-test-key")
        self.assertNotIn("secret-test-key", str(result))
        self.assertEqual(
            json.loads(opener.calls[0].data)["max_tokens"], 800
        )

    def test_paid_model_never_used_by_default(self):
        router = ChatRouter(AIConfig(self.file), opener=FakeOpener())
        result = router.complete(
            role="editorial_review", system_prompt="Review safely",
            user_prompt="Sample", different_from="writing",
        )
        self.assertEqual(result["provider_id"], "backup")
        self.assertEqual(result["billing_policy"], "free")

    def test_explicit_paid_allowed_and_independent_route(self):
        with patch.dict(os.environ, {"KIDS_AI_REVIEW_KEY": "test-review-token"}):
            router = ChatRouter(AIConfig(self.file), opener=FakeOpener())
            result = router.complete(
                role="editorial_review", system_prompt="Review safely",
                user_prompt="Sample", different_from="writing",
                allow_paid=True,
            )
        self.assertEqual(result["provider_id"], "reviewer")
        self.assertEqual(result["model"], "test-paid")

    def test_fallback_not_used_unless_explicit(self):
        with patch.dict(os.environ, {"KIDS_AI_WRITER_KEY": "test"}):
            opener = FakeOpener(break_on="writing.example")
            with self.assertRaises(AIRouterError):
                self.call(opener=opener)
            self.assertEqual(len(opener.calls), 1)
            result = self.call(opener=opener, allow_fallback=True)
        self.assertEqual(result["provider_id"], "backup")
        self.assertTrue(result["failover_used"])

    def test_missing_key_is_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(AIRouterError, "KIDS_AI_WRITER_KEY"):
                self.call()

    def test_reject_unsafe_endpoint_and_undefined_route(self):
        for endpoint in (
            "http://public.example/v1/chat/completions",
            "https://user:pass@provider.example/v1/chat/completions",
            "http://127.0.0.1:1234/v1/chat/completions?secret=yes",
            "https://provider.example/admin",
        ):
            self.config["providers"][0]["endpoint"] = endpoint
            self.save()
            with self.subTest(endpoint=endpoint), self.assertRaises(AIRouterError):
                AIConfig(self.file)
        self.config["providers"][0]["endpoint"] = "https://writing.example/v1/chat/completions"
        self.config["routes"]["unapproved_publish"] = ["writing"]
        self.save()
        with self.assertRaises(AIRouterError):
            AIConfig(self.file)

    def test_review_requires_different_provider(self):
        self.config["routes"]["editorial_review"] = ["writing"]
        self.save()
        router = ChatRouter(AIConfig(self.file), opener=FakeOpener())
        with self.assertRaises(AIRouterError):
            router.complete(role="editorial_review", system_prompt="Review",
                            user_prompt="Sample", different_from="writing")

    def test_provider_errors_are_redacted(self):
        with patch.dict(os.environ, {"KIDS_AI_WRITER_KEY": "super-secret-token"}):
            opener = FakeOpener(break_on="writing.example")
            with self.assertRaises(AIRouterError) as issue:
                self.call(opener=opener)
        self.assertNotIn("super-secret-token", str(issue.exception))


if __name__ == "__main__":
    unittest.main()
