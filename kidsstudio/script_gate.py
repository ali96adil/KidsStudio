"""Shared M33 current-script authorization for M21/M22 Pi+Mac voice pilot.

This is PRIVATE-only internal authorization. Owner legacy and current
two-independent-model M30 script review are distinct modes. A user-editable
note alone never authorizes a pilot; M30 also needs its exact immutable
review ledger and audit. This module does not approve a video or PUBLIC.
"""
from __future__ import annotations

import re

SHA = re.compile(r"^[0-9a-f]{64}$")
AI_NOTE = "M30_TWO_INDEPENDENT_AI_INTERNAL_PRIVATE_ONLY"
AI_ACTION = "SCRIPT_APPROVED_BY_TWO_INDEPENDENT_AI_PRIVATE_ONLY"

def current_script_mode(db, sid: str, ordinal: int) -> str | None:
    ep=db.execute("""SELECT e.state,e.revision,e.source_sha256,
            e.draft_job_id,e.owner_review_note,s.state AS series_state
        FROM studio_episodes e JOIN studio_series s
            ON s.series_id=e.series_id
        WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
    if (not ep or ep["state"]!="SCRIPT_APPROVED" or
        ep["series_state"]!="ACTIVE" or
        not isinstance(ep["source_sha256"],str) or
        not SHA.fullmatch(ep["source_sha256"]) or
        not isinstance(ep["owner_review_note"],str) or
        len(ep["owner_review_note"].strip())<5):
        return None
    if ep["owner_review_note"]==AI_NOTE:
        has=db.execute("""SELECT 1 FROM sqlite_master WHERE
            type='table' AND name='studio_script_ai_reviews'""").fetchone()
        if not has:return None
        proof=db.execute("""SELECT 1 FROM studio_script_ai_reviews
            WHERE series_id=? AND ordinal=? AND revision=?
              AND original_sha256=? AND draft_job_id=?
              AND verdict='AI_SCRIPT_PRIVATE_READY'
              AND first_provider!=second_provider
              AND first_report_sha256 GLOB '[0-9a-f]*'
              AND length(first_report_sha256)=64
              AND second_report_sha256 GLOB '[0-9a-f]*'
              AND length(second_report_sha256)=64
              AND length(report_bundle_sha256)=64""",
            (sid,ordinal,ep["revision"],ep["source_sha256"],
             ep["draft_job_id"])).fetchone()
        audit=db.execute("""SELECT 1 FROM studio_series_audit
            WHERE series_id=? AND ordinal=? AND action=?""",
            (sid,ordinal,AI_ACTION)).fetchone()
        return "AI_PRIVATE_SCRIPT" if proof and audit else None
    if db.execute("""SELECT 1 FROM studio_series_audit
        WHERE series_id=? AND ordinal=?
          AND action='SCRIPT_APPROVED_BY_OWNER'""",
        (sid,ordinal)).fetchone():
        return "OWNER_SCRIPT"
    return None
