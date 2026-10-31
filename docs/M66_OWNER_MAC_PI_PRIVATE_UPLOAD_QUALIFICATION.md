# M66 — Mac → Pi → YouTube PRIVATE owner qualification

Status: TEST PLAN ONLY. No physical Mac/Pi execution, OAuth, upload, or public publishing has been performed by this change. PR #28 stays draft.

## Non-negotiable invariants
1. Mac is producer only. Pi is durable media owner and sole Google OAuth/upload actor.
2. Every transferred master is immutable, SHA-256 verified and stored on Pi before any upload admission.
3. Upload destination is PRIVATE only; publication requires separate explicit owner action.
4. Unknown resumable-session state MUST NOT call videos.insert again. Mark NEEDS_RECONCILIATION and require read-only inspection.
5. Recovery and ordinary uploads share the same daily budget and reject duplicate master/video identity.
6. Rejected review keeps evidence, timestamps and notes; it does not make the video public.

## Test matrix (run with synthetic credentials/media first)
| ID | Fault injection | Expected invariant |
| --- | --- | --- |
| M66-01 | Partial .part rsync transfer, disconnect | Resume; no visible complete inbox object until full hash matches |
| M66-02 | Flip one Pi byte after transfer | Quarantine; never enqueue upload |
| M66-03 | Mac powered down after Pi receipt | Pi worker continues independently |
| M66-04 | Pi service restart before Google HTTP | One durable lease/journal; no duplicate videos.insert |
| M66-05 | Connection lost after videos.insert uncertain outcome | NEEDS_RECONCILIATION; no automatic second insert |
| M66-06 | Google processing pending | GET-only verification using recorded video ID |
| M66-07 | Owner policy revision/pause after enqueue | Fail closed before Google call |
| M66-08 | Ordinary/recovery concurrent claims | Enforce shared budget, no cross-namespace duplicate video ID |
| M66-09 | Rejected or pending owner review | Remains PRIVATE, feedback retained |
| M66-10 | Pi reboot mid-upload | No duplicate insert; resume only if server-confirmed resumable session is proven safe, else manual reconciliation |

## Qualification gates
A. Offline automated tests + real FFmpeg full-decode fixture green.
B. LAN-only Mac/Pi test with 100MB+ non-sensitive fixture; record hashes, rsync resume, Pi persistent storage, Mac shutdown and Pi reboot.
C. Pi OAuth configured privately by owner; upload one expendable sample to a test/private destination. Confirm videos.list channel, privacyStatus=private, processing state and video ID. No public action.
D. Repeat controlled failure tests with network drops; if the Google resumable outcome is ambiguous, stop instead of re-uploading.
E. Owner signs off one actual educational episode after child-safety, rights, pedagogy, captions and preview checks.

## Evidence record per run
Record UTC timestamp, test ID, code SHA, Mac/Pi OS, source SHA256, Pi SHA256, transfer status, Pi service journal state, Google video ID (if present), privacyStatus, processingStatus, retry count, owner review status and failure trace. Never store OAuth secrets or private media paths in public CI logs.

## Exit criteria
No duplicate uploads; no unexpected PUBLIC state; no unverified media; Pi continues with Mac offline; reboot ambiguity fails closed; owner can review and annotate; all evidence attached privately. Only then consider PR merge.