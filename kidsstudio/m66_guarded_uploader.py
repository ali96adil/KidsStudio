"""M66 offline guarded uploader orchestrator.

Combines policy, durable uncertainty journal, and fake transport.
Not connected to the production Pi uploader or Google API.
"""
from __future__ import annotations

from pathlib import Path
from kidsstudio.m66_fake_google import FakeGoogle, reconcile_known_id, start
from kidsstudio.m66_upload_journal_model import JournalError, read
from kidsstudio.m66_upload_policy_gate import Policy, can_start_private_upload


def attempt_private_upload(policy: Policy, journal: Path, remote: FakeGoogle) -> str:
    """Return remote ID only if a policy-approved attempt gets a response.

    On connection failure, journal remains RECONCILIATION_REQUIRED and the
    caller must not retry automatically. Reconciliation is a separate step.
    """
    if not can_start_private_upload(policy, journal):
        raise JournalError("private upload blocked by policy or journal")
    return start(journal, remote)


def reconcile_private_upload(journal: Path, remote: FakeGoogle, known_id: str) -> str:
    """GET-only verification, never inserts or bypasses the journal."""
    reconcile_known_id(journal, remote, known_id)
    return read(journal)["state"]
