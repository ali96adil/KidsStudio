# Episode stage checkpoints

An original KidsStudio implementation of stage-by-stage progress inspired by
OpenMontage's pipeline manifests and checkpoints.

`kidsstudio.episode_stage_checkpoints.initialize(root, episode_id, pipeline)`
creates a private 0600 JSON file. It fails rather than overwriting an
existing episode. `status(root, episode_id)` reports completed stage states
and `next_stage`; this is available via the read-only MCP tool
`kidsstudio_episode_checkpoint_status` (arguments: root, episode_id).

`transition(root, episode_id, stage, new_state)` is a local Python API,
**not exposed to MCP**. It accepts pending→running→passed or failed→running,
and requires earlier stages to pass before advancing. The state is atomically
replaced with fsync and 0600 permissions. No YouTube upload or public release
is possible through these APIs.

**Deployment restriction:** transition is designed for one trusted local
writer only. Do not use concurrent workers against the same checkpoint file:
atomic replace alone does not provide multi-writer locking. Do not store
checkpoints in a directory writable by untrusted users. Production
multi-agent writes require an exclusive lock and stale-write protection
before enabling stage mutations through any agent API.

Test: `python3 -m unittest tests.test_episode_stage_checkpoints -v`.
