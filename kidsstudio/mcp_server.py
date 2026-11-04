"""Read-only KidsStudio MCP server over newline-delimited JSON-RPC stdio.

Run: python3 -m kidsstudio.mcp_server
No network listener, uploads, queue writes, or publishing.
"""
from __future__ import annotations

import json
import sys

from .mac_pi_transfer_precheck import precheck
from .pi_received_media_precheck import verify_received
from .mac_pi_integrity_compare import compare_reports
from .openmontage_pipeline_bridge import plan_episode
from .episode_stage_checkpoints import status as checkpoint_status
from .agent_handoff_ledger import read_handoffs

PROTOCOL_VERSION = "2025-03-26"
TOOLS = [
    {
        "name": "kidsstudio_agent_handoff_history",
        "description": "Read agent handoff event history for an episode. No mutation or execution.",
        "inputSchema": {"type": "object", "properties": {
            "root": {"type": "string"}, "episode_id": {"type": "string"}},
            "required": ["root", "episode_id"], "additionalProperties": False},
    },
    {
        "name": "kidsstudio_episode_checkpoint_status",
        "description": "Read private local checkpoint progress and next pending stage; never change stage state.",
        "inputSchema": {"type": "object", "properties": {
            "root": {"type": "string"}, "episode_id": {"type": "string"}},
            "required": ["root", "episode_id"], "additionalProperties": False},
    },
    {
        "name": "kidsstudio_plan_episode",
        "description": "Plan a child-safe animated, bilingual or printable production pipeline. No execution or upload.",
        "inputSchema": {"type": "object", "properties": {
            "episode_id": {"type": "string"}, "topic": {"type": "string"},
            "language": {"type": "string", "enum": ["ar", "en"]},
            "kind": {"type": "string", "enum": ["animated_explainer", "bilingual_localization", "coloring_companion"]},
            "available_engines": {"type": "array", "items": {"type": "string"}}},
            "required": ["episode_id", "topic"], "additionalProperties": False},
    },
    {
        "name": "kidsstudio_capabilities",
        "description": "Read supported KidsStudio MCP capabilities and safety restrictions.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "mac_pi_compare_reports",
        "description": "Compare offline Mac and Pi media verification reports. Does not access the network.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac_report": {"type": "object"},
                "pi_report": {"type": "object"},
            },
            "required": ["mac_report", "pi_report"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pi_received_media_precheck",
        "description": "Read-only SHA-256 and schema verification of a received Pi staging manifest and MP4. No queue or upload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "staging_dir": {"type": "string"},
                "manifest_name": {"type": "string"},
            },
            "required": ["staging_dir", "manifest_name"],
            "additionalProperties": False,
        },
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
        elif params.get("name") == "kidsstudio_agent_handoff_history":
            args = params.get("arguments", {})
            if (not isinstance(args, dict) or set(args) != {"root", "episode_id"}
                    or any(not isinstance(v, str) or not v for v in args.values())):
                result = _result({"error": "expected root and episode_id"}, error=True)
            else:
                try:
                    result = _result(read_handoffs(args["root"], args["episode_id"]))
                except (ValueError, OSError) as exc:
                    result = _result({"error": type(exc).__name__, "message": str(exc)}, error=True)
        elif params.get("name") == "kidsstudio_episode_checkpoint_status":
            args = params.get("arguments", {})
            if (not isinstance(args, dict) or set(args) != {"root", "episode_id"}
                    or any(not isinstance(v, str) or not v for v in args.values())):
                result = _result({"error": "expected root and episode_id"}, error=True)
            else:
                try:
                    result = _result(checkpoint_status(args["root"], args["episode_id"]))
                except (ValueError, OSError) as exc:
                    result = _result({"error": type(exc).__name__, "message": str(exc)}, error=True)
        elif params.get("name") == "kidsstudio_plan_episode":
            args = params.get("arguments", {})
            if (not isinstance(args, dict) or not {"episode_id", "topic"} <= set(args)
                    or set(args) - {"episode_id", "topic", "language", "kind", "available_engines"}):
                result = _result({"error": "invalid episode plan arguments"}, error=True)
            else:
                try:
                    result = _result(plan_episode(**args))
                except (ValueError, TypeError) as exc:
                    result = _result({"error": type(exc).__name__, "message": str(exc)}, error=True)
        elif params.get("name") == "mac_pi_compare_reports":
            args = params.get("arguments", {})
            if (not isinstance(args, dict) or set(args) != {"mac_report", "pi_report"}
                    or not isinstance(args["mac_report"], dict)
                    or not isinstance(args["pi_report"], dict)):
                result = _result({"error": "expected mac_report and pi_report objects"}, error=True)
            else:
                try:
                    result = _result(compare_reports(args["mac_report"], args["pi_report"]))
                except (ValueError, TypeError) as exc:
                    result = _result({"error": type(exc).__name__,
                                      "message": str(exc)}, error=True)
        elif params.get("name") == "pi_received_media_precheck":
            args = params.get("arguments", {})
            required = {"staging_dir", "manifest_name"}
            if not isinstance(args, dict) or set(args) != required or any(
                    not isinstance(v, str) or not v for v in args.values()):
                result = _result({"error": "expected two nonempty string arguments"}, error=True)
            else:
                try:
                    result = _result(verify_received(args["staging_dir"], args["manifest_name"]))
                except (ValueError, OSError) as exc:
                    result = _result({"error": type(exc).__name__,
                                      "message": str(exc)}, error=True)
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
