# Kids Studio — Autonomous Development Handoff

Updated: 2026-11-12

## Repository state

- Repository: `ali96adil/KidsStudio`
- Branch: `feature/production-intelligence-safe-integration`
- Draft PR: #33 — open, draft, not merged.
- Current code head: `5e3a6c3bd9f18ad3abee94519454ff77195d2f98`.
- Latest regression/test head: `5e3a6c3bd9f18ad3abee94519454ff77195d2f98`.
- Previous Handoff commit: `e35ccd4af327d9f1a9109a378d7daa0f0274d5a6`.
- Rollback before Batch 76B: `6b1e6f9bbcc488824c17536d4c1912ad8a779afd`.
- Rollback before Batch 76A: `885efc729910597458b30031563f9969c960965b`.
- Rollback before Batch 75P: `a9191d642c21f301e999eefdfa995340f8fc2ae4`.
- Rollback before Batch 75O: `139a8dfc0d25b8454983be0cb1649b8b91fdfd1c`.
- Rollback before Batch 75N: `e13c9ac26c6113f3a3ad8eb51c365a3ddb597200`.
- Rollback before Batch 75M: `c7bebde6785cec00a6254bc35f47d1f7b11dc1dd`.
- Rollback before Batch 75L: `17461df42970bd555d54cba745d61d1ae97bf4b7`.
- Rollback before Batch 75K: `d5f267388c6f74fe5b3bacfbbe7766959e463c8b`.
- Rollback before Batch 75J: `f65df1eb2c65dd06e7b05ee38c4ec41fb42e290e`.
- Rollback before Batch 75I: `aa191c328ca644a926bfa12eec2567716a744f32`.
- Rollback before Batch 75H: `c7d9e2d84f4f7167ed9fa0a6fc29b89fc29d1e25`.
- Rollback before Batch 75G: `f1b035e66eeb19c381cb11f8a25c1f20807c8138`.
- Rollback before Batch 75F: `9b69cabe016f0d739e99eaad967465d1d515b22a`.
- Rollback before Batch 75E: `ba64db7117a8c4161626300654ad9292ea003ca9`.
- Rollback before Batch 75D: `ce72200af66b21aa05a04bf62d39fbae5cfa41c4`.
- Rollback before Batch 75C: `34e895fae3249e6414dfeff1f49b407bf8b32b48`.
- Rollback before Batch 75B: `1b347f395c5f6fd6e0cc5775c60d723b7bad7b37`.
- Rollback before Batch 75A: `c0ef2d1c03b43c434122af6242c3610547667ab2`.
- Rollback before Batch 74T: `207f0e859edc8c76d0973d9b29e74de491e9bffe`.
- Rollback before Batch 74S: `87e42cf1ce1dedfdb85deddfec3ef9faa110d590`.
- Rollback before Batch 74R: `0ca6da65ab936dd5e40f210c0a650714c5611c41`.
- Rollback before Batch 74Q: `8728906d455cd56f0e005861efffa1418371fa3a`.
- Rollback before Batch 74P: `197e23cd7af83bfe0384abc45b3fec819d1086eb`.
- Rollback before Batch 74O: `3237ef715b017a94b19ac4f21dee528d0a8b15f7`.
- Rollback before Batch 74N: `39c0457595c4e3750c00fb991db7b07ebe01f29c`.
- Rollback before Batch 74M: `fefb67bcd981d171f03971be9ac4071f8fbea250`.
- Rollback before Batch 74L: `05e29ed502ce7f17eae390e00f1bcb9e5907fa59`.
- Rollback before Batch 74K: `6c7fff7d9c6621e7025b0b3c6e5675ed283cf15f`.
- Rollback before Batch 74J: `dce5b3e59572f62f5f50e880f0afab5ced6e2734`.
- Rollback before Batch 74I: `68fbb4ffc486a79eef8fa669c88fca40915f6624`.
- Rollback before Batch 74H: `64021e00f85c5213571aac5252a3d1f6e30690f5`.
- Rollback before Batch 74G: `32426522fc7c58b80617f58bd03830dc13953a8b`.
- Previous qualified code/test head before Batch 74F: `3cb4b849b6ebf88afbcdccf3277649e2c581a9c7`.
- Branch head before Batch 75D: `ce72200af66b21aa05a04bf62d39fbae5cfa41c4`.
- Rollback before Batch 74F: `f59abf92ff39280821b607f0ca966735afdf5836`.
- Rollback before Batch 74E: `fa8c44992f0500b177acde5129c4fa46fc3c8fb7`.
- Rollback before Batch 74D: `b6734c3bc6fb6b9008af17f9776c162d97f4a5ba`.
- Rollback before Batch 74C: `af246798f2f5d56ec5ba8cb3b182bb0986be4615`.
- Regression-only rollback before Batch 74B: `2943b7f49a207b01cb32849ae60ff0939fb1e1bc`.
- Code rollback before Batch 74A: `56e488b86b3add00ee9746700642d4841cc042a9`.
- Earlier regression qualification reference: `0f5c7140efb4020db39bb2df6e742d6203d559bb`.

## Last completed batch

### Batch 76F — Bind Director results to completed editorial review

- A regression showed `record_queue_result` could persist a completed `DRAFTED_UNREVIEWED` parent job while its linked `editorial_review` job was still queued. This also made an unreviewed trial eligible for measurement ingestion.
- Director now waits for the exact linked review job to complete, checks its source job, draft SHA, original writer provider and distinct reviewer provider, and requires the result to remain explicitly `EDITORIAL_REVIEW_UNVERIFIED` with publication approval false.
- The result digest binds both stage results; the ledger still stores no draft or review text. Pending, failed, or mismatched review leaves no Director result row, so `record_measurement` remains ineligible.
- `tests.test_studio_director`: **51 passed**; `python scripts/run_tests.py`: **931 passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- GitHub checks on Batch 76F code/test head `5e3a6c3bd9f18ad3abee94519454ff77195d2f98` all succeeded: CI `43307200667`, macOS `43307200704`, Godot `43307200691`, and FFmpeg `43307200636`. Only synthetic providers/artifacts were used; no external research, paid API, child-level data, upload or publication occurred.
- Rollback before Batch 76F: `e35ccd4af327d9f1a9109a378d7daa0f0274d5a6`.

### Batch 76E — Route Director drafts to independent Queue review

- A regression first showed that Director-created `script_draft` jobs set `auto_review=False`, so the local worker completed a draft without creating the existing linked `editorial_review` job.
- The trial path now sets `auto_review=True`. The existing queue operation atomically completes the draft and enqueues an independent review linked by source job ID, draft SHA-256, and original provider ID. The review remains unverified and does not approve publication.
- The Director-to-Queue regression verifies the requested handoff metadata, absence of copied script text, separate reviewer provider, and a completed synthetic review result. The existing local-worker integration test also passes.
- Local verification: `tests.test_studio_director`: **51 passed**; `python scripts/run_tests.py`: **931 passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- GitHub checks on Batch 76E code/test head `6ce37d6da9312ef06f8c761c0f24c259e143e353` all succeeded: CI `43305631424`, macOS `43305631132`, Godot `43305631050`, and FFmpeg `43305631252`. Only synthetic providers/artifacts were used; no external research, paid API, child-level data, upload, or publication occurred.
- Rollback before Batch 76E: `6e38c05f891e90572fd6d95bd00a3896e251207d`.

