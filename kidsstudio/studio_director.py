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
_MAX_JSON_BYTES = 32_768
_SECRET_VALUE = re.compile(r"(?:bearer\s+\S+|(?:token|secret|password|api[_-]?key)=\S+|://[^/@]+:[^/@]+@)", re.I)


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


def _proposal_document(document: object) -> dict:
    if not isinstance(document, dict):
        raise ValueError("proposal must be a JSON object")
    required = {"title", "summary", "audience", "learning_objective",
                "alternatives", "evidence", "job_kind", "job_payload"}
    if set(document) - (required | {"supersedes_id"}) or required - set(document):
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
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"source", "observed_at", "claim", "sha256"}:
            raise ValueError("each evidence reference needs source, observed_at, claim and sha256")
        digest = item["sha256"]
        if digest is not None and (not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ValueError("evidence sha256 must be 64 lowercase hex characters or null")
        clean_evidence.append({
            "source": _text(item["source"], "evidence source", 500),
            "observed_at": _text(item["observed_at"], "evidence date", 80),
            "claim": _text(item["claim"], "evidence claim", 2000),
            "sha256": digest,
            "verification": "CALLER_SUPPLIED_UNVERIFIED",
        })
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
        except Exception:
            self.path.unlink(missing_ok=True)
            raise

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

    def propose(self, *, request_key: str, proposal: object) -> dict:
        if not isinstance(request_key, str) or not _KEY.fullmatch(request_key):
            raise ValueError("invalid proposal request key")
        clean = _proposal_document(proposal)
        packed = _pack(clean, "proposal")
        digest = hashlib.sha256(packed.encode("utf-8")).hexdigest()
        with self._connection() as db:
            existing = db.execute("SELECT * FROM proposals WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["proposal_sha256"] != digest:
                    raise ValueError("proposal request key was already used for different content")
                return {"proposal_id": existing["proposal_id"], "proposal_sha256": digest,
                        "status": "PROPOSAL_EXISTS"}
            if clean["supersedes_id"] is not None and not db.execute(
                    "SELECT 1 FROM proposals WHERE proposal_id=?", (clean["supersedes_id"],)).fetchone():
                raise ValueError("superseded proposal not found")
            proposal_id = secrets.token_hex(16)
            db.execute("INSERT INTO proposals VALUES(?,?,?,?,?)",
                       (proposal_id, request_key, packed, digest, time.time()))
        return {"proposal_id": proposal_id, "proposal_sha256": digest,
                "status": "PROPOSAL_RECORDED"}

    def decide(self, *, proposal_id: str, outcome: str, actor: str, rationale: str) -> dict:
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise ValueError("unsupported decision outcome")
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
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        with self._connection(readonly=True) as db:
            row = db.execute("SELECT p.proposal_json,d.decision_id,d.outcome FROM proposals p "
                             "JOIN decisions d USING(proposal_id) WHERE p.proposal_id=?",
                             (proposal_id,)).fetchone()
            if row is None or row["outcome"] != "ACCEPTED":
                raise ValueError("only an explicitly accepted proposal can enqueue work")
            proposal = json.loads(row["proposal_json"])
            decision_id = int(row["decision_id"])
        request_key = f"director-{proposal_id}-{decision_id}"
        payload = dict(proposal["job_payload"])
        payload.update({"studio_proposal_id": proposal_id, "studio_decision_id": decision_id})
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
        return {"proposal_id": proposal_id, "proposal_sha256": proposal["proposal_sha256"],
                "proposal": json.loads(proposal["proposal_json"]),
                "decision": dict(decision) if decision else None,
                "dispatch": dict(dispatch) if dispatch else None,
                "evidence_verified": False, "owner_publication_approval": False}


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
    decision.add_argument("--outcome", required=True, choices=sorted(_OUTCOMES))
    decision.add_argument("--actor", required=True)
    decision.add_argument("--rationale", required=True)
    show = sub.add_parser("show")
    show.add_argument("--proposal-id", required=True)
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--proposal-id", required=True)
    enqueue.add_argument("--queue-db", required=True)
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
