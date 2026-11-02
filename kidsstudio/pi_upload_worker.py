"""One-shot Pi upload worker; invoke repeatedly via service manager."""
from __future__ import annotations

from .pi_upload_queue import PiUploadQueue
from .pi_upload_supervisor import supervise_resume
from .youtube_upload_binding import UploadBindingStore

def process_one(queue: PiUploadQueue, bindings: UploadBindingStore, token_provider) -> dict | None:
    job = queue.claim()
    if job is None:
        return None
    try:
        result = supervise_resume(
            bindings,
            episode_id=job["episode_id"],
            session_path=job["session_path"],
            expected_channel_id=job["channel_id"],
            token_provider=token_provider,
        )
    except Exception:
        # Never write raw exceptions (OAuth/session URLs may be sensitive).
        queue.finish(job["id"], success=False, error="upload recovery failed")
        raise
    queue.finish(job["id"], success=True)
    return {"job_id": job["id"], "episode_id": job["episode_id"], "result": result}
