# M68 — First Mac qualification (read-only)

Run from the KidsStudio repository on the Mac. No models are downloaded,
no inference is executed, and nothing is transferred to the Raspberry Pi.

## 1. Discover actual locally installed Ollama models

```bash
cd ~/KidsStudio
python3 -m kidsstudio.m68_mac_qualification \
  --inventory-only \
  --first-endpoint http://127.0.0.1:11434/api/chat \
  --second-endpoint http://127.0.0.1:11435/api/chat
```

The output reports local binary paths, reachable Ollama services and installed
model names. **A second Ollama service on port 11435 is not assumed to exist.**
If it is absent, the command reports a blocker rather than silently passing.

## 2. Qualify two real installed models

Replace `MODEL_A` and `MODEL_B` with names actually shown by the inventory
and use the correct loopback ports for each service:

```bash
python3 -m kidsstudio.m68_mac_qualification \
  --first-endpoint http://127.0.0.1:11434/api/chat \
  --first-model MODEL_A \
  --second-endpoint http://127.0.0.1:11435/api/chat \
  --second-model MODEL_B
```

Readiness means binaries and model names were found, **not** that they can
produce correct Arabic educational reviews. A live model trial and a separate
real Mac-to-Pi transfer and private YouTube upload trial remain mandatory.

## 3. Open the existing read-only production dashboard

Use the real existing Studio Brain SQLite path:

```bash
python3 -m kidsstudio.studio_dashboard \
  --db /ABSOLUTE/PATH/TO/STUDIO-BRAIN.sqlite \
  --educational-records /ABSOLUTE/PATH/TO/lesson-dashboard.json
```

Open `http://127.0.0.1:8793/`. The optional educational-records JSON file
is written by `m68_lesson_auto_cycle_cli` after an actual review cycle.
If the file does not exist yet, omit `--educational-records`; the panel
will say it is not configured.

**Do not treat any script-review pass as video approval or public release.**
