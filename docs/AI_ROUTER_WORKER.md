# KidsStudio Multi-Provider AI Chat & Local Worker — M2

This stage supports users who already have multiple **AI Chat APIs**. It
provides deterministic *role routing* rather than a single-provider lock-in.

## Supported protocol

First implementation: OpenAI-compatible `POST /v1/chat/completions`,
response `choices[0].message.content`. May be used against local
OpenAI-compatible servers or explicitly configured remote HTTPS providers.
Providers whose APIs differ (e.g. native Anthropic Messages, native Gemini)
need separate adapters and tests — do not assume protocol compatibility.

**No source-code changes are required** to configure multiple compatible
AI endpoints. Set one or more providers per role. Provider configuration,
tokens, original script text and local artifacts stay outside Git.

## Private provider profile

Save this JSON on your Mac or Pi in a private directory,
e.g. `~/Library/Application Support/KidsStudio/providers.local.json`:

    {
      "schema_version": 1,
      "providers": [
        {
          "id": "creative",
          "endpoint": "https://YOUR-EXPLICIT-APPROVED-HOST/v1/chat/completions",
          "model": "YOUR-EXACT-MODEL",
          "api_key_env": "KIDS_AI_CREATIVE_KEY",
          "billing": "free",
          "max_output_tokens": 1200
        },
        {
          "id": "critic",
          "endpoint": "https://YOUR-OTHER-APPROVED-HOST/v1/chat/completions",
          "model": "YOUR-EXACT-SECOND-MODEL",
          "api_key_env": "KIDS_AI_CRITIC_KEY",
          "billing": "free",
          "max_output_tokens": 1000
        }
      ],
      "routes": {
        "script_draft": ["creative"],
        "editorial_review": ["critic"]
      }
    }

`billing=free` is an *operator declaration*, not automatic verification
of actual provider prices, quotas or prompt billing. Set it only after
confirming the provider's terms; check API usage and account quotas.
The code never obtains or verifies current provider prices.

Store API keys in environment variables, e.g. set them in a local
password manager/Keychain-backed launch configuration or private runtime
environment. **Never paste real keys into GitHub, issue comments, PRs
or publicly visible chat transcripts.**

The router rejects remote HTTP, userinfo in URLs, redirects, HTTP proxy
environment forwarding, unapproved/unknown roles, missing API keys and
JSON bodies above the response cap. Nonlocal HTTPS destinations are
explicitly trusted by the local configuration owner; the router does not
independently validate account identity, provider privacy terms or quotas.

Default: at most one provider request, **no fallback**, free-labelled
profiles only. `--allow-paid` is an explicit override; it is not a spending
cap. Do not enable it until hard provider-side spend limits are configured.
Fallback exists only as an internal explicit option and is not enabled
by the local worker CLI.

## Local single-job Mac/Pi worker

With `studioctl` previously initialized on the **same local host**:

    studioctl --db /private/local/kidsstudio/studio.sqlite enqueue \
      --kind script_draft --key bunny-colors-ar-v1 \
      --payload-file /private/local/requests/episode.json

Contents of `episode.json`:

    {"language":"ar","topic":"An original bunny learns colors through play"}

Run exactly one job:

    studio-worker \
      --db /private/local/kidsstudio/studio.sqlite \
      --providers /private/local/kidsstudio/providers.local.json \
      --output-root /private/local/kidsstudio/artifacts \
      --worker-id mac-ai-01 --once

The worker claims one allowlisted job (`script_draft` or
`editorial_review`), contacts exactly one configured provider, writes
an answer and its SHA-256 provenance to a private attempt folder,
and completes/fails its fenced lease. Provider credentials and
the full answer are never written in SQLite; only the local artifact
location/hash, provider ID and model are recorded.

Review payloads must include a reference to the *actual creator provider*
(`original_provider_id`) and cannot use that same provider id;
this requires the director to preserve authoritative provenance. A local
worker may only label output `EDITORIAL_REVIEW_UNVERIFIED` —
not publish or officially approve the educational content.

For editorial review, `episode.json` is instead:

    {
      "language":"ar",
      "script_text":"The text to review",
      "original_provider_id":"creative"
    }

## Critical deployment boundary

The queue currently uses SQLite on the coordinator's **local disk**.
A Mac worker cannot safely share a Pi's SQLite database over SMB/NFS;
do not place the SQLite queue on Synology or claim a remote Mac worker
has been connected. This milestone verifies the local worker logic with
offline fake HTTP providers and real SQLite transactions only.

Future milestone: authenticated outbound Mac connection to a Pi service,
durable idempotent dispatch, TLS trust/worker roles, heartbeat + clock
health, cancel signals, file staging, audit and vault-backed credentials.
Only then will autonomous overnight Mac rendering be safe to deploy.

The Studio Director is still not an autonomous LLM authority: the queue
and local worker provide **execution scaffolding**, not a running
self-directed agent or a public YouTube publisher.
