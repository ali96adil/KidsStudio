"""Minimal TLS-only Pi coordinator API for outbound-initiated Mac workers.

Run with a real TLS certificate, one environment-backed token per worker,
and local-only SQLite/artifact vault. No remote arbitrary code or publishing.
This protocol is a limited prototype for script drafting/review, NOT a general
remote execution interface.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import time
from typing import Any

from .studio_queue import StudioQueue, QueueError

MAX_REQUEST_BYTES = 32_768
MAX_ANSWER_BYTES = 20_000
ID = re.compile(r"^[a-f0-9]{32}$")
IDENT = re.compile(r"^[a-zA-Z0-9_./:-]{1,160}$")
ALLOWED_KINDS = frozenset({
    "script_draft", "editorial_review", "character_generate", "godot_render",
    "episode_assemble", "voice_synthesize", "ltx_animate"
})
MEDIA_KINDS = frozenset({"character_generate", "godot_render", "episode_assemble",
                         "voice_synthesize", "ltx_animate"})
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MEDIA_STATUSES = {
    "godot_render": frozenset({"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"}),
    "episode_assemble": frozenset({"VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"}),
    "voice_synthesize": frozenset({"VOICE_RENDERED_PENDING_QA"}),
    "ltx_animate": frozenset({"A2V_RENDERED_PENDING_QA"}),
    "character_generate": frozenset({
        "INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION",
        "REPAIR_BUDGET_EXHAUSTED", "BLOCKED_MANUAL_TRIAGE",
        "REJECTED_FINAL", "BLOCKED_MANUAL_REVIEW"
    }),
}



class TransportError(ValueError):
    pass


def _safe_vault(vault: str | Path) -> Path:
    dest = Path(vault).expanduser().resolve()
    if any((p / ".git").exists() for p in (dest, *dest.parents)):
        raise TransportError("Studio artifacts may not be stored inside Git.")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    return dest


def _write_exclusive(file: Path, data: bytes) -> None:
    file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(file.parent, 0o700)
    fd = os.open(str(file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class Coordinator:
    """Trusted coordinator used ONLY behind authenticated TLS routes."""

    def __init__(self, queue: StudioQueue, vault: str | Path,
                 workers: dict[str, tuple[str, set[str]]]):
        self.queue = queue
        self.vault = _safe_vault(vault)
        if not workers:
            raise TransportError("At least one preauthorized worker is required.")
        self.workers: dict[str, tuple[str, frozenset[str]]] = {}
        for worker_id, (token, capabilities) in workers.items():
            if (not IDENT.fullmatch(worker_id) or
                not isinstance(token, str) or len(token) < 32 or
                not isinstance(capabilities, (set, frozenset)) or
                not capabilities or
                not capabilities.issubset(ALLOWED_KINDS)):
                raise TransportError("Invalid token or worker capability policy.")
            self.workers[worker_id] = (token, frozenset(capabilities))
        if len({secret for secret, _ in self.workers.values()}) != len(self.workers):
            raise TransportError("Each worker must have an independent token.")

    def authorize(self, worker_id: Any, auth: str | None) -> frozenset[str] | None:
        if not isinstance(worker_id, str) or worker_id not in self.workers:
            return None
        if not isinstance(auth, str) or not auth.startswith("Bearer "):
            return None
        token, capabilities = self.workers[worker_id]
        return capabilities if secrets.compare_digest(auth[7:], token) else None

    def _lease(self, request: dict[str, Any], worker_id: str) -> dict[str, Any]:
        job_id, generation = request.get("job_id"), request.get("generation")
        if not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise TransportError("Invalid job ID.")
        if type(generation) is not int or generation < 1:
            raise TransportError("Invalid generation.")
        claimed = self.queue.get(job_id)
        if (claimed["state"] != "LEASED" or claimed["worker_id"] != worker_id or
            claimed["generation"] != generation or
            claimed["lease_expires"] <= self.queue.clock()):
            raise TransportError("Lease expired, cancelled, or owned by another worker.")
        return claimed

    def dispatch(self, action: str, request: dict[str, Any],
                 worker_id: str, capabilities: frozenset[str]) -> dict[str, Any]:
        if action == "pilot-readiness":
            # Explicit authenticated voice worker capability; read-only and
            # BEFORE the generic lease requirement. This never claims work.
            if "voice_synthesize" not in capabilities:
                raise TransportError("Pilot observation requires voice worker access.")
            from .live_pilot_gate import observe_live_scene_plan
            return observe_live_scene_plan(self.queue, request)
        if action == "claim":
            job = self.queue.claim(worker_id=worker_id,
                                   capabilities=sorted(capabilities), lease_seconds=600)
            if job is None:
                return {"job": None}
            return {"job": {
                "job_id": job["job_id"], "kind": job["kind"],
                "payload": json.loads(job["payload"]),
                "generation": job["generation"],
                "lease_expires": job["lease_expires"],
            }}

        leased = self._lease(request, worker_id)
        if leased["kind"] not in capabilities:
            raise TransportError("Worker capability does not permit this job.")

        if action == "heartbeat":
            self.queue.heartbeat(
                job_id=leased["job_id"], worker_id=worker_id,
                generation=leased["generation"], lease_seconds=600)
            return {"ok": True}

        if action == "fail":
            error_code = request.get("error_code")
            if error_code not in ("AI_WORKER_ERROR", "WORKER_EXECUTION_ERROR",
                                  "PROVIDER_UNAVAILABLE", "INVALID_REVIEW_SOURCE",
                                  "MEDIA_RECONCILIATION_REQUIRED",
                                  "MEDIA_CONFIGURATION_REJECTED"):
                raise TransportError("Invalid error code.")
            self.queue.fail(job_id=leased["job_id"], worker_id=worker_id,
                            generation=leased["generation"], error_code=error_code,
                            retryable=False)
            return {"status": "FAILED"}

        if action == "review-source":
            if leased["kind"] != "editorial_review":
                raise TransportError("Review source can only be accessed by reviewer.")
            payload = json.loads(leased["payload"])
            source_id = payload.get("source_job_id")
            if not isinstance(source_id, str) or not ID.fullmatch(source_id):
                raise TransportError("Review source missing valid parent.")
            parent = self.queue.get(source_id)
            if parent["state"] != "COMPLETED" or parent["kind"] != "script_draft":
                raise TransportError("Draft not completed.")
            previous = json.loads(parent["result_json"])
            if (previous.get("next_review_job_id") != leased["job_id"] or
                previous.get("status") != "DRAFTED_UNREVIEWED" or
                previous.get("provider_id") != payload.get("original_provider_id") or
                previous.get("artifact_sha256") != payload.get("source_answer_sha256")):
                raise TransportError("Review lineage mismatch.")
            file = self.vault / source_id / ("generation_%03d.txt" % parent["generation"])
            if not file.is_file() or file.stat().st_size > MAX_ANSWER_BYTES:
                raise TransportError("Source artifact unavailable.")
            raw = file.read_bytes()
            if hashlib.sha256(raw).hexdigest() != payload["source_answer_sha256"]:
                raise TransportError("Source artifact changed.")
            return {"script_text": raw.decode("utf-8"),
                    "original_provider_id": payload["original_provider_id"],
                    "source_answer_sha256": payload["source_answer_sha256"]}

        if action == "complete-media":
            if leased["kind"] not in MEDIA_KINDS:
                raise TransportError("Media completion requires a media lease.")
            if set(request) != {
                "job_id", "generation", "result_status",
                "artifact_sha256", "artifact_bytes",
                "artifact_type", "publication_approved",
            }:
                raise TransportError("Unexpected media result fields.")
            status = request["result_status"]
            digest = request["artifact_sha256"]
            bytes_count = request["artifact_bytes"]
            expected_type = (
                ("wav" if leased["kind"] == "voice_synthesize" else
                 "mp4" if leased["kind"] in ("godot_render", "episode_assemble", "ltx_animate")
                 else "rig_report")
            )
            if (
                status not in MEDIA_STATUSES[leased["kind"]]
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                or type(bytes_count) is not int
                or not 1 <= bytes_count <= 20_000_000_000
                or request["artifact_type"] != expected_type
                or request["publication_approved"] is not False
            ):
                raise TransportError("Media provenance or approval gate failed.")
            result = {
                "status": status,
                "artifact_sha256": digest,
                "artifact_bytes": bytes_count,
                "artifact_type": expected_type,
                "worker_id": worker_id,
                "publication_approved": False,
                "artifact_stored_on_mac": True,
            }
            done = self.queue.complete(
                job_id=leased["job_id"], worker_id=worker_id,
                generation=leased["generation"], result=result,
            )
            return {
                "status": done["state"],
                "job_id": done["job_id"],
                "artifact_sha256": digest,
            }

        if action != "complete":
            raise TransportError("Unknown action.")
        if leased["kind"] not in ("script_draft", "editorial_review"):
            raise TransportError("Only editorial work may use this completion endpoint.")
        provider = request.get("provider_id")
        model = request.get("model")
        answer = request.get("answer")
        if (not isinstance(provider, str) or
            not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", provider) or
            not isinstance(model, str) or not 1 <= len(model) <= 120 or
            not isinstance(answer, str) or not answer.strip() or
            len(answer.encode("utf-8")) > MAX_ANSWER_BYTES):
            raise TransportError("Invalid AI result metadata/content.")
        payload = json.loads(leased["payload"])
        if (leased["kind"] == "editorial_review" and
            provider == payload.get("original_provider_id")):
            raise TransportError("Reviewer must use a distinct provider.")

        source = answer.encode("utf-8")
        digest = hashlib.sha256(source).hexdigest()
        target = self.vault / leased["job_id"] / (
            "generation_%03d.txt" % leased["generation"])
        _write_exclusive(target, source)
        result = {
            "status": "DRAFTED_UNREVIEWED" if leased["kind"] == "script_draft"
                      else "EDITORIAL_REVIEW_UNVERIFIED",
            "provider_id": provider,
            "model": model,
            "artifact_sha256": digest,
            "artifact_manifest": str(target),
            "publication_approved": False,
        }
        if leased["kind"] == "script_draft" and payload.get("auto_review", False):
            done = self.queue.complete_draft_and_enqueue_review(
                job_id=leased["job_id"], worker_id=worker_id,
                generation=leased["generation"], result=result,
                language=payload["language"],
            )
        else:
            done = self.queue.complete(
                job_id=leased["job_id"], worker_id=worker_id,
                generation=leased["generation"], result=result,
            )
        return {
            "status": done["state"],
            "job_id": done["job_id"],
            "artifact_sha256": digest,
        }


def create_handler(coordinator: Coordinator):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KidsStudioCoordinator/0.1"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            # Do not log bearer tokens, submitted prompts, raw answer or URLs.
            return

        def _reply(self, status: int, obj: dict[str, Any]) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = self.path
            if path not in ("/v1/claim", "/v1/heartbeat", "/v1/review-source",
                            "/v1/complete", "/v1/complete-media", "/v1/fail",
                            "/v1/pilot-readiness"):
                self._reply(404, {"error": "NOT_FOUND"})
                return
            length = self.headers.get("Content-Length")
            if not length or not length.isdigit() or not 1 <= int(length) <= MAX_REQUEST_BYTES:
                self._reply(413, {"error": "INVALID_SIZE"})
                return
            worker = self.headers.get("X-KidsStudio-Worker")
            capabilities = coordinator.authorize(worker, self.headers.get("Authorization"))
            if capabilities is None:
                self._reply(401, {"error": "NOT_AUTHORIZED"})
                return
            if self.headers.get("Content-Type") != "application/json":
                self._reply(415, {"error": "INVALID_CONTENT_TYPE"})
                return
            try:
                value = json.loads(self.rfile.read(int(length)))
                if not isinstance(value, dict):
                    raise TransportError("Expected JSON object.")
                result = coordinator.dispatch(path.split("/")[-1], value,
                                               worker, capabilities)
                result["server_time"] = time.time()
                self._reply(200, result)
            except (QueueError, TransportError, OSError, ValueError,
                    TypeError, UnicodeError):
                self._reply(409, {"error": "REQUEST_REJECTED"})
    return Handler


def serve(queue: StudioQueue, *, bind: str, port: int,
          cert: str, key: str, vault: str | Path,
          workers: dict[str, tuple[str, set[str]]]) -> None:
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise TransportError("Invalid port.")
    control = Coordinator(queue, vault, workers)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert, keyfile=key)
    server = ThreadingHTTPServer((bind, port), create_handler(control))
    server.daemon_threads = True
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="studio-coordinator")
    parser.add_argument("--db", required=True)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tls-cert", required=True)
    parser.add_argument("--tls-key", required=True)
    parser.add_argument("--worker-id", default="mac-ai-01")
    parser.add_argument("--token-env", default="KIDS_STUDIO_WORKER_TOKEN")
    parser.add_argument("--worker-kinds", default="script_draft,editorial_review",
                        help="Comma-separated Pi-approved job kinds for this worker")
    args = parser.parse_args(argv)
    if not isinstance(args.token_env, str) or not re.fullmatch(
        r"[A-Z][A-Z0-9_]{4,90}", args.token_env
    ):
        parser.error("Invalid token environment variable.")
    token = os.environ.get(args.token_env, "")
    if len(token) < 32:
        parser.error("Worker token environment variable must contain 32+ characters.")
    kinds = set(args.worker_kinds.split(","))
    if not kinds or not kinds.issubset(ALLOWED_KINDS):
        parser.error("Worker capabilities must be explicitly allowlisted.")
    serve(StudioQueue(args.db), bind=args.bind, port=args.port,
          cert=args.tls_cert, key=args.tls_key, vault=args.vault,
          workers={args.worker_id: (token, kinds)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
