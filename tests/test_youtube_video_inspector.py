import unittest
from unittest.mock import patch
from io import BytesIO

from kidsstudio.youtube_video_inspector import (
    inspect_video, parse_video_response, YouTubeInspectError,
)


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.video_id = "Abc123_defG"
        self.valid = {"items": [{
            "id": self.video_id,
            "snippet": {"channelId": "channel-123"},
            "status": {"privacyStatus": "private"},
        }]}

    def test_parse_private_video(self):
        info = parse_video_response(self.valid, self.video_id)
        self.assertEqual(info["privacy"], "private")
        self.assertTrue(info["read_only"])

    def test_reject_missing_and_mismatched_video(self):
        with self.assertRaises(YouTubeInspectError):
            parse_video_response({"items": []}, self.video_id)
        with self.assertRaises(YouTubeInspectError):
            parse_video_response(self.valid, "Other123456")

    def test_reject_missing_privacy(self):
        bad = {"items": [{
            "id": self.video_id,
            "snippet": {"channelId": "channel-123"},
            "status": {},
        }]}
        with self.assertRaises(YouTubeInspectError):
            parse_video_response(bad, self.video_id)

    def test_reject_invalid_credentials_without_network(self):
        with self.assertRaises(ValueError):
            inspect_video(self.video_id, "")

    def test_mock_read_only_api(self):
        import json
        with patch("kidsstudio.youtube_video_inspector.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = json.dumps(self.valid).encode()
            result = inspect_video(self.video_id, "fake-token")
            self.assertEqual(result["channel_id"], "channel-123")
            request = opener.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")


if __name__ == "__main__":
    unittest.main()