### Batch 76D — Qualify concurrent measurement idempotency

- Added a deterministic concurrent-retry regression: two threads record the same aggregate measurement with the same request key at once. Exactly one receipt is inserted; callers receive `MEASUREMENT_RECORDED` and `MEASUREMENT_EXISTS` with the same measurement ID and digest.
- The existing `BEGIN IMMEDIATE` transaction and unique request-key constraint serialized the retries correctly. No production-code fix was needed.
- `tests.test_studio_director`: **51 passed**; `python scripts/run_tests.py`: **931 passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- GitHub checks on code/test head `69cf55df39f6734c7e4759ea0562a46f789b3f05` all succeeded: CI `43303870074`, macOS `43303870067`, Godot `43303870076`, and FFmpeg `43303870421`. No source, analytics service, child-level data, or external API was used.
- Rollback before Batch 76D: `257ac5851e80f2cb3a60eead0c9fd396d64de7e2`.

### Batch 76C — Require new evidence for trial successors

- Internal successor trials must include at least one evidence item whose source, observed date, claim, or excerpt differs from the superseded proposal, and the generated successor must cite changed material. Renaming an evidence ID alone is insufficient. The check compares caller-supplied text only; it does not authenticate sources or establish factual truth.
- The intermediate commit `73aa49443da35fa9f7a57f21892f4e625bd936f9` contained literal truncation markers in `kidsstudio/studio_director.py` and `tests/test_studio_director.py` (`…2209 tokens truncated…`, `…2428 tokens truncated…`). Python imports failed with `SyntaxError` (`studio_director.py:527`), and its CI, macOS and Godot runs failed; the FFmpeg smoke passed. This was an incomplete file transfer, not a project regression. The complete files were restored from their correct Git objects in commit `257ac5851e80f2cb3a60eead0c9fd396d64de7e2`; no production repair was repeated.
- On restored code head `257ac5851e80f2cb3a60eead0c9fd396d64de7e2`, `python scripts/run_tests.py`: **930 passed**; `tests.test_studio_director`: **50 passed**; `python -m compileall -q kidsstudio tests scripts`, `git diff --check`, and `git fsck --no-reflogs --unreachable --no-progress` passed.
- GitHub runs on the restored head all succeeded: CI `43296012922`, macOS `43296013332`, Godot `43296012900`, FFmpeg `43296012854`. Intermediate head `73aa49443da35fa9f7a57f21892f4e625bd936f9` runs: CI `43295551285`, macOS `43295551448`, and Godot `43295551197` failed from the truncated Python files; FFmpeg `43295551350` succeeded.
- Rollback before Batch 76C code: `ef5e82bdb31fa4889de0730f71441704234c20df`.

### Batch 76B — Validate measurement calendar dates

- A regression showed the first measurement validator accepted impossible calendar values such as `2026-99-99`: the format regex checked shape but not calendar validity.
- Measurement ingestion now parses the date/timestamp with Python's ISO datetime parser after the shape check and rejects invalid calendar values before persistence. The test also checks an unrecognized source kind remains rejected and confirms no row is written on failure.
- `tests.test_studio_director`: **49 passed**; `python scripts/run_tests.py`: **929 passed**; `python -m compileall -q kidsstudio tests` and `git diff --check` passed.
- GitHub checks on code head `ef5e82bdb31fa4889de0730f71441704234c20df`: CI `43294426534`, macOS `43294426331`, Godot `43294426311`, and FFmpeg `43294426299` were **in progress** at handoff update; do not treat these as passes until completed.
- Rollback before Batch 76B: `6b1e6f9bbcc488824c17536d4c1912ad8a779afd`.

### Batch 76A — Add privacy-safe aggregate measurement receipts

- Added an append-only local measurement table to the existing Studio Director ledger. A record requires an accepted proposal with a completed queue result, a caller-provided episode-version SHA, a stable idempotency key, an ISO date/timestamp and a bounded allowlisted aggregate metric set.
- Only aggregate counters/durations are supported; child IDs, demographic rows, comments, free-text metric keys, booleans, negative, non-finite and out-of-range values are rejected. Reusing a key with different measurement material fails closed.
- Every row is labeled `CALLER_SUPPLIED_UNVERIFIED`; source kinds are caller assertions only. No analytics service connection, source verification, child-level collection, profit calculation, spending decision or publication action exists. A hash binds stored bytes; it does not prove source truth or episode identity.
- `tests.test_studio_director`: **48 passed**; `python scripts/run_tests.py`: **928 passed**; compileall and `git diff --check` passed.
- On code head `2c3c88c679b1e6412c05349dd7023962309cbf91`, CI `43293699134`, Godot `43293699220`, FFmpeg `43293699184`, and macOS `43293699231` all completed successfully.
- Rollback before Batch 76A: `885efc729910597458b30031563f9969c960965b`.

### Batch 75P — Recover after losing the final upload response

- Added a synthetic regression for the server completing the last chunk while the client loses its final response. A retry probes the existing resumable session, recovers the video ID, verifies PRIVATE status, and does not create another session or resend chunks.
- Existing implementation passed the recovery scenario; no production change was needed. `python -m unittest tests.test_pi_youtube_private_upload -q`: **33 passed**; `python scripts/run_tests.py`: **924 passed**; compileall and `git diff --check` passed.
- On test head `4c7be423e8b39cb49733e378e5f717832d262d74`, CI `43292096183`, macOS `43292096247`, FFmpeg `43292096180`, and Godot `43292096143` all succeeded.
- Only synthetic transport and media were used. No real OAuth, upload, publication, spending, or device operation. Rollback before Batch 75P: `a9191d642c21f301e999eefdfa995340f8fc2ae4`.

### Batch 75O — Normalize oversized resumable ranges

- A Regression first showed that a syntactically digit-only but 5,000-digit `Range` from the resumable response escaped as Python's raw `ValueError` during integer conversion.
- `_offset` now converts that conversion failure to the uploader's controlled `YouTubePrivateError`, preserving fail-closed behavior and preventing parser details from escaping to direct callers.
- `python -m unittest tests.test_pi_youtube_private_upload -q`: **32 passed**; `python scripts/run_tests.py`: **923 passed**; compileall and `git diff --check` passed.
- On code head `6be355993a0c2742935fe91cef8cea0b2b20fd32`, CI `43290801982`, Godot `43290802120`, and FFmpeg `43290802085` succeeded; macOS `43290802030` remained in progress at the latest check.
- Only synthetic media and transport were used. No real OAuth/upload, spending, publication, or device operation. Rollback before Batch 75O: `139a8dfc0d25b8454983be0cb1649b8b91fdfd1c`.

