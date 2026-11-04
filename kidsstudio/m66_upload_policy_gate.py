"""M66 offline policy gate for a proposed PRIVATE insert.

This is a standalone testable gate, NOT yet wired to the production Pi uploader.
It intentionally fails closed on malformed input or uncertain journal state.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from kidsstudio.m66_upload_journal_model import may_insert, JournalError


@dataclass(frozen=True)
class Policy:
    enabled: bool
    paused: bool
    revision_requested: bool
    owner_approved_for_private_upload: bool
    privacy: str
    daily_limit: int
    already_uploaded_today: int


def can_start_private_upload(policy: Policy, journal: Path) -> bool:
    if type(policy.enabled) is not bool or type(policy.paused) is not bool:
        return False
    if type(policy.revision_requested) is not bool or type(policy.owner_approved_for_private_upload) is not bool:
        return False
    if type(policy.daily_limit) is not int or type(policy.already_uploaded_today) is not int:
        return False
    if policy.daily_limit <= 0 or not (0 <= policy.already_uploaded_today < policy.daily_limit):
        return False
    if policy.privacy != "private" or not policy.enabled or policy.paused:
        return False
    if policy.revision_requested or not policy.owner_approved_for_private_upload:
        return False
    try:
        return may_insert(journal)
    except (JournalError, OSError):
        return False
