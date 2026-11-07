# OmniRoute — optional KidsStudio text-agent gateway (pilot)

**Status:** integrated as an **opt-in, configuration-only** adapter. Neither OmniRoute nor its model backends have been installed, contacted, or measured on the actual Mac. This commit does not change the queue, running worker, Godot, ComfyUI, Pi transfer, YouTube uploader, or public publication controls.

Upstream: https://github.com/cheaper-inference/OmniRoute

## Why this is small

KidsStudio already uses `AIConfig` + `ChatRouter` in `kidsstudio/ai_router.py`, targeting an explicitly configured `/v1/chat/completions` endpoint. OmniRoute supports that interface at `http://127.0.0.1:20128/v1`. Our adapter **only creates an `AIConfig` v1 profile** for that loopback endpoint. The existing local AI worker consumes the profile unchanged.

## Hard limits for this first pilot

- **Only text-agent roles**: `script_draft` and, if a separate reviewer is configured, `editorial_review`. The video, vision, audio, Pi and uploading pipelines are unaffected.
- **No requests from the profile builder.** Offline preview is the default. An explicit `--write-private-config` creates a new 0600 JSON file in an existing 0700 owner-controlled directory outside Git. No overwrites.
- **No actual API key in config, Git, arguments or diagnostics.** The worker resolves `KIDS_OMNIROUTE_KEY` from its environment when a separate live job is explicitly executed.
- **No `auto`, `auto/offline`, combo, silent fallback, or model discovery.** Each role pins a named provider/model string. This avoids uncontrolled client-side routing; however **OmniRoute's own server-side policies must still be inspected and locked**. A pinned model string is *not cryptographic proof* that content stayed on the Mac or that reviewer backends are independent.
- **Two reviewer safeguards:** the profile requires different provider *prefixes* for drafting vs reviewing. This is necessary but not sufficient for independent underlying models. Review remains unverified and cannot approve publication.
- **Local-model defaults:** known local prefixes (`ollama`, `lmstudio`, `llamacpp`, `mlx-qwen`, `mlx-gemma`, `vllm`, etc.) are marked `billing: free` (zero external API charges expected, excluding local electricity/hardware). These labels do not verify where OmniRoute sends traffic.
- **External model prefixes:** require explicit `--allow-external-profile` when creating the config. They are conservatively marked **`billing: paid`** even if advertised as free-tier. The existing worker blocks such routes unless separately started with `--allow-paid`. No actual dollar spending cap is implemented; output-token cap (1–1200) is **not** a substitute for a provider budget limit.
- **No production, upload, or publishing authority** is added. Owner public-release approval remains separate and mandatory.

## Local Mac preparation — NOT executed by this repo change

1. Inspect and install an appropriate pinned version of OmniRoute on the Mac, following the upstream documentation. Keep it bound to `127.0.0.1:20128`, not `0.0.0.0`. Enable a key in OmniRoute Dashboard → Endpoints; configure the actual local Ollama / LM Studio model providers and disallow cloud fallbacks.
2. Confirm from OmniRoute's local model catalog what explicit `provider/model` names are actually available. **The examples below are placeholders**, not assertions that the models are installed.
3. Preview without writing anything or making a request:

```bash
python -m kidsstudio.omniroute_profile \
  --draft-model "ollama/REPLACE_WITH_LOCAL_MODEL" \
  --review-model "lmstudio/REPLACE_WITH_SEPARATE_LOCAL_MODEL"
```

4. Prepare a private destination; explicitly write the profile:

```bash
umask 077
mkdir -p "$HOME/kidsstudio-private/config"
chmod 700 "$HOME/kidsstudio-private/config"
python -m kidsstudio.omniroute_profile \
  --draft-model "ollama/REPLACE_WITH_LOCAL_MODEL" \
  --review-model "lmstudio/REPLACE_WITH_SEPARATE_LOCAL_MODEL" \
  --max-output-tokens 800 \
  --write-private-config "$HOME/kidsstudio-private/config/omniroute.json"
```

No key values are embedded in that file. The script refuses to overwrite it; to change models, generate a **new versioned filename** and review it before use.

5. **Separate, supervised live test only after reviewing gateway configuration, credentials, current scripts and private queue backup:** load the OmniRoute endpoint key into the environment using a secrets manager or interactive shell prompt (not the command line or Git). Then, with an explicitly queued *synthetic* text draft and no private child imagery, run the existing one-shot worker:

```bash
python -m kidsstudio.local_worker \
  --db "$HOME/kidsstudio-private/state.sqlite" \
  --providers "$HOME/kidsstudio-private/config/omniroute.json" \
  --output-root "$HOME/kidsstudio-private/artifacts" \
  --worker-id mac-omniroute-pilot --once
```

This last command **does** process one real queued text job; it has **not** been run by this integration. Keep `--allow-paid` absent for local-only pilots. An actual running OmniRoute instance, eligible local provider and API key are needed for success.

## Optional external-provider evaluation (later, owner-controlled)

A profile can reference a specific explicit external model such as `groq/EXAMPLE_MODEL` **only** with `--allow-external-profile`. Even when such a route is marked as "free tier" upstream, the config labels it paid and the worker requires a *second* explicit `--allow-paid` switch. Do not use real unpublished children's scripts, private artwork or credentials in an external trial. Do not enable `auto` or server-side paid failover until per-provider limits, data retention, terms, actual costs and billing controls have been verified.

In a controlled trial, evaluate the same **synthetic** Arabic/English fixtures across two explicitly selected models. Record exact model, provider ID, input/output tokens (if returned by an independently verified source), elapsed time, quality notes, any cloud transfer, and actual billed cost. A lower list price or a huge claimed free-tier aggregate alone does not establish savings. Avoid compression for Arabic educational dialogue unless output is reviewed for omissions or distorted meaning.

## Verification already covered by CI mocks

`tests/test_omniroute_profile.py` checks preview-only mode, private config creation, permissions, refusal to overwrite or save inside Git, prohibition of auto/combos, missing opt-in for external models, fail-closed paid route without worker paid opt-in, deterministic exact-model request payloads and a fake two-agent worker workflow.

**These tests contain no live OmniRoute call or paid API usage.** Local-only routing, data residency, provider identity and production quality still require physical supervised verification.
