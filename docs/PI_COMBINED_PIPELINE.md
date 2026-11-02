# Combined Pi private upload pipeline

`kidsstudio.pi_pipeline_service` runs the verified staging watcher and
private upload queue worker under one exclusive process lock. It uses
`/var/lib/kidsstudio/private-upload` for staging, inbox, sessions,
queue and binding ledger.

The Mac transfers an MP4 and its checksum manifest into the staging
directory via SSH. The Pi checks the exact file digest, creates a
private YouTube upload session and queues it. The worker resumes
the session, verifies the uploaded video's channel and private status,
then records the local media binding.

Trusted episode titles live in a separate JSON mapping, for example:
`{"red-ar": "Learn Red | تعلم اللون الأحمر"}`.
This metadata is not accepted from the Mac staging manifest.

A deployment template is in
`deploy/systemd/kidsstudio-pi-pipeline.service`.
Do **not** enable it alongside the older
`kidsstudio-pi-upload.service`: both operate on the same queue and lock.

**Before enabling:** provision a dedicated unprivileged user, private
directories and mode-0600 OAuth credentials, configure SSH, test the
`--once` command and verify one real private upload. The watcher and
worker run synchronously in each tick; a long upload delays scanning.
Failed jobs remain failed for operator inspection. No public
publishing functionality is included.
