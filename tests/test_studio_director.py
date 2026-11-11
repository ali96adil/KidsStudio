import json
import os
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_director import StudioDirector
from kidsstudio.studio_queue import StudioQueue


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

    def test_decision_binds_evidence_and_is_immutable(self):
        proposal = self.create()
        first = self.store.decide(proposal_id=proposal["proposal_id"], outcome="ACCEPTED",
                                  actor="director.editorial", rationale="Evidence supports a story format.")
        same = self.store.decide(proposal_id=proposal["proposal_id"], outcome="ACCEPTED",
                                 actor="director.editorial", rationale="Evidence supports a story format.")
        self.assertEqual(first["decision_id"], same["decision_id"])
        self.assertEqual(len(first["evidence_sha256"]), 64)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.store.decide(proposal_id=proposal["proposal_id"], outcome="REJECTED",
                              actor="director.editorial", rationale="New opinion.")
        record = self.store.get(proposal_id=proposal["proposal_id"])
        self.assertFalse(record["evidence_verified"])
        self.assertFalse(record["owner_publication_approval"])

    def test_rejected_or_deferred_proposals_cannot_enqueue(self):
        proposal = self.create()
        deferred = self.store.propose(request_key="colors-topic-deferred",
                                      proposal=self.proposal(title="Maybe later"))
        for current, outcome in ((proposal, "REJECTED"), (deferred, "DEFERRED")):
            self.store.decide(proposal_id=current["proposal_id"], outcome=outcome,
                              actor="director", rationale="Not supported now.")
            with self.assertRaisesRegex(ValueError, "accepted"):
                self.store.enqueue_accepted(proposal_id=current["proposal_id"],
                                            queue_database=self.queue_path)
        jobs = StudioQueue(self.queue_path).list_jobs()
        self.assertEqual(jobs, [])

    def test_only_explicitly_accepted_proposal_creates_idempotent_queue_job(self):
        proposal = self.create()
        with self.assertRaisesRegex(ValueError, "accepted"):
            self.store.enqueue_accepted(proposal_id=proposal["proposal_id"],
                                        queue_database=self.queue_path)
        self.store.decide(proposal_id=proposal["proposal_id"], outcome="ACCEPTED",
                          actor="director", rationale="Proceed with a bounded Arabic draft.")
        first = self.store.enqueue_accepted(proposal_id=proposal["proposal_id"],
                                            queue_database=self.queue_path)
        second = self.store.enqueue_accepted(proposal_id=proposal["proposal_id"],
                                             queue_database=self.queue_path)
        self.assertEqual(first["queue_job_id"], second["queue_job_id"])
        self.assertFalse(first["execution_started"])
        jobs = StudioQueue(self.queue_path).list_jobs()
        self.assertEqual(len(jobs), 1)
        payload = json.loads(jobs[0]["payload"])
        self.assertEqual(payload["studio_proposal_id"], proposal["proposal_id"])
        self.assertEqual(payload["studio_decision_id"], first["decision_id"])

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


if __name__ == "__main__":
    unittest.main()
