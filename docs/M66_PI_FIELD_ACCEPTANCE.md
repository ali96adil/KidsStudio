# M66 — Mac → Pi field acceptance (operator runbook)

**Status:** FIELD TEST REQUIRED. Passing CI does not prove the physical
Mac/Pi network, YouTube OAuth, or persistent storage. This checklist does
not authorize public publication.

## Safety rules

- Mac produces the final approved MP4 and transfers it over LAN/SSH.
- Pi independently checks the received bytes and owns Google OAuth and
  the PRIVATE upload journal. Never copy Google credentials to Mac.
- Do not use a real YouTube upload as a dry run. A `videos.insert` call
  may create an irreversible remote side effect even if interrupted.
- Never delete an ambiguous `STARTED` journal row to retry.
- All YouTube uploads must remain PRIVATE. Owner review is required before
  any later public release.

## 1. Verify code and environment on both machines

Use the same reviewed commit on Mac and Pi. Record `git rev-parse HEAD`,
OS version, free disk, Pi service account and local time in the acceptance
log. Do not paste private keys or OAuth tokens into the log.

Run offline automated tests on the Pi from the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_m66_*.py'
```

A passing suite is necessary, not sufficient.

## 2. Transfer and hash acceptance

Use the existing M64 transfer entry point and its documented dedicated
SSH key. Confirm that the Mac output says
`M64_MAC_LAN_TRANSFER_SENT_PI_SHA_NOT_YET_CONFIRMED`: this is **not**
a Pi acceptance or upload success.

On the Pi, after the existing Pi inbox accept process has promoted the
received file to its final immutable MP4 path, run:

```bash
python3 -m kidsstudio.m66_master_check \
  --mp4 /ABSOLUTE/PI/PATH/episode_qa_master.mp4 \
  --expected-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Alternatively, use the unified offline check (still **not** YouTube
upload authorization):

```bash
python3 -m kidsstudio.m66_offline_acceptance \
  --mp4 /ABSOLUTE/PI/PATH/episode_qa_master.mp4 \
  --expected-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Once the journal contains an actual reservation, the same command also
accepts `--journal /ABSOLUTE/PI/PATH/upload.sqlite --job JOB_ID`.
A reservation does not exist before the first upload attempt. This command
only verifies local bytes and optional journal state; it does not validate
Pi inbox policy, contact YouTube, or prove field readiness.

Replace the example digest with the approved Mac-side SHA256. Record the
returned `actual_sha256`, `size_bytes`, and exit code. Exit 0 and
`pass=true` are required. Repeat with an intentionally altered *test*
copy; it must exit 2. Do not corrupt the real accepted master.

If the upload journal already has an entry for the same render job, also
cross-check the **reserved** master SHA:

```bash
python3 -m kidsstudio.m66_reserved_master_check \
  --journal /ABSOLUTE/PI/PATH/upload.sqlite \
  --job 0123456789abcdef0123456789abcdef \
  --mp4 /ABSOLUTE/PI/PATH/episode_qa_master.mp4
```

The reserved check cannot replace the initial inbox acceptance: before
first upload, a journal entry may not yet exist.

## 3. Durable journal and reboot

Run the read-only report before reboot:

```bash
python3 -m kidsstudio.m66_journal_report \
  --journal /ABSOLUTE/PI/PATH/upload.sqlite > /tmp/m66-before.json
```

Reboot Pi, verify persistent storage is mounted, and run the report again
to `/tmp/m66-after.json`. Compare:

```bash
python3 -m kidsstudio.m66_reboot_compare \
  --before /tmp/m66-before.json --after /tmp/m66-after.json
```

Do **not** start an uploader during this snapshot comparison. Any
`STARTED` or `UPLOADED_UNVERIFIED` entry requires manual reconciliation,
not automatic re-upload.

## 4. Mac-off / Pi-only upload

Only after a human has checked OAuth scopes, channel identity, and
PRIVATE-only behavior, authorize a **single** real test upload using the
existing Pi service procedure. Disconnect or shut down Mac after the
file has been independently accepted on Pi. Record: Pi uploader logs,
YouTube video ID, privacy verification through authenticated YouTube API,
processing status, owner-visible PRIVATE draft, and restart behavior.

If the upload outcome is uncertain, stop. Do not reset journal state and
do not trigger another insert.

## 5. Acceptance record

- [ ] Mac and Pi commit SHAs recorded and identical
- [ ] M66 offline tests passed on Pi
- [ ] Approved master SHA matches Pi final MP4
- [ ] Corrupted test copy rejected
- [ ] Journal survives reboot without state drift
- [ ] Single Pi uploader lock prevents parallel instances
- [ ] Mac powered off; Pi-only authenticated PRIVATE upload verified
- [ ] Owner can inspect the PRIVATE video
- [ ] No public release occurred

Until every applicable item is evidenced, M66 is **not field-qualified**.