### Batch 75N — Validate missing active upload session safely

- A regression first reproduced that an interrupted `SESSION_ACTIVE` journal with a missing `session_url` leaked a raw `KeyError` from the Python API instead of the uploader's safe `YouTubePrivateError` contract. No OAuth token or transport call occurred, but the exception type was inconsistent.
- Recovery now validates the optional persisted value through the existing strict session URL validator; missing or malformed values produce the controlled error before token/network use. The tampered journal is preserved.
- `python -m unittest tests.test_pi_youtube_private_upload -q`: **31 passed**; `python scripts/run_tests.py`: **922 passed**; compileall and `git diff --check` passed.
- On head `33e229917339aaf50e94bd5de5a958e5f59a09b8`, CI `43244535932`, macOS `43244535757`, Godot `43244535805`, and FFmpeg `43244535821` all completed successfully.
- Only synthetic media/transports/tokens were used. No real OAuth/upload, spending, publication, or device operation. Rollback before Batch 75N: `e13c9ac26c6113f3a3ad8eb51c365a3ddb597200`.

### Batch 75M — Test resumable upload recovery boundaries

- Regression coverage simulates a lost chunk response after the synthetic server has acknowledged bytes. On retry, the uploader probes the same resumable session, resumes at the server-confirmed range, and does not start a duplicate session.
- A stale local `bytes_remote_acknowledged` hint is ignored; remote probe state remains authoritative. A tampered active session URL is rejected before OAuth token retrieval or transport, with the journal preserved.
- No production-code defect was demonstrated, so this batch changes tests only. `python -m unittest tests.test_pi_youtube_private_upload -q`: **30 passed**; `python scripts/run_tests.py`: **921 passed**; compileall and `git diff --check` passed.
- CI `43243711663`, FFmpeg `43243711631`, and Godot `43243711676` succeeded on test head `e13c9ac26c6113f3a3ad8eb51c365a3ddb597200`; macOS `43243717529` remained queued at the last direct check.
- The macOS run `43243717529` for test head `e13c9ac26c6113f3a3ad8eb51c365a3ddb597200` remained queued at the last direct check; the subsequent full macOS run `43244535757` passed on the later Batch 75N head. The previous Handoff-only head `c7bebde6785cec00a6254bc35f47d1f7b11dc1dd` also completed CI `43242838412`, macOS `43242838518`, Godot `43242838393`, and FFmpeg `43242838439` successfully. Only fake local transports/tokens were used; no real OAuth/upload, publication, spending, or device operation. Rollback before Batch 75M: `c7bebde6785cec00a6254bc35f47d1f7b11dc1dd`.

### Batch 75L — Enforce state-specific uploader journal fields

- Regressions showed `SESSION_ACTIVE` accepted an unexpected terminal `video_id`, and `PRIVATE_UPLOAD_CONFIRMED` accepted a leftover `session_url`; both records proceeded to token/transport calls.
- Journal validation now rejects `video_id` on `SESSION_ACTIVE` and `session_url` on terminal states (`PRIVATE_UPLOAD_CONFIRMED`, `REMOTE_COMPLETED_UNVERIFIED`). The conflicting journal is preserved unchanged, and rejection occurs before OAuth token or transport access.
- `python -m unittest tests.test_pi_youtube_private_upload -q`: **28 passed**; `python scripts/run_tests.py`: **919 passed**; compileall and `git diff --check` passed.
- On code head `d39d3a351c00e1f62f902575176dfa0f98145ccf`, CI `43242635002`, FFmpeg `43242634966`, and Godot `43242634986` succeeded; macOS `43242635126` was queued at the last direct check. The subsequent Handoff commit checks all passed on `c7bebde6785cec00a6254bc35f47d1f7b11dc1dd`.
- Only synthetic transports and tokens were used. No real OAuth, upload, owner device, publication or spending. Rollback before Batch 75L: `17461df42970bd555d54cba745d61d1ae97bf4b7`.

### Batch 75K — Validate persisted video IDs before status checks

- Regressions showed confirmed and `REMOTE_COMPLETED_UNVERIFIED` journals accepted an invalid `video_id` until after OAuth token retrieval and transport invocation.
- Uploader retry now validates persisted video IDs in those terminal-recovery states alongside the media identity checks; invalid values fail before requesting a token or calling transport. The test covers both states and verifies no side effects.
- `python -m unittest tests.test_pi_youtube_private_upload -q`: **26 passed**; `python scripts/run_tests.py`: **917 passed**; compileall and `git diff --check` passed.
- GitHub on code head `57aa8e54a0fe69ff1018c0bc08ea4972eac9c80c`: CI `43242106801`, FFmpeg `43242106656`, Godot `43242106730`, and macOS `43242106880` — **success**.
- Only synthetic transports and tokens were used. No real OAuth, upload, owner device, publication or spending. Rollback before Batch 75K: `d5f267388c6f74fe5b3bacfbbe7766959e463c8b`.

### Batch 75J — Bind uploader recovery to journal media anchors

- Regression reproduced that, after an interrupted resumable upload, changing the private journal's `media_name` while retaining the request fingerprint still allowed retry to continue and call transport.
- Existing-journal validation now requires the persisted media SHA, exact byte count, media name, and episode ID to match the current verified request, in addition to the request fingerprint. Mismatch is rejected before OAuth token retrieval or transport, and the conflicting journal is left untouched for diagnosis.
- `python -m unittest tests.test_pi_youtube_private_upload -v`: **24 passed**; `python scripts/run_tests.py`: **915 passed**; compileall and `git diff --check` passed.
- GitHub on code head `8d33abb13cdbf4b03244ff6635a2dda99580abb5`: CI `43241365265`, macOS `43241364653`, Godot `43241364752`, and FFmpeg `43241364712` — **success**.
- Only synthetic transport/credentials were used. No real OAuth, upload, Pi, owner-device operation, publication or spending. Rollback before Batch 75J: `f65df1eb2c65dd06e7b05ee38c4ec41fb42e290e`.

### Batch 75I — Prove internal candidate stops before Pi uploader side effects

- Added an end-to-end uploader regression for the reserved `verified-candidate.mp4`: even with explicit synthetic authorization and matching digest, execution stops before OAuth token retrieval, transport calls, or journal creation.
- The existing upload gate and dry-run → handoff chain already enforced the block; no uploader production change was required.
- Focused Pi upload/handoff/review/inbox suite: **78 passed**; `python scripts/run_tests.py`: **914 passed**; compileall and `git diff --check` passed.
- GitHub on code head `5fb605658e69f95dd1480e81c61dfbbcaa32dc95`: CI `43220358930`, macOS `43220358984`, Godot `43220359028`, and FFmpeg `43220358999` — **success**.
- No real credential, network call, upload, owner device, or publication was used. Rollback before Batch 75I: `aa191c328ca644a926bfa12eec2567716a744f32`.

