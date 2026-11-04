# Agent handoff ledger

Original KidsStudio implementation inspired by OpenMontage's agent handoff
workflow. `agent_handoff_ledger.record_handoff(root, episode_id, stage,
agent_id, event, note="")` appends a timestamped record. Allowed events:
`assigned`, `started`, `completed`, `failed`. Stage and episode must
exist in a checkpoint. The ledger is a private 0600 append-only JSONL file
with local advisory `flock` and fsync per record.

`read_handoffs(root, episode_id)` returns the event history and next
checkpoint stage. MCP tool `kidsstudio_agent_handoff_history` exposes
**read-only** history to agents. No agent is allowed to write the ledger
through MCP. No uploads or public release are possible.

Important: handoff events are an audit trail, **not authoritative stage
transitions**. Stage state remains controlled by checkpoint transition.
This ledger does not enforce unique owners, leases, or distributed
coordination between Mac and Pi. Notes should not contain secrets.
Do not store on untrusted writable directories.

Test: `python3 -m unittest tests.test_agent_handoff_ledger -v`.
