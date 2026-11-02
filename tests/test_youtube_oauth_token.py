import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from kidsstudio.youtube_oauth_token import (
    OAuthTokenError, parse_token_response, refresh_access_token,
)


class OAuthRefreshTests(unittest.TestCase):
    def test_valid_token(self):
        self.assertEqual(parse_token_response({"access_token": "abc", "token_type": "Bearer"}), "abc")

    def test_missing_or_wrong_type_rejected(self):
        for payload in ({}, {"access_token": ""}, {"access_token": "abc", "token_type": "MAC"}):
            with self.subTest(payload=payload):
                with self.assertRaises(OAuthTokenError):
                    parse_token_response(payload)

    def test_mock_exchange(self):
        with patch("kidsstudio.youtube_oauth_token.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = json.dumps({
                "access_token": "short-lived-access-token",
                "token_type": "Bearer",
            }).encode()
            token = refresh_access_token("client", "secret", "refresh")
            self.assertEqual(token, "short-lived-access-token")
            request = opener.call_args.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertIn(b"grant_type=refresh_token", request.data)

    def test_http_error_does_not_expose_secret(self):
        with patch("kidsstudio.youtube_oauth_token.urlopen",
                   side_effect=HTTPError("https://oauth2.googleapis.com/token", 400, "invalid", {}, None)):
            with self.assertRaises(OAuthTokenError) as caught:
                refresh_access_token("client", "my-private-secret", "refresh")
            self.assertNotIn("my-private-secret", str(caught.exception))

    def test_empty_credentials_rejected(self):
        with self.assertRaises(ValueError):
            refresh_access_token("client", "", "refresh")


if __name__ == "__main__":
    unittest.main()
