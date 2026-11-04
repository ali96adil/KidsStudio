# Agent stage claims (local lease coordinator)

`kidsstudio.agent_stage_claims.claim_stage(root, episode_id, stage,
agent_id, lease_seconds=900)` grants a time-limited exclusive claim for
a ready checkpoint stage. A second agent is rejected while the lease is
active, even if the second request comes concurrently. The claim record
is private 0600 JSON, updated under a local advisory flock.

`release_stage(root, episode_id, stage, agent_id)` releases a claim
only for its owner. `read_claims(root, episode_id)` reports claims;
the MCP tool `kidsstudio_agent_stage_claims` exposes **read-only** claims.

A lease can be reclaimed after expiry. Expiry does not forcibly stop an
old worker. Production workers must check their lease again before
committing outputs and should use short-lived work units or renewals.
This implementation has no lease renewal or fencing token yet; it is
not sufficient for distributed multi-host Mac/Pi coordination.
Claim/release are **not** exposed through MCP, and never trigger
rendering, queueing, YouTube upload or public release.

Only use on a trusted local filesystem with cooperating workers.
Tests: `python3 -m unittest tests.test_agent_stage_claims -v`.
