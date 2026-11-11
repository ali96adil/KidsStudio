import json
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.studio_director import StudioDirector
from kidsstudio.studio_queue import StudioQueue
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


if __name__ == "__main__":
    unittest.main()
