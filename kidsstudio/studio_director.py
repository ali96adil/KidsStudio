"""Private evidence-backed proposal ledger for the local Studio Director.

This module records proposals and explicit decisions. It does not research,
call a model, contact a service, execute a job, spend money, or publish media.
Accepted work can be copied into the existing allowlisted SQLite queue.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Iterator

from .studio_queue import KINDS, QueueError, StudioQueue

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z")
_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SENSITIVE = re.compile(r"password|secret|api.?key|access.?token|refresh.?token|private.?key", re.I)
_OUTCOMES = {"ACCEPTED", "REJECTED", "DEFERRED"}
_MANUAL_OUTCOMES = {"REJECTED", "DEFERRED"}
_MAX_JSON_BYTES = 32_768
_SECRET_VALUE = re.compile(r"(?:bearer\s+\S+|(?:token|secret|password|api[_-]?key)=\S+|://[^/@]+:[^/@]+@)", re.I)
_EVIDENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
_RESULT_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
INTERNAL_TRIAL_POLICY = "internal-script-draft-v1"
_PIPELINE_CAPABILITY = object()


def _pack(value: object, label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")

    def inspect(node: object, depth: int = 0) -> None:
        if depth > 15:
            raise ValueError(f"{label} nesting exceeds the safety limit")
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str) or _SENSITIVE.search(key):
                    raise ValueError(f"{label} contains a disallowed sensitive field")
                inspect(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                inspect(item, depth + 1)

    inspect(value)
    try:
        packed = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not valid JSON data") from exc
    if len(packed.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds {_MAX_JSON_BYTES} UTF-8 bytes")
    return packed


def _text(value: object, label: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f"invalid {label}")
    clean = value.strip()
    if _SECRET_VALUE.search(clean):
        raise ValueError(f"{label} appears to contain a credential")
    return clean


def _result_code(value: object) -> str:
    """Keep untrusted worker result labels bounded and free of arbitrary text."""
    if not isinstance(value, str) or not _RESULT_CODE.fullmatch(value):
        raise ValueError("queue result status must be a bounded uppercase code")
    return value


def _proposal_document(document: object) -> dict:
    if not isinstance(document, dict):
        raise ValueError("proposal must be a JSON object")
    required = {"title", "summary", "audience", "learning_objective",
                "alternatives", "evidence", "job_kind", "job_payload"}
    optional = {"supersedes_id", "effort_estimate", "risks"}
    if set(document) - (required | optional) or required - set(document):
        raise ValueError("proposal fields do not match the supported schema")
    title = _text(document["title"], "title", 200)
    summary = _text(document["summary"], "summary", 4000)
    audience = _text(document["audience"], "audience", 100)
    objective = _text(document["learning_objective"], "learning objective", 1000)
    kind = document["job_kind"]
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("job_kind is not an existing allowlisted queue kind")
    payload_json = _pack(document["job_payload"], "job_payload")
    payload = json.loads(payload_json)
    if "studio_proposal_id" in payload or "studio_decision_id" in payload:
        raise ValueError("job_payload contains reserved Director fields")

    alternatives = document["alternatives"]
    if not isinstance(alternatives, list) or not 2 <= len(alternatives) <= 10:
        raise ValueError("at least two and at most ten alternatives are required")
    clean_alternatives = []
    seen_options = set()
    for item in alternatives:
        if not isinstance(item, dict) or set(item) != {"option", "rationale"}:
            raise ValueError("each alternative needs option and rationale")
        option = _text(item["option"], "alternative", 200)
        rationale = _text(item["rationale"], "alternative rationale", 1000)
        if option.casefold() in seen_options:
            raise ValueError("alternative options must be distinct")
        seen_options.add(option.casefold())
        clean_alternatives.append({"option": option, "rationale": rationale})

    evidence = document["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
        raise ValueError("one to twenty evidence references are required")
    clean_evidence = []
    seen_evidence_ids = set()
    for index, item in enumerate(evidence, 1):
        allowed_fields = {"source", "observed_at", "claim", "sha256", "id", "content"}
        required_fields = {"source", "observed_at", "claim", "sha256"}
        if (not isinstance(item, dict) or set(item) - allowed_fields
                or required_fields - set(item)):
            raise ValueError("each evidence reference needs source, observed_at, claim and sha256")
        digest = item["sha256"]
        if digest is not None and (not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ValueError("evidence sha256 must be 64 lowercase hex characters or null")
        content = item.get("content")
        if content is not None:
            content = _text(content, "evidence content", 6000)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest is not None and digest != content_hash:
                raise ValueError("evidence content does not match its supplied sha256")
            digest = content_hash
            verification = "LOCAL_CONTENT_HASH_VERIFIED"
        else:
            verification = "CALLER_SUPPLIED_UNVERIFIED"
        evidence_id = item.get("id", f"evidence_{index}")
        if not isinstance(evidence_id, str) or not _EVIDENCE_ID.fullmatch(evidence_id):
            raise ValueError("invalid evidence id")
        if evidence_id in seen_evidence_ids:
            raise ValueError("evidence ids must be unique")
        seen_evidence_ids.add(evidence_id)
        clean_evidence.append({
            "id": evidence_id,
            "source": _text(item["source"], "evidence source", 500),
            "observed_at": _text(item["observed_at"], "evidence date", 80),
            "claim": _text(item["claim"], "evidence claim", 2000),
            "sha256": digest,
            "verification": verification,
            **({"content": content} if content is not None else {}),
        })
    effort = document.get("effort_estimate", {"hours": None, "basis": "Not estimated."})
    if (not isinstance(effort, dict) or set(effort) != {"hours", "basis"}
            or (effort["hours"] is not None and
                (type(effort["hours"]) not in (int, float) or
                 not 0 <= effort["hours"] <= 200))):
        raise ValueError("effort_estimate must have hours (0..200 or null) and basis")
    clean_effort = {"hours": effort["hours"], "basis": _text(effort["basis"], "effort basis", 500)}
    risks = document.get("risks", ["Estimate not independently qualified."])
    if not isinstance(risks, list) or not 1 <= len(risks) <= 10:
        raise ValueError("one to ten risks are required")
    clean_risks = [_text(item, "risk", 500) for item in risks]
    supersedes = document.get("supersedes_id")
    if supersedes is not None and (not isinstance(supersedes, str) or not _ID.fullmatch(supersedes)):
        raise ValueError("invalid supersedes_id")
    return {
        "schema_version": 1,
        "title": title,
        "summary": summary,
        "audience": audience,
        "learning_objective": objective,
        "alternatives": clean_alternatives,
        "evidence": clean_evidence,
        "effort_estimate": clean_effort,
        "risks": clean_risks,
        "job_kind": kind,
        "job_payload": payload,
        "supersedes_id": supersedes,
    }


class StudioDirector:
    """Append-only local proposal/decision store with idempotent queue handoff."""

    def __init__(self, database: str | Path):
        self.path = Path(os.path.abspath(os.path.expanduser(str(database))))
        if self.path.suffix not in {".db", ".sqlite"}:
            raise ValueError("Director database must end in .db or .sqlite")
        if any((parent / ".git").exists() for parent in (self.path.parent, *self.path.parents)):
            raise ValueError("Director database must remain outside Git")
        self._extensions_ready = False

    def _check_path(self, *, allow_missing: bool = False) -> None:
        parent = self.path.parent
        if (not parent.is_dir() or parent.stat().st_mode & 0o077
                or any(part.is_symlink() for part in (parent, *parent.parents))):
            raise ValueError("existing owner-private database directory required")
        if hasattr(os, "getuid") and parent.stat().st_uid != os.getuid():
            raise ValueError("database directory must be owned by the current user")
        if self.path.is_symlink():
            raise ValueError("database symlink forbidden")
        if not self.path.exists():
            if allow_missing:
                return
            raise ValueError("Director database is not initialized")
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("Director database must be a private regular file")

    def initialize(self) -> None:
        self._check_path(allow_missing=True)
        if self.path.exists():
            raise FileExistsError("Director database already exists")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with self._connection() as db:
                db.execute("""CREATE TABLE proposals (
                        proposal_id TEXT PRIMARY KEY,
                        request_key TEXT NOT NULL UNIQUE,
                        proposal_json TEXT NOT NULL,
                        proposal_sha256 TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )""")
                db.execute("""CREATE TABLE decisions (
                        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(proposal_id),
                        outcome TEXT NOT NULL CHECK(outcome IN ('ACCEPTED','REJECTED','DEFERRED')),
                        actor TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        evidence_sha256 TEXT NOT NULL,
                        decided_at REAL NOT NULL
                    )""")
                db.execute("""CREATE TABLE dispatches (
                        proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
                        decision_id INTEGER NOT NULL UNIQUE REFERENCES decisions(decision_id),
                        queue_job_id TEXT NOT NULL,
                        request_key TEXT NOT NULL UNIQUE,
                        created_at REAL NOT NULL,
                        PRIMARY KEY(proposal_id, decision_id)
                    )""")
                self._create_extension_tables(db)
            self._extensions_ready = True
        except Exception:
            self.path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _create_extension_tables(db: sqlite3.Connection) -> None:
        db.execute("""CREATE TABLE IF NOT EXISTS ai_pipeline (
            proposal_id TEXT PRIMARY KEY REFERENCES proposals(proposal_id),
            generator_provider_id TEXT NOT NULL,
            generator_model TEXT NOT NULL,
            generator_prompt_sha256 TEXT NOT NULL,
            generator_response_sha256 TEXT NOT NULL,
            reviewer_provider_id TEXT,
            reviewer_model TEXT,
            reviewer_prompt_sha256 TEXT,
            reviewer_response_sha256 TEXT,
            review_verdict TEXT,
            review_rationale TEXT,
            evidence_supported INTEGER,
            blocking_issues_json TEXT,
            assessment_sha256 TEXT,
            created_at REAL NOT NULL,
            reviewed_at REAL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS policy_approvals (
            decision_id INTEGER PRIMARY KEY REFERENCES decisions(decision_id),
            proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(proposal_id),
            policy_id TEXT NOT NULL,
            assessment_sha256 TEXT NOT NULL,
            created_at REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS results (
            proposal_id TEXT PRIMARY KEY REFERENCES proposals(proposal_id),
            decision_id INTEGER NOT NULL UNIQUE REFERENCES decisions(decision_id),
            queue_job_id TEXT NOT NULL UNIQUE,
            queue_state TEXT NOT NULL CHECK(queue_state IN ('COMPLETED','FAILED','CANCELLED')),
            result_status TEXT NOT NULL,
            result_sha256 TEXT NOT NULL,
            recorded_at REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS request_bindings (
            proposal_id TEXT PRIMARY KEY REFERENCES proposals(proposal_id),
            request_sha256 TEXT NOT NULL,
            created_at REAL NOT NULL
        )""")

    def _ensure_extensions(self) -> None:
        """Add result/assessment tables to existing private v1 ledgers."""
        if self._extensions_ready:
            return
        self._check_path()
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            self._create_extension_tables(db)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        self._extensions_ready = True

    @contextmanager
    def _connection(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        self._check_path()
        if readonly:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        else:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        try:
            if not readonly:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if not readonly:
                db.execute("COMMIT")
        except Exception:
            if not readonly and db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def propose(self, *, request_key: str, proposal: object,
                _generation_response: dict | None = None,
                _request_sha256: str | None = None,
                _pipeline_capability: object | None = None) -> dict:
        self._ensure_extensions()
        if not isinstance(request_key, str) or not _KEY.fullmatch(request_key):
            raise ValueError("invalid proposal request key")
        clean = _proposal_document(proposal)
        packed = _pack(clean, "proposal")
        digest = hashlib.sha256(packed.encode("utf-8")).hexdigest()
        generation_values = None
        if _generation_response is not None:
            if _pipeline_capability is not _PIPELINE_CAPABILITY:
                raise ValueError("AI provenance may only be recorded by the Director pipeline")
            if not isinstance(_generation_response, dict):
                raise ValueError("writer provenance must be an object")
            provider = _text(_generation_response.get("provider_id"), "writer provider", 64)
            model = _text(_generation_response.get("model"), "writer model", 120)
            if (_generation_response.get("billing_policy") != "free"
                    or _generation_response.get("failover_used") is not False):
                raise ValueError("Director generation requires one no-fallback free provider")
            hashes = (_generation_response.get("prompt_sha256"),
                      _generation_response.get("answer_sha256"))
            if any(not isinstance(value, str) or not _SHA.fullmatch(value) for value in hashes):
                raise ValueError("missing writer provenance digest")
            if not isinstance(_request_sha256, str) or not _SHA.fullmatch(_request_sha256):
                raise ValueError("generated proposal requires a request digest")
            generation_values = (provider, model, *hashes)
        elif _request_sha256 is not None:
            raise ValueError("request digest requires writer provenance")
        with self._connection() as db:
            existing = db.execute("SELECT * FROM proposals WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["proposal_sha256"] != digest:
                    raise ValueError("proposal request key was already used for different content")
                if generation_values is not None:
                    binding = db.execute("SELECT request_sha256 FROM request_bindings WHERE proposal_id=?",
                                         (existing["proposal_id"],)).fetchone()
                    pipeline = db.execute("SELECT generator_provider_id,generator_model,"
                                          "generator_prompt_sha256,generator_response_sha256 "
                                          "FROM ai_pipeline WHERE proposal_id=?",
                                          (existing["proposal_id"],)).fetchone()
                    if (binding is None or binding["request_sha256"] != _request_sha256
                            or pipeline is None or tuple(pipeline) != generation_values):
                        raise ValueError("existing generated proposal provenance differs")
                return {"proposal_id": existing["proposal_id"], "proposal_sha256": digest,
                        "status": "PROPOSAL_EXISTS"}
            if clean["supersedes_id"] is not None and not db.execute(
                    "SELECT 1 FROM proposals WHERE proposal_id=?", (clean["supersedes_id"],)).fetchone():
                raise ValueError("superseded proposal not found")
            proposal_id = secrets.token_hex(16)
            db.execute("INSERT INTO proposals VALUES(?,?,?,?,?)",
                       (proposal_id, request_key, packed, digest, time.time()))
            if generation_values is not None:
                db.execute("INSERT INTO ai_pipeline(proposal_id,generator_provider_id,generator_model,"
                           "generator_prompt_sha256,generator_response_sha256,created_at) "
                           "VALUES(?,?,?,?,?,?)", (proposal_id, *generation_values, time.time()))
                db.execute("INSERT INTO request_bindings VALUES(?,?,?)",
                           (proposal_id, _request_sha256, time.time()))
        return {"proposal_id": proposal_id, "proposal_sha256": digest,
                "status": "PROPOSAL_RECORDED"}

    def decide(self, *, proposal_id: str, outcome: str, actor: str, rationale: str) -> dict:
        self._ensure_extensions()
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        if not isinstance(outcome, str) or outcome not in _MANUAL_OUTCOMES:
            raise ValueError("manual actor labels may reject or defer, never accept or impersonate the owner")
        actor = _text(actor, "decision actor", 120)
        rationale = _text(rationale, "decision rationale", 4000)
        with self._connection() as db:
            proposal = db.execute("SELECT proposal_json FROM proposals WHERE proposal_id=?",
                                  (proposal_id,)).fetchone()
            if proposal is None:
                raise ValueError("proposal not found")
            data = json.loads(proposal["proposal_json"])
            evidence_json = _pack({"evidence": data["evidence"]}, "evidence")
            evidence_sha = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
            old = db.execute("SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,)).fetchone()
            if old:
                if (old["outcome"], old["actor"], old["rationale"], old["evidence_sha256"]) == (
                        outcome, actor, rationale, evidence_sha):
                    return {"decision_id": old["decision_id"], "status": "DECISION_EXISTS",
                            "outcome": outcome}
                raise ValueError("decision is immutable; create a successor proposal with new evidence")
            cur = db.execute("INSERT INTO decisions(proposal_id,outcome,actor,rationale,evidence_sha256,decided_at) "
                             "VALUES(?,?,?,?,?,?)",
                             (proposal_id, outcome, actor, rationale, evidence_sha, time.time()))
            decision_id = int(cur.lastrowid)
        return {"decision_id": decision_id, "status": "DECISION_RECORDED", "outcome": outcome,
                "evidence_sha256": evidence_sha, "owner_publication_approval": False}

    def enqueue_accepted(self, *, proposal_id: str, queue_database: str | Path) -> dict:
        self._ensure_extensions()
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        with self._connection(readonly=True) as db:
            row = db.execute("SELECT p.proposal_json,d.decision_id,d.outcome,pa.policy_id "
                             "FROM proposals p JOIN decisions d USING(proposal_id) "
                             "LEFT JOIN policy_approvals pa USING(proposal_id) "
                             "WHERE p.proposal_id=?",
                             (proposal_id,)).fetchone()
            if (row is None or row["outcome"] != "ACCEPTED"
                    or row["policy_id"] != INTERNAL_TRIAL_POLICY):
                raise ValueError("only an internally policy-approved trial can enqueue work")
            proposal = json.loads(row["proposal_json"])
            decision_id = int(row["decision_id"])
            if proposal["job_kind"] != "script_draft":
                raise ValueError("internal trial policy permits script drafts only")
        request_key = f"director-{proposal_id}-{decision_id}"
        payload = dict(proposal["job_payload"])
        payload.update({"studio_proposal_id": proposal_id, "studio_decision_id": decision_id,
                        "studio_no_paid": True, "studio_trial_policy": INTERNAL_TRIAL_POLICY})
        queue = StudioQueue(queue_database)
        job = queue.enqueue(kind=proposal["job_kind"], request_key=request_key, payload=payload)
        with self._connection() as db:
            prior = db.execute("SELECT queue_job_id FROM dispatches WHERE decision_id=?",
                               (decision_id,)).fetchone()
            if prior and prior["queue_job_id"] != job["job_id"]:
                raise QueueError("decision is linked to a different queue job")
            db.execute("INSERT OR IGNORE INTO dispatches VALUES(?,?,?,?,?)",
                       (proposal_id, decision_id, job["job_id"], request_key, time.time()))
        return {"status": "WORK_ENQUEUED", "proposal_id": proposal_id,
                "decision_id": decision_id, "queue_job_id": job["job_id"],
                "queue_state": job["state"], "execution_started": False,
                "publication_approved": False}

    def get(self, *, proposal_id: str) -> dict:
        self._ensure_extensions()
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        with self._connection(readonly=True) as db:
            proposal = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if proposal is None:
                raise ValueError("proposal not found")
            decision = db.execute("SELECT decision_id,outcome,actor,rationale,evidence_sha256,decided_at "
                                  "FROM decisions WHERE proposal_id=?", (proposal_id,)).fetchone()
            dispatch = db.execute("SELECT queue_job_id,request_key,created_at FROM dispatches "
                                  "WHERE proposal_id=?", (proposal_id,)).fetchone()
            pipeline = db.execute("SELECT * FROM ai_pipeline WHERE proposal_id=?",
                                  (proposal_id,)).fetchone()
            policy = db.execute("SELECT policy_id,assessment_sha256,created_at FROM policy_approvals "
                                "WHERE proposal_id=?", (proposal_id,)).fetchone()
            result = db.execute("SELECT queue_job_id,queue_state,result_status,result_sha256,recorded_at "
                                "FROM results WHERE proposal_id=?", (proposal_id,)).fetchone()
        return {"proposal_id": proposal_id, "proposal_sha256": proposal["proposal_sha256"],
                "proposal": json.loads(proposal["proposal_json"]),
                "decision": dict(decision) if decision else None,
                "dispatch": dict(dispatch) if dispatch else None,
                "ai_pipeline": dict(pipeline) if pipeline else None,
                "internal_policy_approval": dict(policy) if policy else None,
                "result": dict(result) if result else None,
                "evidence_verified": False, "owner_publication_approval": False}

    def record_generation(self, *, proposal_id: str, response: dict,
                          _pipeline_capability: object | None = None) -> None:
        """Bind a proposal to the local-free writer's exact response metadata."""
        if _pipeline_capability is not _PIPELINE_CAPABILITY:
            raise ValueError("AI provenance may only be recorded by the Director pipeline")
        self._ensure_extensions()
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        provider = _text(response.get("provider_id"), "writer provider", 64)
        model = _text(response.get("model"), "writer model", 120)
        if response.get("billing_policy") != "free" or response.get("failover_used") is not False:
            raise ValueError("Director generation requires one no-fallback free provider")
        for key in ("prompt_sha256", "answer_sha256"):
            if not isinstance(response.get(key), str) or not _SHA.fullmatch(response[key]):
                raise ValueError("missing writer provenance digest")
        values = (provider, model, response["prompt_sha256"], response["answer_sha256"])
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone():
                raise ValueError("proposal not found")
            old = db.execute("SELECT * FROM ai_pipeline WHERE proposal_id=?", (proposal_id,)).fetchone()
            if old:
                if tuple(old[k] for k in ("generator_provider_id", "generator_model",
                                          "generator_prompt_sha256", "generator_response_sha256")) != values:
                    raise ValueError("proposal already has different writer provenance")
                return
            db.execute("INSERT INTO ai_pipeline(proposal_id,generator_provider_id,generator_model,"
                       "generator_prompt_sha256,generator_response_sha256,created_at) "
                       "VALUES(?,?,?,?,?,?)", (proposal_id, *values, time.time()))

    def record_agent_review(self, *, proposal_id: str, response: dict,
                            review: dict,
                            _pipeline_capability: object | None = None) -> dict:
        """Store a distinct local-free review of the exact proposal version."""
        if _pipeline_capability is not _PIPELINE_CAPABILITY:
            raise ValueError("independent reviews may only be recorded by the Director pipeline")
        self._ensure_extensions()
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        reviewer = _text(response.get("provider_id"), "reviewer provider", 64)
        model = _text(response.get("model"), "reviewer model", 120)
        if response.get("billing_policy") != "free" or response.get("failover_used") is not False:
            raise ValueError("Director review requires one no-fallback free provider")
        for key in ("prompt_sha256", "answer_sha256"):
            if not isinstance(response.get(key), str) or not _SHA.fullmatch(response[key]):
                raise ValueError("missing reviewer provenance digest")
        if not isinstance(review, dict) or set(review) != {
                "verdict", "rationale", "evidence_supported", "blocking_issues"}:
            raise ValueError("review response schema mismatch")
        verdict = review["verdict"]
        rationale = _text(review["rationale"], "review rationale", 2000)
        if not isinstance(verdict, str) or verdict not in {"PASS", "REVISE", "BLOCK"}:
            raise ValueError("unsupported review verdict")
        if type(review["evidence_supported"]) is not bool:
            raise ValueError("evidence_supported must be boolean")
        issues = review["blocking_issues"]
        if not isinstance(issues, list) or len(issues) > 10:
            raise ValueError("blocking_issues must be a list of at most ten items")
        issues = [_text(item, "blocking issue", 500) for item in issues]
        with self._connection() as db:
            pipeline = db.execute("SELECT * FROM ai_pipeline WHERE proposal_id=?",
                                  (proposal_id,)).fetchone()
            if pipeline is None:
                raise ValueError("writer provenance missing")
            if pipeline["generator_provider_id"] == reviewer:
                raise ValueError("proposal writer cannot review its own proposal")
            values = (reviewer, model, response["prompt_sha256"], response["answer_sha256"],
                      verdict, rationale, bool(review["evidence_supported"]), issues)
            if pipeline["reviewer_provider_id"] is not None:
                old = (pipeline["reviewer_provider_id"], pipeline["reviewer_model"],
                       pipeline["reviewer_prompt_sha256"], pipeline["reviewer_response_sha256"],
                       pipeline["review_verdict"], pipeline["review_rationale"],
                       bool(pipeline["evidence_supported"]),
                       json.loads(pipeline["blocking_issues_json"]))
                if old == values:
                    return {"status": "REVIEW_EXISTS", "verdict": verdict,
                            "assessment_sha256": pipeline["assessment_sha256"]}
                raise ValueError("proposal review is immutable")
            proposal_row = db.execute("SELECT proposal_sha256 FROM proposals WHERE proposal_id=?",
                                      (proposal_id,)).fetchone()
            assessment = {
                "proposal_sha256": proposal_row["proposal_sha256"],
                "writer": pipeline["generator_provider_id"], "reviewer": reviewer,
                "reviewer_prompt_sha256": response["prompt_sha256"],
                "reviewer_response_sha256": response["answer_sha256"], "verdict": verdict,
                "rationale": rationale, "evidence_supported": review["evidence_supported"],
                "blocking_issues": issues,
            }
            assessment_sha = hashlib.sha256(_pack(assessment, "assessment").encode()).hexdigest()
            db.execute("UPDATE ai_pipeline SET reviewer_provider_id=?,reviewer_model=?,"
                       "reviewer_prompt_sha256=?,reviewer_response_sha256=?,review_verdict=?,"
                       "review_rationale=?,evidence_supported=?,blocking_issues_json=?,"
                       "assessment_sha256=?,reviewed_at=? WHERE proposal_id=?",
                       (reviewer, model, response["prompt_sha256"], response["answer_sha256"],
                        verdict, rationale, int(review["evidence_supported"]),
                        json.dumps(issues, ensure_ascii=False), assessment_sha, time.time(), proposal_id))
        return {"status": "REVIEW_RECORDED", "verdict": verdict,
                "assessment_sha256": assessment_sha}

    def _policy_decide(self, *, proposal_id: str) -> dict:
        """Allow only a reviewed, hash-bound, zero-paid script-draft trial."""
        self._ensure_extensions()
        with self._connection() as db:
            proposal_row = db.execute("SELECT proposal_json FROM proposals WHERE proposal_id=?",
                                      (proposal_id,)).fetchone()
            pipeline = db.execute("SELECT * FROM ai_pipeline WHERE proposal_id=?",
                                  (proposal_id,)).fetchone()
            if proposal_row is None or pipeline is None or pipeline["review_verdict"] is None:
                raise ValueError("complete independent proposal review before policy decision")
            proposal = json.loads(proposal_row["proposal_json"])
            if proposal["job_kind"] != "script_draft":
                raise ValueError("internal trial policy permits script drafts only")
            binding = db.execute("SELECT request_sha256 FROM request_bindings WHERE proposal_id=?",
                                 (proposal_id,)).fetchone()
            eligible = (
                binding is not None
                and pipeline["generator_provider_id"] != pipeline["reviewer_provider_id"]
                and pipeline["review_verdict"] == "PASS"
                and bool(pipeline["evidence_supported"])
                and not json.loads(pipeline["blocking_issues_json"] or "[]")
                and any(item["verification"] == "LOCAL_CONTENT_HASH_VERIFIED"
                        for item in proposal["evidence"])
                and proposal["effort_estimate"]["hours"] is not None
                and proposal["effort_estimate"]["hours"] <= 8
            )
            outcome = "ACCEPTED" if eligible else "DEFERRED"
            rationale = (
                f"Accepted under {INTERNAL_TRIAL_POLICY}; independent local-free PASS, "
                "source excerpt hash-bound, script_draft only, no paid or external actions."
                if eligible else
                "Deferred: independent review, evidence verification or bounded-effort gate failed."
            )
            old = db.execute("SELECT * FROM decisions WHERE proposal_id=?", (proposal_id,)).fetchone()
            evidence_sha = hashlib.sha256(_pack({"evidence": proposal["evidence"]},
                                                "evidence").encode()).hexdigest()
            if old:
                if old["outcome"] != outcome:
                    raise ValueError("proposal already has a different immutable decision")
                decision_id = int(old["decision_id"])
            else:
                cur = db.execute("INSERT INTO decisions(proposal_id,outcome,actor,rationale,"
                                  "evidence_sha256,decided_at) VALUES(?,?,?,?,?,?)",
                                  (proposal_id, outcome, "INTERNAL_POLICY", rationale,
                                   evidence_sha, time.time()))
                decision_id = int(cur.lastrowid)
            if eligible:
                db.execute("INSERT OR IGNORE INTO policy_approvals VALUES(?,?,?,?,?)",
                           (decision_id, proposal_id, INTERNAL_TRIAL_POLICY,
                            pipeline["assessment_sha256"], time.time()))
        return {"status": "POLICY_DECISION_RECORDED", "proposal_id": proposal_id,
                "decision_id": decision_id, "outcome": outcome,
                "policy_id": INTERNAL_TRIAL_POLICY if eligible else None,
                "owner_authority": False, "publication_approved": False}

    @staticmethod
    def _parse_model_json(answer: object, label: str) -> dict:
        if not isinstance(answer, str) or len(answer) > 12_000:
            raise ValueError(f"{label} answer is missing or oversized")
        try:
            value = json.loads(answer)
        except ValueError as exc:
            raise ValueError(f"{label} must return strict JSON without markdown fences") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{label} must return a JSON object")
        return value

    def _get_request(self, request_key: str) -> dict | None:
        self._ensure_extensions()
        with self._connection(readonly=True) as db:
            row = db.execute("SELECT proposal_id,proposal_json,proposal_sha256 FROM proposals "
                             "WHERE request_key=?", (request_key,)).fetchone()
            if row is None:
                return None
            pipeline = db.execute("SELECT * FROM ai_pipeline WHERE proposal_id=?",
                                  (row["proposal_id"],)).fetchone()
            binding = db.execute("SELECT request_sha256 FROM request_bindings WHERE proposal_id=?",
                                 (row["proposal_id"],)).fetchone()
        return {"proposal_id": row["proposal_id"], "proposal": json.loads(row["proposal_json"]),
                "proposal_sha256": row["proposal_sha256"],
                "pipeline": dict(pipeline) if pipeline else None,
                "request_sha256": binding["request_sha256"] if binding else None}

    def run_internal_script_trial(self, *, router, queue_database: str | Path,
                                  request_key: str, brief: str, language: str,
                                  evidence: list[dict],
                                  supersedes_id: str | None = None) -> dict:
        """Generate, independently review and policy-queue one bounded script draft."""
        if not isinstance(language, str) or language not in {"ar", "en"}:
            raise ValueError("language must be ar or en")
        brief = _text(brief, "production brief", 2000)
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 10:
            raise ValueError("one to ten caller-supplied evidence items are required")
        normalized = []
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict) or set(item) - {"id", "source", "observed_at", "claim", "content"}:
                raise ValueError("invalid evidence item fields")
            evidence_id = item.get("id", f"evidence_{index}")
            if not isinstance(evidence_id, str) or not _EVIDENCE_ID.fullmatch(evidence_id):
                raise ValueError("invalid evidence id")
            content = item.get("content")
            normalized.append({
                "id": evidence_id,
                "source": _text(item.get("source"), "evidence source", 500),
                "observed_at": _text(item.get("observed_at"), "evidence date", 80),
                "claim": _text(item.get("claim"), "evidence claim", 1000),
                "content": _text(content, "evidence excerpt", 4000) if content is not None else None,
            })
        if len({item["id"] for item in normalized}) != len(normalized):
            raise ValueError("evidence ids must be unique")
        if supersedes_id is not None:
            if not isinstance(supersedes_id, str) or not _ID.fullmatch(supersedes_id):
                raise ValueError("invalid supersedes_id")
            with self._connection(readonly=True) as db:
                previous = db.execute("SELECT 1 FROM proposals WHERE proposal_id=?",
                                      (supersedes_id,)).fetchone()
            if previous is None:
                raise ValueError("superseded proposal not found")
        request_json = _pack({"brief": brief, "language": language, "evidence": normalized,
                              "supersedes_id": supersedes_id},
                             "trial request")
        request_sha = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        if not hasattr(router, "local_free_provider_ids"):
            raise ValueError("Studio Director requires the existing ChatRouter provider controls")
        writers = router.local_free_provider_ids(role="script_draft")
        reviewers = router.local_free_provider_ids(role="editorial_review")
        if not writers or not reviewers or not any(w != r for w in writers for r in reviewers):
            raise ValueError("two distinct loopback free providers are required for independent review")

        existing = self._get_request(request_key)
        if existing is not None and existing["request_sha256"] is None:
            raise ValueError("trial proposal lacks atomic request/provenance binding; inspect ledger")
        if existing is not None and existing["request_sha256"] != request_sha:
            raise ValueError("trial request key was already used for different input")
        if existing is None:
            user_input = json.dumps({"brief": brief, "language": language, "age_band": "4-6",
                                     "evidence": normalized,
                                     "supersedes_id": supersedes_id},
                                    ensure_ascii=False, sort_keys=True)
            writer_system = (
                "You are the Kids Studio educational idea proposer. You have no browser or research tool. "
                "Use ONLY caller-supplied evidence IDs; do not invent studies, market data, views, sources "
                "or verification. A supersedes_id is only an audit link, never evidence, provenance, or approval. "
                "Return one original idea as strict JSON "
                "with exactly: title, summary, "
                "learning_objective, evidence_ids (array), alternatives (2-4 objects each option/rationale), "
                "effort_estimate (hours 0-8 and basis), risks (1-5 strings). Suit ages 4-6 and the specified "
                "language. The effort is an unverified planning estimate, not a budget or promise."
            )
            writer = router.complete(
                role="script_draft", system_prompt=writer_system, user_prompt=user_input,
                allow_paid=False, allow_fallback=False, allowed_providers=writers,
                max_output_tokens=900,
            )
            if writer.get("provider_id") not in writers or writer.get("billing_policy") != "free" \
                    or writer.get("failover_used") is not False:
                raise ValueError("idea proposer response is outside the local-free provider boundary")
            concept = self._parse_model_json(writer.get("answer"), "idea proposer")
            required = {"title", "summary", "learning_objective", "evidence_ids",
                        "alternatives", "effort_estimate", "risks"}
            if set(concept) != required:
                raise ValueError("idea proposer response fields do not match the schema")
            supplied = {item["id"]: item for item in normalized}
            refs = concept["evidence_ids"]
            if (not isinstance(refs, list) or not refs or len(set(refs)) != len(refs)
                    or any(not isinstance(ref, str) or ref not in supplied for ref in refs)):
                raise ValueError("idea must cite only supplied evidence IDs")
            selected = [supplied[ref] for ref in refs]
            title = _text(concept["title"], "idea title", 200)
            objective = _text(concept["learning_objective"], "learning objective", 500)
            proposal = {
                "title": title,
                "summary": _text(concept["summary"], "idea summary", 4000),
                "audience": "ages 4-6",
                "learning_objective": objective,
                "alternatives": concept["alternatives"],
                "effort_estimate": concept["effort_estimate"],
                "risks": concept["risks"],
                "evidence": [{**item, "sha256": None} for item in selected],
                "job_kind": "script_draft",
                "job_payload": {"language": language, "topic": f"{title}: {objective}"[:400],
                                "auto_review": False},
            }
            if supersedes_id is not None:
                proposal["supersedes_id"] = supersedes_id
            created = self.propose(request_key=request_key, proposal=proposal,
                                   _generation_response=writer, _request_sha256=request_sha,
                                   _pipeline_capability=_PIPELINE_CAPABILITY)
            existing = self._get_request(request_key)
        if existing is None or existing["pipeline"] is None:
            raise ValueError("proposal writer provenance missing; inspect ledger before retrying")
        proposal_id = existing["proposal_id"]
        pipeline = existing["pipeline"]
        if pipeline["review_verdict"] is None:
            reviewer_system = (
                "You are an independent educational/editorial reviewer, not the proposer. Review this "
                "exact proposal and caller-supplied evidence. Check objective clarity, age suitability, "
                "source support, originality risk and bounded effort. A local content hash verifies excerpt "
                "bytes only, not source authenticity or factual truth. You have no browser or research tool. "
                "Do not approve money, publication or external actions. Return strict JSON with exactly: "
                "verdict (PASS/REVISE/BLOCK), rationale, evidence_supported (boolean), blocking_issues (array)."
            )
            reviewer = router.complete(
                role="editorial_review", system_prompt=reviewer_system,
                user_prompt=json.dumps(existing["proposal"], ensure_ascii=False, sort_keys=True),
                allow_paid=False, allow_fallback=False,
                different_from=pipeline["generator_provider_id"], allowed_providers=reviewers,
                max_output_tokens=700,
            )
            if reviewer.get("provider_id") not in reviewers or reviewer.get("billing_policy") != "free" \
                    or reviewer.get("failover_used") is not False:
                raise ValueError("review response is outside the local-free provider boundary")
            review = self._parse_model_json(reviewer.get("answer"), "independent reviewer")
            self.record_agent_review(proposal_id=proposal_id, response=reviewer, review=review,
                                     _pipeline_capability=_PIPELINE_CAPABILITY)
        decision = self._policy_decide(proposal_id=proposal_id)
        if decision["outcome"] != "ACCEPTED":
            return {**decision, "status": "TRIAL_DEFERRED", "queue_job_id": None,
                    "external_research_performed": False, "owner_publication_approval": False}
        queued = self.enqueue_accepted(proposal_id=proposal_id, queue_database=queue_database)
        return {**decision, **queued, "status": "INTERNAL_TRIAL_QUEUED",
                "external_research_performed": False, "owner_publication_approval": False}

    def record_queue_result(self, *, proposal_id: str, queue_database: str | Path) -> dict:
        """Record one terminal queue result with status and digest, not its content."""
        self._ensure_extensions()
        with self._connection(readonly=True) as db:
            dispatch = db.execute("SELECT queue_job_id,decision_id FROM dispatches "
                                  "WHERE proposal_id=?", (proposal_id,)).fetchone()
            prior = db.execute("SELECT * FROM results WHERE proposal_id=?", (proposal_id,)).fetchone()
        if dispatch is None:
            raise ValueError("proposal has no linked queue job")
        queue_job = StudioQueue(queue_database).get(dispatch["queue_job_id"])
        state = queue_job["state"]
        if state not in {"COMPLETED", "FAILED", "CANCELLED"}:
            raise ValueError("queue job is not terminal; result cannot be recorded yet")
        if state == "COMPLETED":
            material = queue_job.get("result_json")
            if not isinstance(material, str):
                raise ValueError("completed queue job has no result record")
            decoded = json.loads(material)
            if not isinstance(decoded, dict):
                raise ValueError("completed queue result must be an object")
            result_status = _result_code(decoded.get("status", "COMPLETED"))
        elif state == "FAILED":
            result_status = _result_code(queue_job.get("error_code") or "FAILED")
            material = json.dumps({"state": state, "error_code": result_status}, sort_keys=True)
        else:
            result_status = "CANCELLED"
            material = json.dumps({"state": state}, sort_keys=True)
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()

        def matches_saved_result(row, dispatch_row) -> bool:
            return (row["decision_id"] == dispatch_row["decision_id"]
                    and row["queue_job_id"] == dispatch_row["queue_job_id"]
                    and row["queue_state"] == state
                    and row["result_status"] == result_status
                    and row["result_sha256"] == digest)

        if prior:
            if not matches_saved_result(prior, dispatch):
                raise ValueError("result record is immutable and conflicts with queue state")
            return {"status": "RESULT_EXISTS", "queue_job_id": queue_job["job_id"],
                    "queue_state": state, "result_sha256": digest}
        with self._connection() as db:
            current_dispatch = db.execute("SELECT queue_job_id,decision_id FROM dispatches "
                                           "WHERE proposal_id=?", (proposal_id,)).fetchone()
            if (current_dispatch is None
                    or current_dispatch["decision_id"] != dispatch["decision_id"]
                    or current_dispatch["queue_job_id"] != dispatch["queue_job_id"]):
                raise ValueError("dispatch changed during result recording")
            concurrent_prior = db.execute("SELECT * FROM results WHERE proposal_id=?",
                                          (proposal_id,)).fetchone()
            if concurrent_prior:
                if not matches_saved_result(concurrent_prior, current_dispatch):
                    raise ValueError("result record is immutable and conflicts with queue state")
                return {"status": "RESULT_EXISTS", "queue_job_id": queue_job["job_id"],
                        "queue_state": state, "result_sha256": digest}
            db.execute("INSERT INTO results VALUES(?,?,?,?,?,?,?)",
                       (proposal_id, current_dispatch["decision_id"], queue_job["job_id"],
                        state, result_status, digest, time.time()))
        return {"status": "RESULT_RECORDED", "queue_job_id": queue_job["job_id"],
                "queue_state": state, "result_status": result_status,
                "result_sha256": digest, "result_content_stored": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local evidence-backed Studio Director ledger")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    add = sub.add_parser("propose")
    add.add_argument("--request-key", required=True)
    add.add_argument("--proposal-json", required=True)
    decision = sub.add_parser("decide")
    decision.add_argument("--proposal-id", required=True)
    decision.add_argument("--outcome", required=True, choices=sorted(_MANUAL_OUTCOMES))
    decision.add_argument("--actor", required=True)
    decision.add_argument("--rationale", required=True)
    show = sub.add_parser("show")
    show.add_argument("--proposal-id", required=True)
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--proposal-id", required=True)
    enqueue.add_argument("--queue-db", required=True)
    pilot = sub.add_parser("pilot", help="Generate and review a zero-paid internal script trial")
    pilot.add_argument("--providers", required=True, help="Existing private AI provider profile")
    pilot.add_argument("--queue-db", required=True)
    pilot.add_argument("--request-key", required=True)
    pilot.add_argument("--brief", required=True)
    pilot.add_argument("--language", choices=("ar", "en"), required=True)
    pilot.add_argument("--evidence-json", required=True,
                       help="Caller-supplied evidence JSON array; no external research is performed")
    result_cmd = sub.add_parser("record-result")
    result_cmd.add_argument("--proposal-id", required=True)
    result_cmd.add_argument("--queue-db", required=True)
    args = parser.parse_args(argv)
    try:
        store = StudioDirector(args.db)
        if args.action == "init":
            store.initialize()
            result = {"status": "INITIALIZED"}
        elif args.action == "propose":
            source = Path(args.proposal_json)
            info = source.lstat()
            if (not stat.S_ISREG(info.st_mode) or source.is_symlink()
                    or info.st_size > _MAX_JSON_BYTES):
                raise ValueError("proposal input must be a bounded regular file")
            result = store.propose(request_key=args.request_key,
                                   proposal=json.loads(source.read_text(encoding="utf-8")))
        elif args.action == "decide":
            result = store.decide(proposal_id=args.proposal_id, outcome=args.outcome,
                                  actor=args.actor, rationale=args.rationale)
        elif args.action == "show":
            result = store.get(proposal_id=args.proposal_id)
        elif args.action == "pilot":
            source = Path(args.evidence_json)
            info = source.lstat()
            if (not stat.S_ISREG(info.st_mode) or source.is_symlink() or info.st_size > _MAX_JSON_BYTES):
                raise ValueError("evidence input must be a bounded regular file")
            supplied = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(supplied, list):
                raise ValueError("evidence input must be a JSON array")
            from .ai_router import AIConfig, ChatRouter
            result = store.run_internal_script_trial(
                router=ChatRouter(AIConfig(args.providers)), queue_database=args.queue_db,
                request_key=args.request_key, brief=args.brief, language=args.language,
                evidence=supplied,
            )
        elif args.action == "record-result":
            result = store.record_queue_result(proposal_id=args.proposal_id,
                                               queue_database=args.queue_db)
        else:
            result = store.enqueue_accepted(proposal_id=args.proposal_id,
                                            queue_database=args.queue_db)
    except (ValueError, OSError, sqlite3.Error, QueueError):
        print(json.dumps({"status": "DIRECTOR_ERROR", "publication_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
