# Offline Mac -> Pi integration test

`tests/test_mac_pi_end_to_end_handoff.py` exercises the full transfer contract without external services:

1. Build a manifest from a rendered MP4.
2. Simulate rsync copying the video and then the matching manifest into Pi staging.
3. Run the Pi staging watcher and validate SHA-256.
4. Create a mocked private YouTube resumable session.
5. Verify exactly one queue job and that its persisted session points to identical video bytes.
6. Corrupt a staged video and confirm no upload session or queue job is created.

Run with `python -m unittest tests.test_mac_pi_end_to_end_handoff` from the repository root (or the repository's existing test runner).

**Scope:** tests use a mocked SSH transfer and a mocked YouTube session. They do not establish that a real Raspberry Pi, OAuth token, LAN connection, YouTube upload or owner review is working. Public publishing is never performed.
