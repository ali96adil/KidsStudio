"""Purely mocked HTTP wire tests: no DNS, HTTPS connection or Google API calls."""
from __future__ import annotations

import json
import types
import unittest
from unittest.mock import patch

from kidsstudio.pi_youtube_private_upload import HTTPSYouTubeTransport, YouTubePrivateError


SESSION = ("https://www.googleapis.com/upload/youtube/v3/videos?"
           "uploadType=resumable&upload_id=ABC12")


class Response:
    def __init__(self, code, headers=None, body=b""):
        self.status = code
        self._headers = headers or {}
        self._body = body
        self.length = len(body)

    def getheaders(self):
        return list(self._headers.items())

    def read(self, maximum):
        return self._body[:maximum]


class FakeHTTPSConnection:
    response = Response(200)
    calls = []
    hosts = []

    def __init__(self, host, timeout, context):
        self.hosts.append((host, timeout, context))
        self.record = []

    def request(self, method, target, body=b"", headers=None):
        self.calls.append((method, target, body, headers or {}))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class TransportWireTests(unittest.TestCase):
    def setUp(self):
        FakeHTTPSConnection.calls = []
        FakeHTTPSConnection.hosts = []
        FakeHTTPSConnection.response = Response(200)
        self.patch = patch(
            "kidsstudio.pi_youtube_private_upload.http.client.HTTPSConnection",
            FakeHTTPSConnection)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.transport = HTTPSYouTubeTransport()

    def test_resumable_initiation_exact_private_metadata(self):
        FakeHTTPSConnection.response = Response(200, {"Location": SESSION})
        result = self.transport.start(
            token="FAKE_ACCESS_TOKEN_12345", size=16,
            metadata={
                "snippet": {"title": "تعلم الألوان", "defaultLanguage": "ar"},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": True},
            })
        self.assertEqual(result, SESSION)
        method, target, body, headers = FakeHTTPSConnection.calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("uploadType=resumable", target)
        self.assertIn("notifySubscribers=false", target)
        self.assertEqual(headers["X-Upload-Content-Length"], "16")
        self.assertEqual(json.loads(body)["status"]["privacyStatus"], "private")
        self.assertEqual(headers["Authorization"], "Bearer FAKE_ACCESS_TOKEN_12345")
        self.assertEqual(FakeHTTPSConnection.hosts[0][0], "www.googleapis.com")

    def test_redirect_without_session_location_rejected(self):
        FakeHTTPSConnection.response = Response(302, {"Location": "https://evil.test"})
        with self.assertRaises(YouTubePrivateError):
            self.transport.start(
                token="FAKE_ACCESS_TOKEN_12345", size=1, metadata={})
        self.assertEqual(len(FakeHTTPSConnection.calls), 1)

    def test_malicious_location_rejected(self):
        FakeHTTPSConnection.response = Response(
            200, {"Location": "https://evil.test/upload/youtube/v3/videos?upload_id=Y"})
        with self.assertRaises(YouTubePrivateError):
            self.transport.start(
                token="FAKE_ACCESS_TOKEN_12345", size=1, metadata={})

    def test_chunk_range_and_body_are_exact(self):
        FakeHTTPSConnection.response = Response(308, {"Range": "bytes=0-9"})
        status, headers, body = self.transport.send_chunk(
            session=SESSION, token="FAKE_ACCESS_TOKEN_12345",
            data=b"1234567890", start=0, total=20)
        self.assertEqual(status, 308)
        self.assertEqual(headers["range"], "bytes=0-9")
        method, target, data, request_headers = FakeHTTPSConnection.calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(data, b"1234567890")
        self.assertEqual(request_headers["Content-Range"], "bytes 0-9/20")
        self.assertEqual(request_headers["Content-Length"], "10")

    def test_zero_length_probe(self):
        FakeHTTPSConnection.response = Response(308)
        self.transport.probe(session=SESSION,
                             token="FAKE_ACCESS_TOKEN_12345", size=100)
        method, _, payload, headers = FakeHTTPSConnection.calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(payload, b"")
        self.assertEqual(headers["Content-Range"], "bytes */100")

    def test_video_status_checks_id_and_returns_private(self):
        FakeHTTPSConnection.response = Response(200, body=json.dumps({
            "items": [{"id": "exampleVid9", "status": {"privacyStatus": "private"}}]
        }).encode("utf-8"))
        status = self.transport.video_status(
            token="FAKE_ACCESS_TOKEN_12345", video_id="exampleVid9")
        self.assertEqual(status["privacyStatus"], "private")
        method, path, _, _ = FakeHTTPSConnection.calls[0]
        self.assertEqual(method, "GET")
        self.assertIn("part=status", path)
        self.assertIn("id=exampleVid9", path)

    def test_oauth_refresh_payload_secrets_only_in_body(self):
        FakeHTTPSConnection.response = Response(200, body=json.dumps({
            "access_token": "FAKE_ACCESS_TOKEN_12345",
            "expires_in": 3600,
        }).encode())
        token, ttl = self.transport.refresh(
            "CLIENT_ID_TEST", "CLIENT_SECRET_TEST", "REFRESH_TOKEN_TEST")
        self.assertEqual(ttl, 3600)
        self.assertEqual(token, "FAKE_ACCESS_TOKEN_12345")
        method, path, body, headers = FakeHTTPSConnection.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/token")
        self.assertIn(b"refresh_token=REFRESH_TOKEN_TEST", body)
        self.assertNotIn("REFRESH_TOKEN_TEST", path)
        self.assertEqual(FakeHTTPSConnection.hosts[0][0], "oauth2.googleapis.com")

    def test_oauth_refresh_errors_do_not_echo_server_body(self):
        FakeHTTPSConnection.response = Response(
            401, body=b"private token do not disclose")
        with self.assertRaises(YouTubePrivateError) as context:
            self.transport.refresh(
                "CLIENT_ID_TEST", "CLIENT_SECRET_TEST", "REFRESH_TOKEN_TEST")
        self.assertNotIn("private token", str(context.exception))

    def test_untrusted_endpoint_not_contacted(self):
        with self.assertRaises(YouTubePrivateError):
            self.transport._request("https://evil.test/steal", "GET", {})
        self.assertEqual(FakeHTTPSConnection.calls, [])

    def test_large_response_rejected(self):
        FakeHTTPSConnection.response = Response(
            200, body=b"x" * (128 * 1024 + 1))
        with self.assertRaises(YouTubePrivateError):
            self.transport._request("https://www.googleapis.com/test", "GET", {})


if __name__ == "__main__":
    unittest.main()
