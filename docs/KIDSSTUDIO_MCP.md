# KidsStudio MCP (first read-only milestone)

Start from the repository root on the Mac:

```bash
python3 -m kidsstudio.mcp_server
```

The server communicates using newline-delimited JSON-RPC over stdin/stdout
(MCP stdio transport); it does not bind a network port. Configure an MCP client
with command `python3`, arguments `-m`, `kidsstudio.mcp_server`, and
working directory set to the KidsStudio repository root (or install the
package in the client's Python environment).

Current tools:
- `mac_pi_compare_reports`: compares Mac precheck and Pi received-media reports passed as JSON objects; checks episode, size, SHA-256, and offline-only safety flags. No filesystem or network access.\n- `kidsstudio_capabilities`: read-only capability and safety report.
- `pi_received_media_precheck`: checks a received MP4 and matching JSON manifest in a local Pi staging directory (SHA-256, size and naming); read-only and never queues uploads. Requires staging_dir and manifest_name.\n- `mac_pi_transfer_precheck`: hashes a local MP4 and checks safe naming
  for Mac-to-Pi transfer. Requires video, episode_id, ssh_target,
  remote_staging_dir. **Does not contact SSH or transfer files.**

This milestone does not expose render execution, Pi commands, credential
access, YouTube uploads, queue mutations, or public publishing. Add
privileged tools only after an explicit permission model and hardware tests.
Do not connect the stdio process to an untrusted remote agent with unrestricted
filesystem access. The precheck reads local files by path and may be expensive
for large videos.

Test locally: `python3 -m unittest tests.test_mcp_server -v`.
CI tests protocol handling without opening network connections.
