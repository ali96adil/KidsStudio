# One-shot editorial evaluation — operator procedure

This tool is **disabled unless explicitly invoked**. It does not change queue state, create tasks, contact providers, upload content, or approve publication.

Run from a trusted local Mac/Pi environment with a previously created **private** worker artifact:

```bash
python -m kidsstudio.editorial_eval_adapter \
  --artifact-root /private/kidsstudio/artifacts \
  --manifest /private/kidsstudio/artifacts/JOB_ID/attempt_001/result.json \
  --sha256 EXPECTED_SHA256_FROM_QUEUE_PROVENANCE \
  --language ar \
  --required-term "الأحمر"
```

The expected SHA256 must come from the existing trusted queue completion/provenance record, not from a potentially tampered answer file. The command verifies both the manifest and the answer bytes.

Exit status: `0` means **mechanical checks passed but editorial review is still required**; `1` means revise; `2` means an evaluation error. Output is metadata JSON only. No private script content is printed. Never treat exit status 0 as permission to publish.

To roll back, stop invoking this command. Existing workers, queue tables, and manifests remain unchanged. No migration or cleanup is required.

Qualification: GitHub CI covers synthetic files; private Mac/Pi artifact evaluation requires supervised local validation before any worker integration.