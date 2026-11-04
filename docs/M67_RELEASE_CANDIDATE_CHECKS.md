# M67 release candidate: run locally before Pi upload

The repository contains a read-only syntax audit for all M67 Python
modules and their tests. It does not require ComfyUI or YouTube credentials.

```sh
python3 -m kidsstudio.m67_source_audit --repository .
python3 -m unittest discover -s tests -p 'test_m67_*.py'
python3 -m kidsstudio.m67_offline_handoff_lab
```

Then run the existing Godot smoke and real FFmpeg decode workflows.
Record their exit codes and exact Git commit SHA.

Do not merge or label the release production-ready if any test fails.
A static syntax audit is not equivalent to executing all imports, media
pipelines, M65 approval checks, or private YouTube upload.

Before hardware acceptance, inspect Pi storage, SSH credentials, M65
owner policy, upload journal, and the original M8 readiness report.
The Mac may be shut down after a verified Pi transfer only when the Pi
has a durable copy and can independently complete the PRIVATE upload.
