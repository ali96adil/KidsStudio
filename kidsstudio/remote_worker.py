"""Outbound-only TLS Mac worker client and one-shot editorial execution.

All network requests target a configured HTTPS Pi endpoint with normal
certificate verification (optional trusted private CA). No insecure flags,
redirects, proxies, uncontrolled filesystem operations or paid model use.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
from typing import Any
from urllib import request, error
from urllib.parse import urlparse

from .ai_router import AIConfig, ChatRouter, AIRouterError
from .local_worker import _prompts, WorkerError

MAX_MESSAGE = 45_000
SAFE_WORKER = re.compile(r"^[a-zA-Z0-9_./:-]{1,160}$")


class RemoteWorkerError(RuntimeError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RemoteClient:
    def __init__(self, base_url: str, *, worker_id: str, token: str,
                 ca_file: str | None = None, opener: Any | None = None):
        parsed = urlparse(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.fragment or
            parsed.query or parsed.path not in ("", "/") or
            parsed.port is None or not 1 <= parsed.port <= 65535):
            raise RemoteWorkerError("Pi endpoint must be explicit HTTPS host and port.")
        if not isinstance(worker_id, str) or not SAFE_WORKER.fullmatch(worker_id):
            raise RemoteWorkerError("Unsafe worker identity.")
        if not isinstance(token, str) or len(token) < 32:
            raise RemoteWorkerError("Worker token missing or too short.")
        self.base = base_url.rstrip("/")
        self.worker_id = worker_id
        self.token = token
        context = ssl.create_default_context(cafile=ca_file)
        self.opener = opener if opener is not None else request.build_opener(
            request.ProxyHandler({}), NoRedirect(),
            request.HTTPSHandler(context=context),
        )

    def call(self, operation: str, body: dict[str, Any]) -> dict[str, Any]:
        if operation not in ("claim", "heartbeat", "review-source", "complete", "complete-media", "fail", "pilot-readiness", "pilot-voice-lease-check", "montage-pre-execution-check", "request-private-upload", "private-upload-lease-check", "complete-private-upload"):
            raise RemoteWorkerError("Unknown Pi operation.")
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(data) > MAX_MESSAGE:
            raise RemoteWorkerError("Request too large.")
        req = request.Request(
            self.base + "/v1/" + operation, method="POST", data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.token,
                "X-Kidsstudio-Worker": self.worker_id,
            }
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                content = response.read(MAX_MESSAGE + 1)
            if len(content) > MAX_MESSAGE:
                raise RemoteWorkerError("Coordinator reply exceeds limit.")
            answer = json.loads(content)
            if not isinstance(answer, dict):
                raise RemoteWorkerError("Malformed coordinator reply.")
            server_time = answer.get("server_time")
            if type(server_time) not in (int, float) or abs(time.time() - server_time) > 120:
                raise RemoteWorkerError(
                    "Pi/Mac clock mismatch; synchronize clocks before job claims."
                )
            return answer
        except (error.HTTPError, error.URLError, TimeoutError, OSError,
                ValueError, KeyError, TypeError):
            # Never display bearer token, answer text, or server-provided body.
            raise RemoteWorkerError(
                "Secure coordinator request failed; inspect Pi/clock/cert/lease health."
            ) from None


class RemoteAIWorker:
    def __init__(self, coordinator: RemoteClient, ai: ChatRouter):
        self.pi = coordinator
        self.ai = ai

    def run_once(self) -> dict[str, Any]:
        response = self.pi.call("claim", {})
        job = response.get("job")
        if job is None:
            return {"status": "NO_ELIGIBLE_JOB"}
        if (not isinstance(job, dict) or
            job.get("kind") not in ("script_draft", "editorial_review") or
            not isinstance(job.get("payload"), dict) or
            not isinstance(job.get("job_id"), str) or
            type(job.get("generation")) is not int):
            raise RemoteWorkerError("Pi returned unsupported/invalid claim.")
        job_id, generation = job["job_id"], job["generation"]
        role = job["kind"]
        try:
            payload = dict(job["payload"])
            if role == "editorial_review" and "source_job_id" in payload:
                source = self.pi.call("review-source", {
                    "job_id": job_id, "generation": generation,
                })
                body = source.get("script_text")
                digest = source.get("source_answer_sha256")
                if (not isinstance(body, str) or
                    not isinstance(digest, str) or
                    hashlib.sha256(body.encode("utf-8")).hexdigest() != digest or
                    source.get("original_provider_id") !=
                        payload.get("original_provider_id")):
                    raise RemoteWorkerError("Reviewer source failed identity validation.")
                payload["script_text"] = body

            system, prompt, original = _prompts(role, payload)
            result = self.ai.complete(
                role=role, system_prompt=system, user_prompt=prompt,
                allow_paid=False, allow_fallback=False,
                different_from=original, max_output_tokens=1200,
            )
            self.pi.call("heartbeat", {
                "job_id": job_id, "generation": generation,
            })
            completed = self.pi.call("complete", {
                "job_id": job_id, "generation": generation,
                "provider_id": result["provider_id"],
                "model": result["model"],
                "answer": result["answer"],
            })
            if completed.get("status") != "COMPLETED":
                raise RemoteWorkerError("Pi did not acknowledge job completion.")
            return {"status": "COMPLETED", "job_id": job_id,
                    "provider_id": result["provider_id"]}
        except (AIRouterError, WorkerError, RemoteWorkerError,
                ValueError, OSError):
            try:
                self.pi.call("fail", {
                    "job_id": job_id, "generation": generation,
                    "error_code": "AI_WORKER_ERROR",
                })
            except RemoteWorkerError:
                pass  # coordinator may have already fenced or completed this lease
            return {"status": "FAILED", "job_id": job_id, "error_code": "AI_WORKER_ERROR"}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="studio-remote-worker")
    parser.add_argument("--coordinator", required=True,
                        help="https://YOUR-PI-HOST:8765")
    parser.add_argument("--ca-cert", help="Trusted Pi TLS certificate/CA")
    parser.add_argument("--providers", required=True,
                        help="Private local AI provider profile JSON")
    parser.add_argument("--worker-id", default="mac-ai-01")
    parser.add_argument("--token-env", default="KIDS_STUDIO_WORKER_TOKEN")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("Explicit --once is required. No background automation enabled.")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{4,90}", args.token_env):
        parser.error("Invalid token environment variable.")
    try:
        client = RemoteClient(
            args.coordinator, worker_id=args.worker_id,
            token=os.environ.get(args.token_env, ""), ca_file=args.ca_cert,
        )
        worker = RemoteAIWorker(client, ChatRouter(AIConfig(args.providers)))
        result = worker.run_once()
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["status"] == "FAILED" else 0
    except (RemoteWorkerError, AIRouterError, OSError, ValueError):
        print("Remote worker is not configured or coordinator is unavailable.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
