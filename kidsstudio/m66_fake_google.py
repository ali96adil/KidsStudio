"""M66 deterministic fake Google upload transport.

Pure offline test harness: it never calls Google. Models the dangerous gap
between a durable STARTED marker and a remote response.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kidsstudio.m66_upload_journal_model import (
    JournalError, begin_insert, may_insert, read, verified_private,
    UNCERTAIN, VERIFIED,
)


@dataclass
class FakeGoogle:
    inserts: int = 0
    video_id: str = "fake-private-video"
    remote_private: bool = True
    processed: bool = True
    lose_response: bool = False

    def insert(self) -> str:
        self.inserts += 1
        if self.lose_response:
            raise ConnectionError("simulated response lost after remote insert")
        return self.video_id

    def get(self, video_id: str) -> dict:
        if video_id != self.video_id:
            raise LookupError("remote id not found")
        return {"id": self.video_id, "private": self.remote_private, "processed": self.processed}


def start(path: Path, remote: FakeGoogle) -> str:
    """Mark uncertainty on durable storage before invoking remote insert."""
    if not may_insert(path):
        raise JournalError("insert blocked: pending reconciliation or completed")
    begin_insert(path)
    return remote.insert()


def reconcile_known_id(path: Path, remote: FakeGoogle, video_id: str) -> None:
    """GET-only reconciliation; never issues an insert."""
    if read(path)["state"] != UNCERTAIN:
        raise JournalError("reconciliation not pending")
    status = remote.get(video_id)
    if status["id"] != video_id:
        raise JournalError("remote id mismatch")
    verified_private(
        path, video_id,
        remote_private=status["private"],
        processed=status["processed"],
    )


def state(path: Path) -> str:
    return read(path)["state"]
