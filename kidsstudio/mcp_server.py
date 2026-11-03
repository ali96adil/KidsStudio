"""Read-only KidsStudio MCP server over newline-delimited JSON-RPC stdio.

Run: python3 -m kidsstudio.mcp_server
No network listener, uploads, queue writes, or publishing.
"""
from __future__ import annotations

import json
import sys

from .mac_pi_transfer_precheck import precheck

PROTOCOL_VERSION = "2025-03-26"
TOOLS = [
    {
        "name": "kidsstudio_capabilities",
        "description": "Read supported KidsStudio MCP capabilities and safety restrictions.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "mac_pi_transfer_precheck",
        "description": "Offline-only video digest and Mac-to-Pi transfer naming precheck. No SSH or transfer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video": {"type": "string"},
                "episode_id": {"type": "string"},
                "ssh_target": {"type": "string"},
                "remote_staging_dir": {"type": "string"},
            },
            "required": ["video", "episode_id", "ssh_target", "remote_staging_dir"],
            "additionalProperties": False,
        },
    },
]


def _result(value: dict, *, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}],
            "isError": error}


def handle(message: dict) -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ValueError("expected JSON-RPC 2.0 object")
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if request_id is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION,
                  "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "kidsstudio-readonly", "version": "0.1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            result = _result({"error": "invalid tool parameters"}, error=True)
        elif params.get("name") == "kidsstudio_capabilities":
            result = _result({"mode": "read_only", "network_listener": False,
                              "ssh_transfer": False, "youtube_upload": False,
                              "public_release_authorized": False,
                              "tools": [item["name"] for item in TOOLS]})
        elif params.get("name") == "mac_pi_transfer_precheck":
            args = params.get("arguments", {})
            required = {"video", "episode_id", "ssh_target", "remote_staging_dir"}
            if not isinstance(args, dict) or set(args) != required or any(
                    not isinstance(v, str) or not v for v in args.values()):
                result = _result({"error": "expected four nonempty string arguments"}, error=True)
            else:
                try:
                    result = _result(precheck(args["video"], args["episode_id"],
                                              args["ssh_target"], args["remote_staging_dir"]))
                except (ValueError, OSError) as exc:
                    result = _result({"error": type(exc).__name__,
                                      "message": str(exc)}, error=True)
        else:
            result = _result({"error": "unknown tool"}, error=True)
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = handle(message)
        except (ValueError, TypeError) as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
