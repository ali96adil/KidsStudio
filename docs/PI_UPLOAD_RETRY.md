# Pi upload retry policy

`kidsstudio.pi_upload_retry.resume_with_retries` resumes a saved private
upload session with at most five attempts by default, exponential delays
starting at two seconds and capped at thirty seconds.

Each attempt revalidates the local media fingerprint and asks YouTube for
its authoritative resumable upload offset. Network failures, timeouts and
HTTP 408/409/429/5xx are retryable. HTTP 401/403 and other permanent
errors are not retried. Failed media integrity checks stop immediately.

The runner never changes a video's privacy to public.

**Still required before production:** OAuth token renewal during long
uploads, durable process supervision (for example systemd), recovery
after Pi reboot, handling expired upload sessions, verifying the uploader
does not start duplicate uploads, and a live test against a private
YouTube channel. The retry helper itself does not run in the background.
