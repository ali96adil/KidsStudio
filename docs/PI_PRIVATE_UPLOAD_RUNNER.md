# Raspberry Pi private upload runner

`kidsstudio.pi_private_upload_runner` composes the existing upload modules.

- `start_private_upload(...)` creates a resumable upload session with
  private privacy, atomically persists the session, uploads the MP4, then
  **independently inspects** the resulting YouTube video ID, channel ID,
  and private status before recording the local media SHA-256 binding.
- `resume_private_upload(...)` reads a private session file, verifies
  that the video has not changed, queries YouTube's server-side progress,
  resumes transfer and performs the same independent verification.

The caller must supply a valid OAuth access token with the appropriate
YouTube upload and read permissions. The session file and database must
be stored outside the repository. Do not reuse a session after a
successful upload. No automatic retries, OAuth refresh during upload,
process supervisor, or real account integration are provided yet.

The uploader does not authorize publication and does not change an
existing video's privacy. The returned binding is not proof of the
remote video's content bytes: YouTube may transcode uploaded media.
