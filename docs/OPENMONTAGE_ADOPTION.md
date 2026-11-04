# OpenMontage → KidsStudio adoption audit (2026-11-04)

Upstream: https://github.com/calesthio/OpenMontage
License: AGPL-3.0. Reference: upstream AGENT_GUIDE.md and docs/PROVIDERS.md.
This is an original implementation of the *architectural ideas*, not a copy
or vendoring of upstream source. Reassess licensing with counsel before
importing any upstream code, skills, templates, or modifying/distributing it.

## What was verified in upstream

- Manifest-first pipelines, stage director instructions and tool-specific
  skills. Preflight discovers available tools; agents operate each stage.
- Provider routing distinguishes free/local and paid tools. Paid API calls
  require entitlement and may incur cost; resumable jobs avoid double billing.
- Upstream includes reference-video analysis and a separate review workflow.
- Upstream advertises 12 pipelines, 100+ tools, 700+ agent skill/knowledge
  files; these counts are upstream claims, not installed KidsStudio features.

## Adoption priorities

1. **Implemented in this branch:** original `openmontage_pipeline_bridge.py`
   with three KidsStudio-specific pipeline plans, stage gates, offline
   capability reporting, and read-only MCP tool `kidsstudio_plan_episode`.
2. **Next:** source-of-truth per-series curriculum and episode continuity;
   agent handoffs with resumable stage checkpoints; cost and resource ledger.
3. **Next:** capability-aware provider registry for Godot, ComfyUI, FFmpeg,
   local TTS; no automatic paid fallback.
4. **Next:** reference-video analysis for pacing/structure only, with
   originality and rights checks; no scene or character copying.
5. **Next:** dashboard stage timeline and owner notes integrated with
   existing Mac→Pi→private YouTube handoff.
6. **Later, after hardware acceptance:** explicitly permissioned production
   execution tools, local only; never grant agents public YouTube release.

## Explicit non-goals

Do not vendor 700+ upstream skills indiscriminately; do not replace
KidsStudio's Pi upload queue, human owner approval, or bilingual child
safety gates. Do not automatically install untrusted dependencies, run
upstream scripts, send content to paid services, or expose credentials.

## Test

`python3 -m unittest tests.test_openmontage_pipeline_bridge -v`

This milestone plans stages but does not execute any. CI is a mocked/offline
verification; Mac, Pi and YouTube hardware tests are separate.
