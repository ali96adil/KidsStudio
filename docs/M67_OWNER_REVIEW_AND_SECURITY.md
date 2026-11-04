# M67.25 — Owner review and security hardening

## New owner feedback workflow

After the Pi uploader has uploaded a video as PRIVATE and returned its
real YouTube video ID, the owner can record a local review decision:

```sh
python3 -m kidsstudio.m67_owner_review_notes \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --episode-id colors-ar-001 \
  --video-id REPLACEWITHREALID \
  --decision REQUEST_CHANGES \
  --notes "At 00:28 the red object is difficult to recognize"
```

The tool creates `owner_reviews/review_0001.json`, then `0002`, etc.
It never edits an earlier review, calls YouTube, or changes visibility.
The review ID must be a real 11-character YouTube ID, not the example
placeholder. Decisions: ACCEPT_PRIVATE, ACCEPT_WITH_NOTES,
REQUEST_CHANGES, REJECT. Even ACCEPT_PRIVATE is only a note, not
authorization for public release.

## Handoff security changes

- Pi deployment audit blocks missing, unreadable, and ambiguous upload
  journals rather than interpreting them as ready.
- Receipt preflight checks regular files with a single hard link.
- Pi import rehashes the copied master and removes files created by a
  failed copy, while leaving existing staged files untouched.
- Mac inventory blocks symlinked master paths and symlinked directories.
- SSH transfer rejects dot/dot-dot directory traversal.

## Acceptance limits

CI results and real Mac/Pi hardware acceptance remain separate. This
work does not claim a successfully produced 75-second episode or a
completed YouTube upload. A passing offline test only establishes the
corresponding software contract.

## Follow-up before production

Run the full Python test suite, check real Pi M65 acceptance with
approved episode provenance, and verify that YouTube private review
decisions appear in the owner dashboard. The new feedback recorder is
a local append-only data source; dashboard integration is not yet done.
