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

**Concurrency:** transition now uses a per-episode advisory `flock` lock\nso cooperating local writers serialize read/validate/replace. The lock\nfile is private 0600 and remains for reuse. This is not a distributed\nlock: all writers must use this API and the same local filesystem. Do not\nstore checkpoints in a directory writable by untrusted users. Stage\nmutations remain unavailable through MCP; remote or distributed workers\nneed an additional coordination layer.

Test: `python3 -m unittest tests.test_episode_stage_checkpoints -v`.