### Batch 75H — Qualify reserved candidate blocking in Pi review inbox

- Added an inbox-level regression with a synthetic confirmed journal pointing to `verified-candidate.mp4`. The inbox reports `BLOCKED_LOCAL_EVIDENCE`, omits episode/video identities, does not mark bytes SHA-verified, and never counts it as owner review eligible.
- The existing shared review inspection already provided the block; no production-code change was required.
- `python -m unittest tests.test_pi_private_draft_inbox`: **21 passed**; full suite on the following code head: **914 passed**.
- Runs on test head `aa191c328ca644a926bfa12eec2567716a744f32`: CI `43220090382`, Godot `43220090551`, and FFmpeg `43220090459` — **success**; macOS `43220090533` was **in progress** at last check.
- Rollback before Batch 75H: `c7d9e2d84f4f7167ed9fa0a6fc29b89fc29d1e25`.

### Batch 75G — Block internal mux candidate from Pi upload and review

- Regression first showed an exact `verified-candidate.mp4` could become eligible through the owner-authorized PRIVATE upload gate and the PRIVATE upload handoff. A second regression showed a matching historical journal could make the same internal filename eligible for owner review.
- The upload eligibility gate now blocks the reserved candidate path segment (including Windows separators) before media verification; the shared Pi review inspection rejects the reserved exact filename. The Pi inbox inherits the review rejection through this shared inspection gate. Final episode names remain eligible subject to the existing controls.
- Focused upload-gate, handoff and Pi-review tests: **34 passed**. `python scripts/run_tests.py`: **912 passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- Code head: `6ea4f3f16b1c56736f088c41ccc75c5affdb53a5`. CI `43219330522`, Godot `43219330734`, and FFmpeg `43219330493` — **success**. macOS `43219330562` — **in progress** at handoff preparation; do not infer qualification from it until completed.
- No YouTube/OAuth/network call, upload, Pi deployment, owner-device operation, public release, spending, paid API, or model download was performed. The owner's Arabic episode remains **Pending Physical Qualification**. Rollback before Batch 75G: `f1b035e66eeb19c381cb11f8a25c1f20807c8138`.

### Batch 75F — Exclude internal mux candidates from review history

- Regression proved the generic episode review history accepted `verified-candidate.mp4` as `ACCEPTED_PRIVATE`, allowing the internal staging artifact to appear in the episode's review freshness summary.
- The shared review-receipt builder now rejects the reserved candidate name, including nested and Windows-style paths. This also blocks persistence through `VideoReviewHistory`; publication approval remains false.
- `python -m unittest tests.test_video_review_history tests.test_video_review_receipt tests.test_episode_review_overview tests.test_dashboard_reviews tests.test_reviewed_mac_pi_handoff tests.test_mac_pilot_evidence tests.test_mac_pilot_review_shortcut -v`: **103 passed**; `python scripts/run_tests.py`: **909 passed**; compileall and `git diff --check` passed.
- GitHub on code head `837aed7273a45563c425bfb60be1d414cb165ee5`: CI runs `43215288581` and `43215281657` — **success**; macOS `43215288729` — **success**; Godot `43215288588` — **success**; FFmpeg `43215288908` — **success**.
- Rollback before Batch 75F: `9b69cabe016f0d739e99eaad967465d1d515b22a`. macOS used synthetic audio and the repository suite; owner Mac/Arabic episode qualification remains pending.

### Batch 75E — Keep internal mux candidates out of owner review choices

- Regression showed the Mac review-choice list accepted a manually supplied sidecar for `verified-candidate.mp4`, even though the later Mac→Pi transfer guard rejected that file. The candidate could therefore be selected as an episode before transfer failed.
- Evidence collection and the review-choice validator now both reject the internal mux-candidate name. The transfer guard remains unchanged.
- `python -m unittest tests.test_mac_pilot_evidence tests.test_mac_pilot_review_shortcut tests.test_reviewed_mac_pi_handoff tests.test_mac_to_pi_transfer -v`: **83 passed**; `python scripts/run_tests.py`: **908 passed**; compileall and `git diff --check` passed.
- GitHub on code head `9b69cabe016f0d739e99eaad967465d1d515b22a`: CI runs `43214622547` and `43214613520` — **success**; macOS `43214622685` — **success**; Godot `43214622661` — **success**; FFmpeg `43214622506` — **success**.
- Rollback before Batch 75E: `ba64db7117a8c4161626300654ad9292ea003ca9`. No Mac/Pi, model, API, spending, publication or upload was used.

### Batch 75D — Gate Godot pilot on final AAC energy

- A regression proved the Godot pilot muxed directly to the final episode filename and returned success without decoding/checking the AAC output. A post-mux failure could therefore leave a final-named, unverified episode.
- The Godot path now muxes to `verified-candidate.mp4` in its private render directory, decodes AAC to a private PCM check file, and checks energy against every validated scene beat. It verifies candidate mode, size and digest, then promotes by hard link and fsync without replacing an existing final name.
- Regression covers silent post-mux audio blocking final publication, valid per-beat decoded audio, successful candidate promotion, and a final-name race preserving the existing file. Synthetic AAC decode smoke using local FFmpeg: active two-beat tone **PASS**, silent AAC **REJECTED**.
- `python -m unittest tests.test_mac_episode_pilot -v`: **18 passed**; `python scripts/run_tests.py`: **906 passed**; compileall and `git diff --check` passed.
- GitHub checks on code head `b0a2f3c79e672b46a23856ec2c4c102676615650`: Python CI runs `43208029385` and `43208020687` — **success**; macOS `43208029555` — **success**; Godot `43208029448` — **success**; FFmpeg `43208029361` — **success**.
- Hosted macOS exercised synthetic tones and the repository suite. It does not qualify the owner's Mac, Arabic voice, Godot episode review, or physical production flow. Rollback before Batch 75D: `ce72200af66b21aa05a04bf62d39fbae5cfa41c4`. No model/API, Pi deployment, upload, publication, spending or device change was used.

### Batch 75C — Gate Godot pilot narration against the scene timeline

