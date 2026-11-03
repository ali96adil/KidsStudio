import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.mcp_server import handle
from kidsstudio.pi_media_inbox import build_manifest


def rpc(method, params=None, request_id=1):
    msg = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        msg["params"] = params
    return handle(msg)


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tool_list(self):
        init = rpc("initialize", {"protocolVersion": "2025-03-26"})["result"]
        self.assertEqual(init["serverInfo"]["name"], "kidsstudio-readonly")
        names = [tool["name"] for tool in rpc("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["kidsstudio_capabilities", "pi_received_media_precheck", "mac_pi_transfer_precheck"])
        self.assertIsNone(handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_capabilities_are_read_only(self):
        response = rpc("tools/call", {"name": "kidsstudio_capabilities", "arguments": {}})
        value = json.loads(response["result"]["content"][0]["text"])
        self.assertFalse(value["youtube_upload"])
        self.assertFalse(value["public_release_authorized"])

    def test_precheck_never_transfers(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "episode.mp4"
            video.write_bytes(b"episode")
            response = rpc("tools/call", {"name": "mac_pi_transfer_precheck",
                "arguments": {"video": str(video), "episode_id": "colors_001",
                              "ssh_target": "pi@host",
                              "remote_staging_dir": "/home/pi/staging"}})
            self.assertFalse(response["result"]["isError"])
            report = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(report["status"], "READY_FOR_TRANSFER_NOT_TRANSFERRED")
            self.assertFalse(report["youtube_uploaded"])

    def test_pi_received_verification_and_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            video = base / "render.mp4"
            video.write_bytes(b"original educational video")
            manifest = build_manifest(video, "colors_001")
            prefix = "colors_001-" + manifest["sha256"][:16]
            target = base / (prefix + ".mp4")
            target.write_bytes(video.read_bytes())
            manifest["filename"] = target.name
            metadata = base / (prefix + ".json")
            metadata.write_text(json.dumps(manifest))
            args = {"name": "pi_received_media_precheck",
                    "arguments": {"staging_dir": str(base), "manifest_name": metadata.name}}
            response = rpc("tools/call", args)
            self.assertFalse(response["result"]["isError"])
            value = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(value["status"], "PI_MEDIA_VERIFIED_NOT_QUEUED")
            self.assertFalse(value["youtube_uploaded"])
            target.write_bytes(b"corrupted")
            response = rpc("tools/call", args)
            self.assertTrue(response["result"]["isError"])

    def test_unknown_tool_and_invalid_arguments_fail_closed(self):
        for params in ({"name": "upload_public", "arguments": {}},
                       {"name": "mac_pi_transfer_precheck", "arguments": {}}):
            response = rpc("tools/call", params)
            self.assertTrue(response["result"]["isError"])
        self.assertEqual(rpc("unknown")["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
