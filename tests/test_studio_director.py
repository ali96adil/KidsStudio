import json
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from kidsstudio.studio_director import StudioDirector
from kidsstudio.studio_queue import QueueError, StudioQueue
from kidsstudio.studio_director import INTERNAL_TRIAL_POLICY, _result_code


class SyntheticRouter:
    """Deterministic provider double; never opens a model/API connection."""
    def __init__(self, verdict="PASS"):
        self.verdict = verdict
        self.calls = []

    def local_free_provider_ids(self, *, role):
        return {"writer-local"} if role == "script_draft" else {"reviewer-local"}

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        role = kwargs["role"]
        if role == "script_draft":
            answer = json.dumps({
                "title": "ألوان الحديقة", "summary": "قصة تميّز اللونين الأحمر والأزرق.",
                "learning_objective": "أن يميز الطفل الأحمر والأزرق.",
                "evidence_ids": ["note1"],
                "alternatives": [
                    {"option": "قصة حوارية", "rationale": "تربط اللون بأمثلة يومية."},
                    {"option": "لعبة مطابقة", "rationale": "تدعم الاسترجاع النشط."},
                ],
                "effort_estimate": {"hours": 2, "basis": "تقدير اصطناعي للاختبار."},
                "risks": ["يحتاج النص لمراجعة عربية قبل الإنتاج."],
            }, ensure_ascii=False)
            provider = "writer-local"
        else:
            answer = json.dumps({
                "verdict": self.verdict, "rationale": "Synthetic independent review.",
                "evidence_supported": True, "blocking_issues": [],
            })
            provider = "reviewer-local"
        return {"provider_id": provider, "model": "test-only", "role": role,
                "billing_policy": "free", "failover_used": False,
                "prompt_sha256": hashlib.sha256(kwargs["user_prompt"].encode()).hexdigest(),
                "answer": answer, "answer_sha256": hashlib.sha256(answer.encode()).hexdigest()}


class StudioDirectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.ledger_path = self.root / "director.sqlite"
        self.queue_path = self.root / "queue.sqlite"
        self.store = StudioDirector(self.ledger_path)
        self.store.initialize()
        StudioQueue(self.queue_path).initialize()

    def tearDown(self):
        self.temp.cleanup()

    def proposal(self, **overrides):
        document = {
            "title": "Colors through play",
            "summary": "A short story introduces colors through everyday objects.",
            "audience": "ages 4-6",
            "learning_objective": "Identify red and blue objects.",
            "alternatives": [
                {"option": "story", "rationale": "Supports recall in context."},
                {"option": "worksheet", "rationale": "Lower production effort."},
            ],
            "evidence": [{
                "source": "owner-research-note-01",
                "observed_at": "2026-11-11",
                "claim": "The owner supplied a note requesting color recognition topics.",
                "sha256": "a" * 64,
            }],
            "job_kind": "script_draft",
            "job_payload": {"language": "ar", "topic": "الألوان", "auto_review": True},
        }
        document.update(overrides)
        return document

    def create(self, **overrides):
        return self.store.propose(request_key="colors-topic-v1", proposal=self.proposal(**overrides))

    def trial_args(self, request_key, router):
        content = "Caller supplied curriculum text."
        return {"router": router, "queue_database": self.queue_path,
                "request_key": request_key, "brief": "Teach colors.",
                "language": "en", "evidence": [{"id": "note1", "source": "note",
                "observed_at": "2026-11-11", "claim": content, "content": content}]}

    def test_proposal_is_unique_and_idempotent(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(second["status"], "PROPOSAL_EXISTS")
        self.assertEqual(len(self.store.get(proposal_id=first["proposal_id"])["proposal"]["alternatives"]), 2)

    def test_same_request_key_cannot_hide_different_proposal(self):
        self.create()
        with self.assertRaisesRegex(ValueError, "different content"):
            self.store.propose(request_key="colors-topic-v1",
                               proposal=self.proposal(title="Different concept"))

    def test_requires_multiple_alternatives_and_evidence(self):
        with self.assertRaisesRegex(ValueError, "alternatives"):
            self.create(alternatives=[{"option": "story", "rationale": "Only one."}])
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.create(evidence=[])

    def test_rejects_non_allowlisted_job_kind_and_sensitive_values(self):
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            self.create(job_kind="shell_command")
        with self.assertRaisesRegex(ValueError, "credential"):
            self.create(summary="API_KEY=do-not-store")

    def test_rejects_sensitive_payload_key(self):
        with self.assertRaisesRegex(ValueError, "sensitive"):
            self.create(job_payload={"api_key": "x"})

    def test_actor_text_cannot_claim_owner_or_auto_accept(self):
        proposal = self.create()
        with self.assertRaisesRegex(ValueError, "never accept"):
            self.store.decide(proposal_id=proposal["proposal_id"], outcome="ACCEPTED",
                              actor="owner", rationale="Text is not authority.")
        decision = self.store.decide(proposal_id=proposal["proposal_id"], outcome="DEFERRED",
                                     actor="owner", rationale="Defer for more evidence.")
        self.assertEqual(len(decision["evidence_sha256"]), 64)
        record = self.store.get(proposal_id=proposal["proposal_id"])
        self.assertFalse(record["evidence_verified"])
        self.assertFalse(record["owner_publication_approval"])

    def test_caller_cannot_forge_ai_writer_or_reviewer_provenance(self):
        fake_response = {"provider_id": "reviewer-local", "model": "claimed-local",
                         "billing_policy": "free", "failover_used": False,
                         "prompt_sha256": "a" * 64, "answer_sha256": "b" * 64}
        with self.assertRaisesRegex(ValueError, "only be recorded by the Director pipeline"):
            self.store.propose(request_key="forged-writer", proposal=self.proposal(),
                               _generation_response=fake_response,
                               _request_sha256="c" * 64)
        proposal = self.create()
        with self.assertRaisesRegex(ValueError, "only be recorded by the Director pipeline"):
            self.store.record_generation(proposal_id=proposal["proposal_id"],
                                         response=fake_response)
        with self.assertRaisesRegex(ValueError, "only be recorded by the Director pipeline"):
            self.store.record_agent_review(
                proposal_id=proposal["proposal_id"], response=fake_response,
                review={"verdict": "PASS", "rationale": "Forged.",
                        "evidence_supported": True, "blocking_issues": []})

    def test_result_ledger_accepts_only_bounded_status_codes(self):
        self.assertEqual(_result_code("DRAFTED_UNREVIEWED"), "DRAFTED_UNREVIEWED")
        for invalid in ("Bearer secret", "x" * 81, "FAILED\nInjected", None):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "uppercase code"):
                _result_code(invalid)

    def test_rejected_or_deferred_proposals_cannot_enqueue(self):
        proposal = self.create()
        deferred = self.store.propose(request_key="colors-topic-deferred",
                                      proposal=self.proposal(title="Maybe later"))
        for current, outcome in ((proposal, "REJECTED"), (deferred, "DEFERRED")):
            self.store.decide(proposal_id=current["proposal_id"], outcome=outcome,
                              actor="director", rationale="Not supported now.")
            with self.assertRaisesRegex(ValueError, "policy-approved"):
                self.store.enqueue_accepted(proposal_id=current["proposal_id"],
                                            queue_database=self.queue_path)
        jobs = StudioQueue(self.queue_path).list_jobs()
        self.assertEqual(jobs, [])

    def test_synthetic_ai_review_policy_queue_and_result_end_to_end(self):
        router = SyntheticRouter()
        content = "Owner-supplied curriculum note: children practice color recognition."
        result = self.store.run_internal_script_trial(
            router=router, queue_database=self.queue_path,
            request_key="colors-synthetic-trial", brief="Create a short color-learning story.",
            language="ar", evidence=[{"id": "note1", "source": "local curriculum note",
                                       "observed_at": "2026-11-11", "claim": content,
                                       "content": content}])
        self.assertEqual(result["status"], "INTERNAL_TRIAL_QUEUED")
        self.assertEqual(result["outcome"], "ACCEPTED")
        self.assertEqual(len(router.calls), 2)
        self.assertFalse(result["external_research_performed"])
        self.assertFalse(result["owner_publication_approval"])
        jobs = StudioQueue(self.queue_path).list_jobs()
        self.assertEqual(len(jobs), 1)
        payload = json.loads(jobs[0]["payload"])
        self.assertTrue(payload["studio_no_paid"])
        self.assertEqual(payload["studio_trial_policy"], INTERNAL_TRIAL_POLICY)
        self.assertEqual(payload["auto_review"], False)
        self.assertEqual(StudioQueue(self.queue_path).claim(
            worker_id="synthetic-worker", capabilities=["script_draft"])["job_id"],
            result["queue_job_id"])
        StudioQueue(self.queue_path).complete(
            job_id=result["queue_job_id"], worker_id="synthetic-worker", generation=1,
            result={"status": "SYNTHETIC_DRAFT_COMPLETED", "publication_approved": False})
        recorded = self.store.record_queue_result(proposal_id=result["proposal_id"],
                                                  queue_database=self.queue_path)
        self.assertEqual(recorded["status"], "RESULT_RECORDED")
        self.assertEqual(recorded["queue_state"], "COMPLETED")
        self.assertFalse(recorded["result_content_stored"])
        record = self.store.get(proposal_id=result["proposal_id"])
        self.assertEqual(record["proposal"]["evidence"][0]["verification"],
                         "LOCAL_CONTENT_HASH_VERIFIED")
        self.assertEqual(record["internal_policy_approval"]["policy_id"],
                         INTERNAL_TRIAL_POLICY)
        self.assertEqual(self.store.record_queue_result(proposal_id=result["proposal_id"],
                                                        queue_database=self.queue_path)["status"],
                         "RESULT_EXISTS")

    def test_result_record_recovers_after_commit_before_caller_observes_success(self):
        router = SyntheticRouter()
        args = self.trial_args("crash-after-result", router)
        trial = self.store.run_internal_script_trial(**args)
        StudioQueue(self.queue_path).claim(
            worker_id="result-worker", capabilities=["script_draft"])
        StudioQueue(self.queue_path).complete(
            job_id=trial["queue_job_id"], worker_id="result-worker", generation=1,
            result={"status": "SYNTHETIC_DRAFT_COMPLETED"})

        original_connection = self.store._connection
        interrupted = {"pending": True}

        @contextmanager
        def connection(*, readonly=False):
            with original_connection(readonly=readonly) as db:
                yield db
            if not readonly and interrupted["pending"]:
                interrupted["pending"] = False
                raise RuntimeError("simulated interruption after result commit")

        with patch.object(self.store, "_connection", new=connection):
            with self.assertRaisesRegex(RuntimeError, "after result commit"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
        resumed = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                 queue_database=self.queue_path)
        self.assertEqual(resumed["status"], "RESULT_EXISTS")

        original_connection = self.store._connection
        interrupted = {"pending": True}

        @contextmanager
        def interrupt_after_retry_check(*, readonly=False):
            with original_connection(readonly=readonly) as db:
                yield db
            if not readonly and interrupted["pending"]:
                interrupted["pending"] = False
                raise RuntimeError("simulated interruption after saved-result check")

        with patch.object(self.store, "_connection", new=interrupt_after_retry_check):
            with self.assertRaisesRegex(RuntimeError, "after saved-result check"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
        recovered = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                   queue_database=self.queue_path)
        self.assertEqual(recovered["status"], "RESULT_EXISTS")
        self.assertEqual(resumed["queue_job_id"], trial["queue_job_id"])
        record = self.store.get(proposal_id=trial["proposal_id"])
        self.assertEqual(record["result"]["queue_state"], "COMPLETED")

    def test_terminal_queue_result_survives_interruption_before_director_commit(self):
        for mode in ("completed", "failed", "cancelled"):
            with self.subTest(mode=mode):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"before-director-commit-{mode}", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                if mode == "completed":
                    lease = queue.claim(worker_id="before-commit", capabilities=["script_draft"])
                    queue.complete(job_id=trial["queue_job_id"], worker_id="before-commit",
                                   generation=lease["generation"],
                                   result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
                    expected_state = "COMPLETED"
                elif mode == "failed":
                    lease = queue.claim(worker_id="before-commit", capabilities=["script_draft"])
                    queue.fail(job_id=trial["queue_job_id"], worker_id="before-commit",
                               generation=lease["generation"], error_code="SYNTHETIC_FAILURE")
                    expected_state = "FAILED"
                else:
                    queue.cancel(trial["queue_job_id"])
                    expected_state = "CANCELLED"
                queue_events_before = queue.events(trial["queue_job_id"])
                expected_event = {
                    "COMPLETED": "COMPLETED",
                    "FAILED": "FAILED",
                    "CANCELLED": "CANCELLED",
                }[expected_state]
                self.assertEqual(sum(event["event_type"] == expected_event
                                     for event in queue_events_before), 1)

                original_connection = self.store._connection

                @contextmanager
                def interrupt_before_commit(*, readonly=False):
                    with original_connection(readonly=readonly) as db:
                        yield db
                        if not readonly:
                            raise RuntimeError("simulated interruption before Director commit")

                with patch.object(self.store, "_connection", new=interrupt_before_commit):
                    with self.assertRaisesRegex(RuntimeError, "before Director commit"):
                        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                       queue_database=self.queue_path)
                self.assertEqual(queue.events(trial["queue_job_id"]), queue_events_before)
                record = self.store.get(proposal_id=trial["proposal_id"])
                self.assertIsNone(record["result"])
                resumed = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                         queue_database=self.queue_path)
                self.assertEqual(resumed["status"], "RESULT_RECORDED")
                self.assertEqual(resumed["queue_state"], expected_state)
                self.assertEqual(self.store.record_queue_result(
                    proposal_id=trial["proposal_id"], queue_database=self.queue_path
                )["status"], "RESULT_EXISTS")
                self.assertEqual(queue.events(trial["queue_job_id"]), queue_events_before)

    def test_concurrent_result_record_retries_are_idempotent(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "concurrent-result-record", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="concurrent-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="concurrent-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})

        original_connection = self.store._connection
        prior_reads = threading.Barrier(2)

        @contextmanager
        def synchronize_prior_reads(*, readonly=False):
            with original_connection(readonly=readonly) as db:
                yield db
            if readonly:
                prior_reads.wait(timeout=5)

        outcomes = []
        errors = []

        def record():
            try:
                outcomes.append(self.store.record_queue_result(
                    proposal_id=trial["proposal_id"], queue_database=self.queue_path))
            except Exception as exc:  # capture thread failure for a deterministic assertion
                errors.append(exc)

        with patch.object(self.store, "_connection", new=synchronize_prior_reads):
            threads = [threading.Thread(target=record) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads), "result writer thread hung")
        self.assertEqual(errors, [])
        self.assertEqual(sorted(item["status"] for item in outcomes),
                         ["RESULT_EXISTS", "RESULT_RECORDED"])
        self.assertEqual(len(StudioQueue(self.queue_path).list_jobs()), 1)
        record = self.store.get(proposal_id=trial["proposal_id"])
        self.assertEqual(record["result"]["queue_job_id"], trial["queue_job_id"])

    def test_failed_and_cancelled_results_resume_after_commit(self):
        for mode in ("failed", "cancelled"):
            with self.subTest(mode=mode):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"terminal-{mode}-resume", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                if mode == "failed":
                    lease = queue.claim(worker_id="terminal-worker", capabilities=["script_draft"])
                    queue.fail(job_id=trial["queue_job_id"], worker_id="terminal-worker",
                               generation=lease["generation"], error_code="RENDER_FAILED")
                    expected_state, expected_status = "FAILED", "RENDER_FAILED"
                else:
                    queue.cancel(trial["queue_job_id"])
                    expected_state, expected_status = "CANCELLED", "CANCELLED"

                original_connection = self.store._connection
                interrupted = {"pending": True}

                @contextmanager
                def interrupt_after_commit(*, readonly=False):
                    with original_connection(readonly=readonly) as db:
                        yield db
                    if not readonly and interrupted["pending"]:
                        interrupted["pending"] = False
                        raise RuntimeError("simulated interruption after terminal commit")

                with patch.object(self.store, "_connection", new=interrupt_after_commit):
                    with self.assertRaisesRegex(RuntimeError, "after terminal commit"):
                        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                       queue_database=self.queue_path)
                resumed = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                         queue_database=self.queue_path)
                self.assertEqual(resumed["status"], "RESULT_EXISTS")
                record = self.store.get(proposal_id=trial["proposal_id"])
                self.assertEqual(record["result"]["queue_state"], expected_state)
                self.assertEqual(record["result"]["result_status"], expected_status)

    def test_concurrent_failed_and_cancelled_result_retries_are_idempotent(self):
        for mode in ("failed", "cancelled"):
            with self.subTest(mode=mode):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"concurrent-terminal-{mode}", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                if mode == "failed":
                    lease = queue.claim(worker_id="terminal-concurrent", capabilities=["script_draft"])
                    queue.fail(job_id=trial["queue_job_id"], worker_id="terminal-concurrent",
                               generation=lease["generation"], error_code="WORKER_FAILED")
                else:
                    queue.cancel(trial["queue_job_id"])

                original_connection = self.store._connection
                prior_reads = threading.Barrier(2)

                @contextmanager
                def synchronize_reads(*, readonly=False):
                    with original_connection(readonly=readonly) as db:
                        yield db
                    if readonly:
                        prior_reads.wait(timeout=5)

                outcomes, errors = [], []

                def record():
                    try:
                        outcomes.append(self.store.record_queue_result(
                            proposal_id=trial["proposal_id"], queue_database=self.queue_path))
                    except Exception as exc:
                        errors.append(exc)

                with patch.object(self.store, "_connection", new=synchronize_reads):
                    threads = [threading.Thread(target=record) for _ in range(2)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=10)

                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                self.assertEqual(sorted(item["status"] for item in outcomes),
                                 ["RESULT_EXISTS", "RESULT_RECORDED"])

    def test_failed_and_cancelled_result_retries_reject_conflicting_terminal_state(self):
        for mode in ("failed", "cancelled"):
            with self.subTest(mode=mode):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"terminal-conflict-{mode}", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                if mode == "failed":
                    lease = queue.claim(worker_id="conflict-terminal", capabilities=["script_draft"])
                    queue.fail(job_id=trial["queue_job_id"], worker_id="conflict-terminal",
                               generation=lease["generation"], error_code="ORIGINAL_FAILURE")
                else:
                    queue.cancel(trial["queue_job_id"])
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
                original_get = StudioQueue.get

                def conflicting_terminal_state(queue_instance, job_id):
                    job = original_get(queue_instance, job_id)
                    job["state"] = "COMPLETED" if mode == "failed" else "FAILED"
                    job["error_code"] = "CHANGED_FAILURE"
                    return job

                with patch.object(StudioQueue, "get", new=conflicting_terminal_state):
                    with self.assertRaises(ValueError):
                        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                       queue_database=self.queue_path)

    def test_result_record_rejects_nonterminal_and_unlinked_jobs(self):
        proposal = self.create()
        with self.assertRaisesRegex(ValueError, "no linked queue job"):
            self.store.record_queue_result(proposal_id=proposal["proposal_id"],
                                           queue_database=self.queue_path)
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-not-terminal", SyntheticRouter()))
        with self.assertRaisesRegex(ValueError, "not terminal"):
            self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                           queue_database=self.queue_path)

    def test_result_retry_rejects_changed_terminal_result_material(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-conflict", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="conflict-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="conflict-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)

        original_get = StudioQueue.get

        def changed_result(queue_instance, job_id):
            job = original_get(queue_instance, job_id)
            job["result_json"] = json.dumps({"status": "DIFFERENT_TERMINAL_RESULT"})
            return job

        with patch.object(StudioQueue, "get", new=changed_result):
            with self.assertRaisesRegex(ValueError, "immutable and conflicts"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)

    def test_result_retry_rejects_dispatch_relinked_to_another_queue_job(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-job-identity", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="identity-worker", capabilities=["script_draft"])
        result_payload = {"status": "SYNTHETIC_DRAFT_COMPLETED"}
        queue.complete(job_id=trial["queue_job_id"], worker_id="identity-worker", generation=1,
                       result=result_payload)
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)

        alternate = queue.enqueue(kind="script_draft", request_key="alternate-terminal-job",
                                  payload={"topic": "unrelated test job"})
        queue.claim(worker_id="identity-worker", capabilities=["script_draft"])
        queue.complete(job_id=alternate["job_id"], worker_id="identity-worker", generation=1,
                       result=result_payload)
        with self.store._connection() as db:
            db.execute("UPDATE dispatches SET queue_job_id=? WHERE proposal_id=?",
                       (alternate["job_id"], trial["proposal_id"]))

        with self.assertRaisesRegex(ValueError, "immutable and conflicts"):
            self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                           queue_database=self.queue_path)

    def test_result_retry_fails_closed_and_preserves_record_when_queue_lookup_fails(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-queue-read-failure", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="read-failure-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="read-failure-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)
        with self.store._connection(readonly=True) as db:
            saved_before = dict(db.execute("SELECT * FROM results WHERE proposal_id=?",
                                           (trial["proposal_id"],)).fetchone())

        with patch.object(StudioQueue, "get", side_effect=OSError("queue unavailable")):
            with self.assertRaisesRegex(OSError, "queue unavailable"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
        with self.store._connection(readonly=True) as db:
            saved_after = dict(db.execute("SELECT * FROM results WHERE proposal_id=?",
                                          (trial["proposal_id"],)).fetchone())
        self.assertEqual(saved_after, saved_before)

    def test_result_retry_fails_closed_and_preserves_record_when_ledger_read_fails(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-ledger-read-failure", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="ledger-read-failure-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="ledger-read-failure-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)
        with self.store._connection(readonly=True) as db:
            saved_before = dict(db.execute("SELECT * FROM results WHERE proposal_id=?",
                                           (trial["proposal_id"],)).fetchone())

        original_connection = self.store._connection

        @contextmanager
        def fail_read(*, readonly=False):
            if readonly:
                raise OSError("ledger unavailable")
            with original_connection(readonly=readonly) as db:
                yield db

        with patch.object(self.store, "_connection", new=fail_read):
            with self.assertRaisesRegex(OSError, "ledger unavailable"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
        with self.store._connection(readonly=True) as db:
            saved_after = dict(db.execute("SELECT * FROM results WHERE proposal_id=?",
                                          (trial["proposal_id"],)).fetchone())
        self.assertEqual(saved_after, saved_before)

    def test_result_retry_rejects_queue_lookup_returning_different_job_identity(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-queue-identity-mismatch", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="identity-mismatch-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="identity-mismatch-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)
        original_get = StudioQueue.get

        def wrong_identity(queue_instance, job_id):
            result = original_get(queue_instance, job_id)
            result["job_id"] = "different-queue-job"
            return result

        with patch.object(StudioQueue, "get", new=wrong_identity):
            with self.assertRaisesRegex(ValueError, "queue job identity does not match dispatch"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)

    def test_result_retry_rejects_dispatch_relinked_to_another_decision(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "result-decision-identity", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="decision-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="decision-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)
        other = self.store.propose(request_key="other-decision-proposal",
                                   proposal=self.proposal(title="Unrelated deferred proposal"))
        other_decision = self.store.decide(
            proposal_id=other["proposal_id"], outcome="DEFERRED", actor="director",
            rationale="Independent test decision.")
        with self.store._connection() as db:
            db.execute("UPDATE dispatches SET decision_id=? WHERE proposal_id=?",
                       (other_decision["decision_id"], trial["proposal_id"]))

        with self.assertRaisesRegex(ValueError, "immutable and conflicts"):
            self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                           queue_database=self.queue_path)

    def test_saved_result_retry_rechecks_dispatch_after_queue_snapshot(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "saved-result-stale-dispatch", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="stale-dispatch-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="stale-dispatch-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                       queue_database=self.queue_path)
        original_get = StudioQueue.get

        def relink_after_snapshot(queue_instance, job_id):
            result = original_get(queue_instance, job_id)
            with self.store._connection() as db:
                db.execute("UPDATE dispatches SET queue_job_id=? WHERE proposal_id=?",
                           ("concurrent-relinked-job", trial["proposal_id"]))
            return result

        with patch.object(StudioQueue, "get", new=relink_after_snapshot):
            with self.assertRaisesRegex(ValueError, "dispatch changed during result retry"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)

        with self.store._connection() as db:
            db.execute("UPDATE dispatches SET queue_job_id=? WHERE proposal_id=?",
                       (trial["queue_job_id"], trial["proposal_id"]))
        resumed = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                 queue_database=self.queue_path)
        self.assertEqual(resumed["status"], "RESULT_EXISTS")

    def test_dispatch_snapshot_change_before_write_rolls_back_and_recovers(self):
        trial = self.store.run_internal_script_trial(**self.trial_args(
            "write-result-stale-dispatch", SyntheticRouter()))
        queue = StudioQueue(self.queue_path)
        queue.claim(worker_id="write-stale-dispatch-worker", capabilities=["script_draft"])
        queue.complete(job_id=trial["queue_job_id"], worker_id="write-stale-dispatch-worker", generation=1,
                       result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
        original_get = StudioQueue.get

        def relink_after_snapshot(queue_instance, job_id):
            result = original_get(queue_instance, job_id)
            with self.store._connection() as db:
                db.execute("UPDATE dispatches SET queue_job_id=? WHERE proposal_id=?",
                           ("concurrent-relinked-job", trial["proposal_id"]))
            return result

        with patch.object(StudioQueue, "get", new=relink_after_snapshot):
            with self.assertRaisesRegex(ValueError, "dispatch changed during result recording"):
                self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                               queue_database=self.queue_path)
        self.assertIsNone(self.store.get(proposal_id=trial["proposal_id"])["result"])

        with self.store._connection() as db:
            db.execute("UPDATE dispatches SET queue_job_id=? WHERE proposal_id=?",
                       (trial["queue_job_id"], trial["proposal_id"]))
        resumed = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                 queue_database=self.queue_path)
        self.assertEqual(resumed["status"], "RESULT_RECORDED")

    def test_queue_snapshot_change_before_result_write_is_rejected_and_recoverable(self):
        for change in ("state", "material"):
            with self.subTest(change=change):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"stale-queue-snapshot-{change}", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                queue.claim(worker_id="queue-snapshot-worker", capabilities=["script_draft"])
                queue.complete(job_id=trial["queue_job_id"], worker_id="queue-snapshot-worker", generation=1,
                               result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
                original_get = StudioQueue.get
                changed = {"value": False}

                def mutate_after_snapshot(queue_instance, job_id):
                    snapshot = original_get(queue_instance, job_id)
                    if not changed["value"]:
                        changed["value"] = True
                        with queue_instance._connection(write=True) as db:
                            if change == "state":
                                db.execute("UPDATE jobs SET state='FAILED',error_code='SYNTHETIC_FAILURE',"
                                           "result_json=NULL WHERE job_id=?", (job_id,))
                            else:
                                db.execute("UPDATE jobs SET result_json=? WHERE job_id=?",
                                           (json.dumps({"status": "CHANGED_AFTER_SNAPSHOT"}), job_id))
                    return snapshot

                with patch.object(StudioQueue, "get", new=mutate_after_snapshot):
                    with self.assertRaisesRegex(ValueError, "queue result changed during Director recording"):
                        self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                       queue_database=self.queue_path)
                self.assertIsNone(self.store.get(proposal_id=trial["proposal_id"])["result"])
                recovered = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                           queue_database=self.queue_path)
                self.assertEqual(recovered["status"], "RESULT_RECORDED")
                expected = "FAILED" if change == "state" else "COMPLETED"
                self.assertEqual(recovered["queue_state"], expected)

    def test_terminal_queue_state_cannot_change_after_confirmation_read(self):
        for mode in ("completed", "failed", "cancelled"):
            with self.subTest(mode=mode):
                trial = self.store.run_internal_script_trial(**self.trial_args(
                    f"terminal-confirmed-immutable-{mode}", SyntheticRouter()))
                queue = StudioQueue(self.queue_path)
                lease = None
                if mode == "completed":
                    lease = queue.claim(worker_id="confirmed-state-worker",
                                        capabilities=["script_draft"])
                    queue.complete(job_id=trial["queue_job_id"], worker_id="confirmed-state-worker",
                                   generation=lease["generation"],
                                   result={"status": "SYNTHETIC_DRAFT_COMPLETED"})
                elif mode == "failed":
                    lease = queue.claim(worker_id="confirmed-state-worker",
                                        capabilities=["script_draft"])
                    queue.fail(job_id=trial["queue_job_id"], worker_id="confirmed-state-worker",
                               generation=lease["generation"], error_code="SYNTHETIC_FAILURE")
                else:
                    queue.cancel(trial["queue_job_id"])

                original_get = StudioQueue.get
                confirmations = {"count": 0}

                def attempt_terminal_mutation_after_confirmation(queue_instance, job_id):
                    snapshot = original_get(queue_instance, job_id)
                    confirmations["count"] += 1
                    if confirmations["count"] == 2:
                        if mode == "completed":
                            with self.assertRaisesRegex(QueueError, "Terminal jobs cannot be cancelled"):
                                queue_instance.cancel(job_id)
                        elif mode == "failed":
                            with self.assertRaisesRegex(QueueError, "Stale, expired or revoked"):
                                queue_instance.fail(job_id=job_id, worker_id="confirmed-state-worker",
                                                    generation=lease["generation"],
                                                    error_code="LATE_FAILURE")
                        else:
                            self.assertEqual(queue_instance.cancel(job_id)["state"], "CANCELLED")
                    return snapshot

                with patch.object(StudioQueue, "get", new=attempt_terminal_mutation_after_confirmation):
                    recorded = self.store.record_queue_result(proposal_id=trial["proposal_id"],
                                                              queue_database=self.queue_path)
                self.assertEqual(recorded["status"], "RESULT_RECORDED")
                self.assertEqual(recorded["queue_state"], mode.upper())
                self.assertEqual(queue.get(trial["queue_job_id"])["state"], mode.upper())

    def test_failed_independent_review_defers_without_queue(self):
        router = SyntheticRouter(verdict="REVISE")
        content = "The caller supplied this local note."
        result = self.store.run_internal_script_trial(
            router=router, queue_database=self.queue_path, request_key="defer-review",
            brief="Create a short lesson.", language="en",
            evidence=[{"id": "note1", "source": "local note", "observed_at": "2026-11-11",
                       "claim": content, "content": content}])
        self.assertEqual(result["status"], "TRIAL_DEFERRED")
        self.assertEqual(result["outcome"], "DEFERRED")
        self.assertEqual(StudioQueue(self.queue_path).list_jobs(), [])

    def test_remote_or_unverified_evidence_cannot_auto_approve(self):
        router = SyntheticRouter()
        result = self.store.run_internal_script_trial(
            router=router, queue_database=self.queue_path, request_key="unverified-evidence",
            brief="Create a short lesson.", language="en",
            evidence=[{"id": "note1", "source": "web claim", "observed_at": "2026-11-11",
                       "claim": "Caller supplied an unverified statement."}])
        self.assertEqual(result["outcome"], "DEFERRED")
        self.assertEqual(StudioQueue(self.queue_path).list_jobs(), [])

    def test_trial_request_key_cannot_be_reused_for_different_input(self):
        router = SyntheticRouter()
        content = "Caller supplied curriculum text."
        args = {"router": router, "queue_database": self.queue_path,
                "request_key": "bound-trial-key", "brief": "Teach colors.",
                "language": "en", "evidence": [{"id": "note1", "source": "note",
                "observed_at": "2026-11-11", "claim": content, "content": content}]}
        self.store.run_internal_script_trial(**args)
        with self.assertRaisesRegex(ValueError, "different input"):
            self.store.run_internal_script_trial(**{**args, "brief": "Teach shapes."})

    def test_trial_recovers_if_process_stops_after_proposal_commit(self):
        router = SyntheticRouter()
        args = self.trial_args("crash-after-proposal", router)
        original_propose = self.store.propose

        def commit_then_interrupt(**kwargs):
            original_propose(**kwargs)
            raise RuntimeError("simulated process interruption after proposal commit")

        with patch.object(self.store, "propose", side_effect=commit_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "simulated process interruption"):
                self.store.run_internal_script_trial(**args)
        resumed = self.store.run_internal_script_trial(**args)
        self.assertEqual(resumed["status"], "INTERNAL_TRIAL_QUEUED")
        self.assertEqual([call["role"] for call in router.calls],
                         ["script_draft", "editorial_review"])

    def test_trial_recovers_after_independent_review_is_persisted(self):
        router = SyntheticRouter()
        args = self.trial_args("crash-after-review", router)
        original_review = self.store.record_agent_review

        def review_then_interrupt(**kwargs):
            original_review(**kwargs)
            raise RuntimeError("simulated interruption after review commit")

        with patch.object(self.store, "record_agent_review", side_effect=review_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "after review commit"):
                self.store.run_internal_script_trial(**args)
        resumed = self.store.run_internal_script_trial(**args)
        self.assertEqual(resumed["status"], "INTERNAL_TRIAL_QUEUED")
        self.assertEqual([call["role"] for call in router.calls],
                         ["script_draft", "editorial_review"])

    def test_trial_recovers_after_policy_decision_is_persisted(self):
        router = SyntheticRouter()
        args = self.trial_args("crash-after-policy", router)
        original_decide = self.store._policy_decide

        def decide_then_interrupt(**kwargs):
            original_decide(**kwargs)
            raise RuntimeError("simulated interruption after policy commit")

        with patch.object(self.store, "_policy_decide", side_effect=decide_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "after policy commit"):
                self.store.run_internal_script_trial(**args)
        resumed = self.store.run_internal_script_trial(**args)
        self.assertEqual(resumed["status"], "INTERNAL_TRIAL_QUEUED")
        self.assertEqual(len(StudioQueue(self.queue_path).list_jobs()), 1)
        self.assertEqual([call["role"] for call in router.calls],
                         ["script_draft", "editorial_review"])

    def test_trial_recovers_when_queue_enqueue_commits_before_dispatch_link(self):
        router = SyntheticRouter()
        args = self.trial_args("crash-between-queue-and-ledger", router)
        original_enqueue = StudioQueue.enqueue

        def enqueue_then_interrupt(queue, **kwargs):
            original_enqueue(queue, **kwargs)
            raise RuntimeError("simulated interruption after queue commit")

        with patch.object(StudioQueue, "enqueue", enqueue_then_interrupt):
            with self.assertRaisesRegex(RuntimeError, "after queue commit"):
                self.store.run_internal_script_trial(**args)
        resumed = self.store.run_internal_script_trial(**args)
        self.assertEqual(resumed["status"], "INTERNAL_TRIAL_QUEUED")
        self.assertEqual(len(StudioQueue(self.queue_path).list_jobs()), 1)

    def test_successor_links_old_proposal_for_re_evaluation(self):
        old = self.create()
        new = self.store.propose(
            request_key="colors-topic-v2",
            proposal=self.proposal(supersedes_id=old["proposal_id"],
                                   evidence=[{"source": "new-note", "observed_at": "2026-11-11",
                                              "claim": "New evidence changes expected demand.",
                                              "sha256": None}]))
        self.assertNotEqual(old["proposal_id"], new["proposal_id"])
        self.assertEqual(self.store.get(proposal_id=new["proposal_id"])["proposal"]["supersedes_id"],
                         old["proposal_id"])

    def test_successor_requires_existing_proposal(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.create(supersedes_id="0" * 32)

    def test_private_database_rejects_symlink_and_group_readable_file(self):
        link = self.root / "linked.sqlite"
        link.symlink_to(self.ledger_path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            StudioDirector(link).get(proposal_id="0" * 32)
        self.ledger_path.chmod(0o640)
        with self.assertRaisesRegex(ValueError, "private regular"):
            self.store.propose(request_key="colors-topic-v1", proposal=self.proposal())

    def test_legacy_v1_ledger_adds_director_extensions_without_losing_proposals(self):
        proposal = self.create()
        with sqlite3.connect(self.ledger_path) as db:
            for table in ("ai_pipeline", "policy_approvals", "results", "request_bindings"):
                db.execute("DROP TABLE " + table)
        migrated = StudioDirector(self.ledger_path)
        record = migrated.get(proposal_id=proposal["proposal_id"])
        self.assertEqual(record["proposal"]["title"], "Colors through play")
        self.assertIsNone(record["ai_pipeline"])
        decision = migrated.decide(proposal_id=proposal["proposal_id"], outcome="DEFERRED",
                                   actor="legacy-reviewer", rationale="Needs new evidence.")
        self.assertEqual(decision["outcome"], "DEFERRED")

    def test_legacy_unbound_proposal_cannot_reuse_trial_key(self):
        legacy = self.create()
        router = SyntheticRouter()
        args = self.trial_args("colors-topic-v1", router)
        with self.assertRaisesRegex(ValueError, "lacks atomic request/provenance binding"):
            self.store.run_internal_script_trial(**args)
        self.assertEqual(router.calls, [])
        after = self.store.get(proposal_id=legacy["proposal_id"])
        self.assertIsNone(after["decision"])
        self.assertIsNone(after["ai_pipeline"])
        self.assertEqual(StudioQueue(self.queue_path).list_jobs(), [])

    def test_legacy_unbound_proposal_can_only_be_replaced_by_linked_successor(self):
        legacy = self.create()
        original_sha = self.store.get(proposal_id=legacy["proposal_id"])["proposal_sha256"]
        router = SyntheticRouter()
        args = self.trial_args("colors-successor-v2", router)
        result = self.store.run_internal_script_trial(**args, supersedes_id=legacy["proposal_id"])
        self.assertEqual(result["status"], "INTERNAL_TRIAL_QUEUED")
        old_after = self.store.get(proposal_id=legacy["proposal_id"])
        new_after = self.store.get(proposal_id=result["proposal_id"])
        self.assertEqual(old_after["proposal_sha256"], original_sha)
        self.assertIsNone(old_after["decision"])
        self.assertEqual(new_after["proposal"]["supersedes_id"], legacy["proposal_id"])
        self.assertIn(legacy["proposal_id"], router.calls[0]["user_prompt"])
        self.assertNotIn("owner-research-note-01", router.calls[0]["user_prompt"])

    def test_successor_request_key_cannot_be_rebound_to_different_parent(self):
        first_parent = self.create()
        second_parent = self.store.propose(
            request_key="other-old-proposal",
            proposal=self.proposal(title="Another historical proposal"))
        router = SyntheticRouter()
        args = self.trial_args("bound-successor-request", router)
        self.store.run_internal_script_trial(**args, supersedes_id=first_parent["proposal_id"])
        self.assertEqual(len(router.calls), 2)
        with self.assertRaisesRegex(ValueError, "different input"):
            self.store.run_internal_script_trial(**args, supersedes_id=second_parent["proposal_id"])
        self.assertEqual(len(router.calls), 2)
        self.assertEqual(len(StudioQueue(self.queue_path).list_jobs()), 1)

    def test_successor_to_missing_legacy_proposal_fails_before_model_call(self):
        router = SyntheticRouter()
        args = self.trial_args("missing-successor-parent", router)
        with self.assertRaisesRegex(ValueError, "not found"):
            self.store.run_internal_script_trial(**args, supersedes_id="0" * 32)
        self.assertEqual(router.calls, [])
        self.assertEqual(StudioQueue(self.queue_path).list_jobs(), [])

    def test_legacy_unbound_proposal_with_pass_review_still_defers(self):
        content = "Locally supplied learning objective excerpt."
        proposal = self.store.propose(
            request_key="legacy-reviewed-unbound",
            proposal=self.proposal(
                effort_estimate={"hours": 2, "basis": "Existing estimate."},
                evidence=[{"source": "local note", "observed_at": "2026-11-11",
                           "claim": content, "content": content, "sha256": None}]),
        )
        with self.store._connection() as db:
            db.execute("""INSERT INTO ai_pipeline(
                proposal_id,generator_provider_id,generator_model,generator_prompt_sha256,
                generator_response_sha256,reviewer_provider_id,reviewer_model,
                reviewer_prompt_sha256,reviewer_response_sha256,review_verdict,
                review_rationale,evidence_supported,blocking_issues_json,
                assessment_sha256,created_at,reviewed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (proposal["proposal_id"], "writer-local", "model", "a" * 64, "b" * 64,
                 "reviewer-local", "model", "c" * 64, "d" * 64, "PASS",
                 "Synthetic legacy review.", 1, "[]", "e" * 64, 1.0, 1.0))
        decision = self.store._policy_decide(proposal_id=proposal["proposal_id"])
        self.assertEqual(decision["outcome"], "DEFERRED")
        self.assertIsNone(decision["policy_id"])
        with self.assertRaisesRegex(ValueError, "policy-approved"):
            self.store.enqueue_accepted(proposal_id=proposal["proposal_id"],
                                        queue_database=self.queue_path)


if __name__ == "__main__":
    unittest.main()