- Regression first proved that `run_mac_episode_pilot` accepted a fully silent SHA-pinned WAV and proceeded into Godot rendering. The same path could accept a WAV with one silent scene beat.
- Added a reusable PCM energy checker for validated scene beat durations. In execute mode the Godot pilot now checks each segment before rendering; silent or partial-beat silence blocks Godot and mux. Preview mode remains read-only and does not require audible audio.
- The established six-beat colors gate now delegates to the shared timeline checker without changing its report contract. Checks remain signal-energy heuristics; they do not verify speech, language, words, clipping, educational correctness or owner review.
- `python -m unittest tests.test_audio_pcm_energy tests.test_mac_episode_pilot -v`: **25 tests passed**; `python scripts/run_tests.py`: **902 tests passed**; compileall and `git diff --check` passed.
- GitHub on code head `f37fe02281855dfad8de1171ccd176911204ab9b`: CI `43200187015`, macOS `43200187067`, Godot `43200187151`, and FFmpeg/original-colors `43200187217` all **success**. macOS used hosted synthetic tones and did not qualify the owner's device or Arabic voice.
- Rollback before Batch 75C: `34e895fae3249e6414dfeff1f49b407bf8b32b48`. No actual Mac/Pi deployment, model, paid API, upload, publication or spending was used.


### Batch 75B — Block direct transfer of unverified episode candidates

- A regression showed the generic Mac→Pi transfer planner accepted the first-colors pipeline's `verified-candidate.mp4` from its private `*-pilot-sources-<random>` directory when given an explicit path and digest. The reviewed handoff already requires a matching simple final filename and independent review evidence; the lower-level generic transfer API did not distinguish this internal staging artifact.
- The transfer planner now rejects the reserved candidate filename and per-attempt stage path markers, including Windows-style separators, before filesystem verification or SSH. Normal final episode transfer behavior is unchanged. Regression verifies no remote runner is reached.
- `python -m unittest tests.test_mac_to_pi_transfer tests.test_first_colors_episode -v`: **43 tests passed**; `python scripts/run_tests.py`: **899 tests passed**; compileall and `git diff --check` passed.
- GitHub on code head `ef09fb59f21e1ea8026173bb96c26a3524942a4d`: CI `43198600966`, macOS `43198600985`, Godot `43198601203`, and FFmpeg `43198601009` all **success**.
- This only blocks direct use of the internal candidate path/name. It does not authenticate arbitrary files that a person copies or renames; the reviewed Mac→Pi path still requires exact sidecar and owner review assertions. No actual Pi transfer, upload, real model, paid API, spending or publication was performed.
- Rollback before Batch 75B: `1b347f395c5f6fd6e0cc5775c60d723b7bad7b37`.


### Batch 75A — Publish the episode only after final audio verification

- Regression first proved that a failed post-mux AAC energy gate left the muxed file at the final episode filename. That falsely exposed a rejected episode as the output and blocked rerunning the same episode name.
- The mux now writes a candidate inside the current private attempt directory. The pipeline checks final AAC energy, candidate type/size/hash, then atomically hard-links it to the final filename without replacing an existing file. If final audio validation fails, no final-name artifact is published; the private attempt candidate remains for diagnosis. A race that creates the final filename is rejected without overwriting it.
- Updated the hosted macOS synthetic harness to inspect the private candidate and the published final output. Local regression covers rejected candidate isolation, successful promotion and a final-name race.
- `python -m unittest tests.test_first_colors_episode -v`: **28 tests passed**; `python scripts/run_tests.py`: **898 tests passed**; compileall and `git diff --check` passed.
- Local original-colors FFmpeg smoke passed. The native-mode synthetic-tone end-to-end smoke passed with a Darwin platform stub and real FFmpeg; this is not owner hardware or Arabic speech qualification.
- GitHub checks on code head `f785b522089c0bb409c48cb43867cb7165c33554` all succeeded: CI `43195859191`, macOS `43195859202`, Godot `43195859207`, and FFmpeg/original-colors `43195859599`.
- Rollback before Batch 75A: `c0ef2d1c03b43c434122af6242c3610547667ab2`. Real Arabic narration on the owner's Mac remains **Pending Physical Qualification**. No paid API, model, Pi, upload, publication or spending was used.


### Batch 74U — Verify final muxed audio energy for every story beat

- Regression first exposed that the episode pipeline validated six-beat energy in the supplied WAV, but did not gate success on the audio track after FFmpeg muxing. A muxed output with a silent/missing story beat could be reported as successful.
- Added a final-MP4 audio gate: FFmpeg decodes the muxed track into a private per-attempt staging WAV, then the existing six-beat PCM-energy checker validates it. Decode failures, absent audio, or a beat below the energy threshold fail the episode.
- Added focused tests for all beats having energy, one silent decoded beat, and preventing a successful pipeline result when final-audio validation fails. `python -m unittest tests.test_first_colors_episode -v`: **26 tests passed**.
- `python scripts/run_tests.py`: **896 tests passed**; compileall, diff check, and the synthetic native-voice-mode FFmpeg smoke passed locally. The smoke used synthetic tones, not speech.
- On the first code-head run, Python 3.11/3.12/3.13, Godot 4.7.2, and original-colors/FFmpeg succeeded; macOS was initially queued. Follow-up checks on Handoff-only head `c0ef2d1c03b43c434122af6242c3610547667ab2` completed successfully, including macOS run `131100392069`.
- This gate checks signal energy only; it cannot verify speech, words, language, educational correctness, or pronunciation. Real Arabic episode qualification on the owner's Mac remains **Pending Physical Qualification**. No model, paid API, owner device, Pi, publishing, or spending was used.
- Rollback before Batch 74U: `068115fcd25bbc95fbb80769f41fa1e24b8b4318`.


### Batch 74T — Keep hosted macOS smoke aligned with retry staging

- The first CI run after Batch 74S exposed that the macOS synthetic-tone harness still expected a fixed staging directory. The macOS unit suite and other smoke tests passed, but the full native-mode synthetic pipeline failed at that stale path.
- Added a resolver that requires exactly one private per-attempt workspace and fails closed if it is missing, ambiguous, symlinked, or not private. Added success, missing-directory, and ambiguous-directory regression coverage.
- A first integration commit (`fe25db86`) was accidentally built from an older tree and dropped Batch 74S files; the failing CI exposed this. A forward-only recovery commit (`7dcc5daa`) restored Batch 74S and retained the smoke fix. No history was rewritten.
- `python scripts/run_tests.py`: **894 tests passed**; 33 focused tests passed; compileall and `git diff --check` passed. The native-mode smoke also passed locally with a Darwin platform stub and real FFmpeg using synthetic tones only.
- GitHub on `7dcc5daa1aa2714e598282317d0b7939f7851ae2`: Python 3.11/3.12/3.13, macOS, Godot, and original-colors/FFmpeg checks all **success**.
- These checks qualify CI orchestration and synthetic media only; no real Arabic speech, owner Mac, Pi, model, paid API, upload, or publishing was qualified or used.

### Batch 74S — Retry interrupted episode renders in a fresh staging area

