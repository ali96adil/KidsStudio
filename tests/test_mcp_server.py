import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.mcp_server import handle


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
        self.assertEqual(names, ["kidsstudio_capabilities", "mac_pi_transfer_precheck"])
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

    def test_unknown_tool_and_invalid_arguments_fail_closed(self):
        for params in ({"name": "upload_public", "arguments": {}},
                       {"name": "mac_pi_transfer_precheck", "arguments": {}}):
            response = rpc("tools/call", params)
            self.assertTrue(response["result"]["isError"])
        self.assertEqual(rpc("unknown")["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
