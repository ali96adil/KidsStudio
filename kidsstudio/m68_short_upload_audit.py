"""M68 audit the existing M65 upload attempt journal for a derived short.

This is read-only and intentionally never retries an uncertain YouTube upload.
"""
from __future__ import annotations

import re

from .youtube_private_upload import UploadJournal


JOB = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class ShortUploadAuditError(ValueError):
    pass


def audit_short_upload(journal_path, *, short_id, render_job_id,
                       media_sha256, registry_record):
    if (not isinstance(render_job_id, str) or not JOB.fullmatch(render_job_id)
            or not isinstance(media_sha256, str) or not SHA.fullmatch(media_sha256)
            or not isinstance(registry_record, dict)
            or registry_record.get("short_id") != short_id
            or registry_record.get("media_sha256") != media_sha256
            or registry_record.get("status") != "PI_STAGED_NOT_APPROVED"):
        raise ShortUploadAuditError("matching staged short identity required")
    journal = UploadJournal(journal_path)
    attempt = journal.status(render_job_id)
    if attempt is None:
        return {
            "status": "NO_UPLOAD_ATTEMPT_M65_APPROVAL_REQUIRED",
            "short_id": short_id, "render_job_id": render_job_id,
            "youtube_uploaded": False, "retry_authorized": False,
            "public_release_authorized": False,
        }
    if attempt["master_sha256"] != media_sha256:
        raise ShortUploadAuditError("upload journal digest conflicts with short")
    return {
        "status": "EXISTING_UPLOAD_ATTEMPT_REQUIRES_M65_RECONCILIATION",
        "short_id": short_id, "render_job_id": render_job_id,
        "attempt_state": attempt["state"],
        "youtube_video_id": attempt["video_id"],
        "retry_authorized": False,
        "public_release_authorized": False,
    }