- Regression first exposed that a render failure left a fixed-name staging directory; retrying the same episode failed at `mkdir` before a new render could start.
- Each render attempt now creates a fresh owner-private staging directory. Partial artifacts from earlier attempts are preserved for diagnosis, never reused or overwritten. The regression covers a failed render followed by a successful retry and verifies both isolated directories remain private.
- This enables safe retry after a failed local render call; it does not implement persisted render-task resumption across process restarts or prove real Mac narration quality.
- `python -m unittest tests.test_first_colors_episode -v`: **24 tests passed**; `python scripts/run_tests.py`: **893 tests passed**; compileall and `git diff --check` passed.
- Hosted macOS later exposed the stale smoke path described in Batch 74T; the regression was corrected and all checks now pass on the recovered code head.
- No real model, paid API, external research, Pi, OAuth, YouTube, public release, or owner device was used.

### Batch 74R — Gate Director auto-approval on requested writing script

- Regression first exposed that the Director policy accepted an English request whose generated learning objective was Arabic, even though the existing evaluator already had a conservative Arabic/Latin script-dominance heuristic.
- The internal `script_draft` policy now requires the requested script heuristic to pass for the learning objective. A mismatch is deferred before queueing. The test router now honors requested language for normal synthetic cases, with a deliberate mismatch fixture for regression.
- This heuristic distinguishes dominant Arabic versus Latin script only; it does not verify language fluency, educational accuracy, age suitability, or spoken narration. Independent review and owner publication approval remain required.
- `python scripts/run_tests.py`: **892 tests passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- GitHub on code head `92003a625f6fcacd21896541abb64f9b9258796e`: Python 3.11/3.12/3.13 jobs, Godot and FFmpeg/original-colors smoke succeeded; hosted macOS colors smoke and aggregate CI were still **in progress** at handoff update.
- No real model, paid API, external research, Pi, OAuth, YouTube, public release, or owner device was used.

### Batch 74Q — Reject editorial candidates dominated by the wrong script

- Regression first exposed that an English-only script labeled `ar` passed the mechanical evaluator because `language` was only checked as an allowed enum. The same gap existed in the local artifact evaluation path.
- Added a conservative Unicode script-dominance check for Arabic versus Latin text and wired it into the existing evaluator used by the editorial artifact adapter. Positive Arabic/English samples and opposite-script rejection are covered.
- This is a script heuristic only; it does not identify language reliably, check grammar, verify educational facts, or establish child suitability. Mechanical passes still require independent editorial review and never authorize publication.
- `python scripts/run_tests.py`: **891 tests passed**; `python -m compileall -q kidsstudio tests scripts` and `git diff --check` passed.
- GitHub on code head `bb9c0fb6ac68010ba28581e3e9bc88ef5fee6707`: CI `43176608496`, macOS `43176608476`, Godot `43176608555`, and FFmpeg/colors `43176608475` all **success**.
- No real model, paid API, external research, Pi, OAuth, YouTube, public release, or owner device was used.

### Batch 74P — Match storyboard timing to the rendered colors pilot

- Regression first exposed that `colors_ar_01_pilot_cues.json` and the renderer used the same six Arabic lines but different timings: 12 seconds with two-second beats in the storyboard versus 24 seconds with four-second beats in the current pilot.
- Updated the draft storyboard and pilot instructions to six four-second beats (24 seconds), matching the current renderer and WAV contract. Added a regression that checks episode ID, narration order, total duration, and contiguous beat boundaries so the manifest cannot silently drift from the renderer.
- `python scripts/run_tests.py`: **889 tests passed**; `python -m compileall -q kidsstudio tests scripts`, JSON parsing, `git diff --check`, and the real FFmpeg synthetic-tone episode smoke passed.
- GitHub on code head `4270c21dce045135996c6981e7c102c19e4c0ef9`: CI `43172239739`, macOS `43172239761`, Godot `43172239714`, and FFmpeg/colors `43172239683` all **success**.
- Timing agreement is a technical integration check; it does not establish educational appropriateness, speech quality, Arabic pronunciation, or owner approval. The real Arabic episode on the owner's Mac remains **Pending Physical Qualification**.
- No real model, paid API, external research, Pi, OAuth, YouTube, public release, or owner device was used.

### Batch 74O — Reject silent supplied narration before episode render

- Regression first exposed that execute mode accepted a fully silent, otherwise valid 24-second supplied WAV and proceeded to render visuals. Its hash and duration bound bytes and length, not audio presence.
- Execute mode now applies the existing per-beat PCM energy gate to the verified supplied WAV before image/video rendering. The gate detects only minimum signal energy; it does not verify words, Arabic pronunciation, speech quality, or owner approval. Preview mode remains non-mutating and does not require audible media.
- Added positive and failure coverage for supplied audio; the silent fixture is rejected before render/mux, while a synthetic tone passes the presence gate without being described as speech.
- Updated the real FFmpeg smoke fixture from silence to a synthetic tone so the integrated execution path can pass the gate. The macOS job label now accurately identifies the tone fixture.
- `python scripts/run_tests.py`: **888 tests passed**; `python -m compileall -q kidsstudio tests scripts`, `git diff --check`, and `PYTHONPATH=. python scripts/ci_colors_episode_smoke.py` passed.
- GitHub on code head `a3e945200869ee799b93383f654615947331623a`: CI `43170954014`, macOS `43170954041`, Godot `43170953927`, and FFmpeg/colors `43170953990` all **success**. Hosted macOS and the tone fixture do not qualify real Arabic narration or the owner's Mac.
- No real model, paid API, external research, Pi, OAuth, YouTube, public release, or owner device was used.

### Batch 74N — Correlate terminal queue events with Director result retries

- Extended interruption/recovery coverage for COMPLETED, FAILED, and CANCELLED to assert each terminal queue state has exactly one matching terminal event before Director records its result.
- The event stream remains unchanged after Director rollback, result recovery, and idempotent retry. This confirms supported queue transitions persist state and event together; Director does not duplicate queue events.
- No production-code change was justified: supported queue APIs did not produce a state/event mismatch. Direct database edits remain outside the supported path and separate-database atomicity guarantee.
- `python scripts/run_tests.py`: **886 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74M — Keep queue events stable across Director result retries

- Extended the COMPLETED/FAILED/CANCELLED pre-commit interruption regression to snapshot queue events before Director result recording.
- After Director rollback, recovery, and an idempotent retry, the queue event stream remains byte-for-byte equivalent at the decoded record level; no event is duplicated or rewritten by Director.
- Queue state transitions and their events are committed together in the queue database. Director result persistence remains a separate ledger transaction; no cross-database atomicity is claimed.
- `python scripts/run_tests.py`: **886 tests passed**; compileall and `git diff --check` passed.
- No production-code change was needed. No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74L — Verify lease reaping preserves terminal queue results

- Added a queue regression covering COMPLETED, FAILED, and CANCELLED jobs while a later claim runs the expired-lease reaper.
- The claim returns no queued job; all three terminal states, result/error material, and event histories remain unchanged.
- The production reaper already limits updates to `state='LEASED'`; no production-code change was justified.
- `python scripts/run_tests.py`: **886 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74K — Audit supported terminal queue writers

- Audited every production `UPDATE jobs` path. State-changing terminal transitions are guarded by a live `LEASED` generation, expiry reaping only changes expired `LEASED` jobs, and cancellation rejects `COMPLETED`/`FAILED` while repeated `CANCELLED` is idempotent.
- Added a deterministic test that attempts a state change after Director's confirming queue read for COMPLETED, FAILED, and CANCELLED. Supported APIs prevent mutation or preserve the same terminal state; Director records the confirmed outcome.
- No additional production-code change was justified. Direct edits to the queue SQLite file remain outside the supported API and cannot be made atomic with the separate Director database.
- `python scripts/run_tests.py`: **885 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74J — Qualify terminal-state immutability after queue confirmation

- Added a regression that attempts a late cancellation after confirming COMPLETED, a late worker failure after FAILED, and a repeated cancellation after CANCELLED.
- The supported queue API rejects state-changing operations for terminal jobs; repeated CANCELLED is idempotent. Director records the confirmed result for each state.
- Tests passed against the current implementation; no additional production-code change was warranted.
- This does not protect against an external process editing the queue SQLite file directly after the confirmation read. Queue and Director remain separate databases, with no shared atomic transaction claim.
- `python scripts/run_tests.py`: **885 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74I — Reject stale queue result snapshots

- Regressions simulated a queue state or result material changing after the first queue read but before Director persistence; the old code recorded the stale result.
- Result recording now reads the queue job again and compares identity, terminal state, result code, and digest before returning or writing the ledger result. If the snapshots differ, it fails closed; retry after the state settles can recover.
- Added coverage for state and content changes, no partial Director result on conflict, and successful retry using the settled queue state. Existing Director rollback and post-commit recovery tests remain passing.
- Queue and Director use separate SQLite databases: this is a consistency recheck, not a cross-database atomic transaction or a guarantee against a queue change after the confirming read.
- `python scripts/run_tests.py`: **884 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74H — Recheck dispatch before returning a saved result

- A regression exposed a stale-snapshot gap: when a terminal result already existed, retry matched it against the dispatch read before queue lookup and returned `RESULT_EXISTS` without checking whether dispatch had changed meanwhile.
- Saved-result retry now re-reads dispatch and result inside a transaction before returning success. A changed dispatch is rejected; an unchanged result remains idempotent.
- Added regression coverage for a dispatch relink between snapshot reads, relink before first write with rollback/recovery, and interruption after a saved-result check. Existing pre-commit interruption coverage remains in place.
- `python scripts/run_tests.py`: **883 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74G — Validate queue identity during result retry

- Regression tests confirmed queue and ledger read failures propagate without changing the saved terminal result.
- A retry previously accepted a terminal queue row whose returned `job_id` differed from the dispatch identity when state and result material still matched.
- Result recording now rejects that mismatch before comparing or returning a saved result.
- `python scripts/run_tests.py`: **881 tests passed**; compileall and `git diff --check` passed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74F — Terminal queue result survives pre-commit interruption

- Added a regression that makes Director result persistence fail before its database transaction commits while the queue job is already terminal.
- Covered COMPLETED, FAILED, and CANCELLED jobs. The Director transaction rolls back cleanly, and retry reads the still-terminal queue job and records exactly one result.
- Tests passed against the existing implementation; no production-code change was needed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74E — FAILED/CANCELLED result retry qualification

- Added normal and post-commit interruption/recovery coverage for FAILED and CANCELLED queue jobs.
- Added deterministic concurrent retry coverage for both terminal states and verified one recorded result with one retry response.
- Added conflicting terminal-state retries for both modes; changed state/error material is rejected.
- Tests passed against the existing implementation; no production-code change was needed.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74D — Concurrent result-record retry safety

- A deterministic two-thread regression made both calls read the missing result before either wrote it; the second writer previously failed with a SQLite unique-constraint error.
- The write transaction now rechecks the dispatch identity and any result row before inserting. A concurrent retry with the same decision, job, terminal state, status, and digest returns `RESULT_EXISTS`; identity or content conflicts remain rejected.
- Concurrent success, post-commit recovery, relinked dispatch conflicts, and changed-result conflicts all pass.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74C — Dispatch identity and terminal result consistency

- Regression tests exposed that result retry compared only terminal state and content digest, allowing a relinked dispatch to a different queue job or decision to return `RESULT_EXISTS`.
- Result retry now also requires the stored decision ID, queue job ID, result state, result status, and result digest to match the current dispatch and queue result.
- Added positive and failure coverage for queue-job relinking, decision relinking, changed terminal material, and post-commit retry. All passed.
- No paid API, real model, external research, owner hardware, spending, or publishing was used.

### Batch 74B — Successor idempotency and result conflict regressions

- Added a regression proving a bound successor request key cannot be replayed with a different `supersedes_id`; the second attempt is rejected before another model/reviewer call and cannot create a second queue job.
- Added a regression proving a retry rejects changed terminal result material after an earlier result was recorded.
- Both regression tests pass against the current implementation; no production-code fix was needed.
- Normal queueing, result recording, post-commit interruption/resume, nonterminal rejection, and conflicting retry paths remain covered.
- No model/API, external research, owner hardware, spending, or publishing action was used.

### Batch 74A — Safe legacy proposal recovery and result resumption

- A legacy proposal without atomic request/provenance binding remains ineligible for automatic acceptance, even if an old review row says PASS.
- Reusing a legacy proposal's request key is rejected before any model call. A caller can create a separate successor proposal linked to the old proposal ID; the old proposal and decision remain immutable.
- The successor link is included in the request digest and is audit metadata only. Prior proposal evidence/provenance is not passed to the proposer or treated as validated.
- Added terminal result-record interruption coverage: if the process stops after the result transaction commits, retry returns the existing result without duplication. Unlinked and nonterminal jobs are rejected.
- No production model, paid API, external research, owner Mac/Pi, or publishing action was used.

## Verification

- Local `python scripts/run_tests.py`: **931 tests passed** on Batch 76F code/test head `5e3a6c3bd9f18ad3abee94519454ff77195d2f98`.
- `tests.test_studio_director`: **51 passed** on Batch 76F.
- `python -m compileall -q kidsstudio tests scripts`: passed on Batch 76F.
- `git diff --check`: passed.
- Batch 76F GitHub CI `43307200667`, macOS `43307200704`, Godot `43307200691`, and FFmpeg `43307200636` completed successfully on test head `5e3a6c3bd9f18ad3abee94519454ff77195d2f98`.
- Batch 76E GitHub CI `43305631424`, macOS `43305631132`, Godot `43305631050`, and FFmpeg `43305631252` completed successfully on test head `6ce37d6da9312ef06f8c761c0f24c259e143e353`.
- Batch 76D GitHub CI `43303870074`, macOS `43303870067`, Godot `43303870076`, and FFmpeg `43303870421` completed successfully on test head `69cf55df39f6734c7e4759ea0562a46f789b3f05`.
- Batch 76C GitHub CI `43296012922`, macOS `43296013332`, Godot `43296012900`, and FFmpeg `43296012854` completed successfully on code head `257ac5851e80f2cb3a60eead0c9fd396d64de7e2`. Batch 76B runs `43294426534`, `43294426331`, `43294426311`, and `43294426299` also completed successfully after the prior Handoff update.
- GitHub checks on Batch 74N head `269aaeb23943375621d58142150fab623afe1322` all completed successfully:
  - CI run `43164779987` — success.
  - macOS run `43164779979` — success.
  - Godot run `43164779986` — success.
  - FFmpeg run `43164779963` — success.
- GitHub checks on Batch 74M head `93a689693934fa7d2448b802f5746be625a38a24` all completed successfully:
  - CI run `43160166238` — success.
  - macOS run `43160166268` — success.
  - Godot run `43160166306` — success.
  - FFmpeg run `43160166149` — success.
- GitHub checks on Batch 74L head `8d1e3649f238a6e31e4e48be3bcabb447dd757cb` all completed successfully:
  - CI run `43159012585` — success.
  - macOS run `43159012460` — success.
  - Godot run `43159012424` — success.
  - FFmpeg run `43159012578` — success.
- GitHub checks on Batch 74J head `1ae29f751ab9bcc4030373f95c89076398a292e0` all completed successfully:
  - CI run `43157639122` — success.
  - macOS run `43157639181` — success.
  - Godot run `43157639228` — success.
  - FFmpeg run `43157639132` — success.
- Batch 74I production code checks on `bf57d0d066bf09be98813903677512ad49d2e828` all completed successfully:
  - CI run `43156652772` — success.
  - macOS run `43156652889` — success.
  - Godot run `43156652908` — success.
  - FFmpeg run `43156652884` — success.
- GitHub checks on Batch 74I code head `bf57d0d066bf09be98813903677512ad49d2e828` all completed successfully:
  - CI run `43156652772` — success.
  - macOS run `43156652889` — success.
  - Godot run `43156652908` — success.
  - FFmpeg run `43156652884` — success.
- GitHub checks on Batch 74H code head `1d889bb7a2e5c28400d40f252dc0ece62aee0661` all completed successfully:
  - CI run `43154506534` — success.
  - macOS run `43154506625` — success.
  - Godot run `43154506773` — success.
  - FFmpeg run `43154506554` — success.
- GitHub checks on Batch 74G code head `f887161cee84ff69e009d7de1e84919c46d11558` all completed successfully:
  - CI run `43152691120` — success.
  - macOS run `43152691100` — success.
  - Godot run `43152691130` — success.
  - FFmpeg run `43152691107` — success.
- GitHub checks on base head `56e488b86b3add00ee9746700642d4841cc042a9` all passed:
  - CI run `43082246409`.
  - macOS run `43082246373`.
  - Godot run `43082246432`.
  - FFmpeg run `43082246280`.
- GitHub checks on code head `3c8bb098381957c02889a612cdb8987836659321` all completed successfully:
  - CI run `43084519378` — success.
  - macOS run `43084519277` — success.
  - Godot run `43084519266` — success.
  - FFmpeg run `43084519667` — success.
- The macOS run used synthetic audio. It does not qualify the owner's Arabic episode workflow or prove a real AI model works.
- Synthetic router tests are test doubles only. No real model was invoked.
- GitHub checks on regression head `53b202f1da88bc22de9dcdebc786bd626ec86c87` all completed successfully:
  - CI run `43086298662` — success.
  - macOS run `43086298598` — success.
  - Godot run `43086298711` — success.
  - FFmpeg run `43086298646` — success.
- GitHub checks on code head `28348b6479b8c500da3947e1a3fcc5ca1d7be1bd` all completed successfully:
  - CI run `43088223782` — success.
  - macOS run `43088223863` — success.
  - Godot run `43088223822` — success.
  - FFmpeg run `43088223699` — success.
- GitHub checks on code head `88e8ad5a0d4b26fd98822ecc0ddc9511c2d39a1f` all completed successfully:
  - CI run `43089956893` — success.
  - macOS run `43089956975` — success.
  - Godot run `43089956952` — success.
  - FFmpeg run `43089957106` — success.
- GitHub checks on regression head `aae29b153e41e4e14fd2063f82d66c8b8a19e17e` all completed successfully:
  - CI run `43093351718` — success.
  - macOS run `43093351499` — success.
  - Godot run `43093351376` — success.
  - FFmpeg run `43093351356` — success.
- GitHub checks on regression head `3cb4b849b6ebf88afbcdccf3277649e2c581a9c7` all completed successfully:
  - CI run `43094732538` — success.
  - macOS run `43094732062` — success.
  - Godot run `43094732486` — success.
  - FFmpeg run `43094732160` — success.

## Existing system and boundaries

- Studio Director uses the existing ChatRouter, proposal ledger, policy decision records and Studio Queue; no parallel agent or queue system was added.
- Internal automatic approval remains limited to the existing zero-paid, independently reviewed, bounded `script_draft` policy. Owner publication approval and commercial decisions remain separate.
- Hashes bind bytes/records for consistency; they do not establish source authenticity or factual correctness.
- The Arabic episode on the owner's Mac is **Pending Physical Qualification**. No actual Arabic narration/render/listening qualification is claimed.
- Real Mac/Pi transfer, PRIVATE YouTube upload, owner review, and backup/restore qualification remain pending physical/owner-gated work.

## Open work and priorities

1. Verify the live branch head, PR #33, and CI before every batch.
2. Continue P3 with explicit research evidence provenance and a source-bound production handoff. Research remains caller-supplied and unverified; do not introduce external calls or child-level data. Production stays gated on the exact reviewed artifact and owner-controlled decisions.
3. Keep post-draft editorial review explicitly unverified; do not treat completion as a PASS, owner approval, production authorization or public-publishing decision.
4. Keep owner Mac/Pi/PRIVATE transfer and upload qualification pending for supervised operation; do not replace these requirements with synthetic checks.

## First action next session

Read this handoff, fetch the live branch head and PR #33 state, and verify Batch 76F's latest checks. Update the stale PR description to match the verified branch head, then continue source-bound production integration only within existing Queue and owner gates. Keep research evidence caller-supplied and unverified. Hashes bind stored bytes only; do not promote sources based on their digest or label. Keep actual owner-Mac Arabic narration/render/listening Pending Physical Qualification. No child-level data; do not claim atomicity across separate databases.

## Required limits

- Stay on the existing branch and PR. No new branches/PRs, merge to `main`, force push, or history rewrite.
- No paid API, large model download, public publishing, spending, real Mac/Pi deployment, or device modification without owner authorization.
- Keep owner approval for public publishing and binding commercial decisions. Do not collect children's personal data.
- Do not claim a real model, external research, or hardware qualification from synthetic tests or hashes.
