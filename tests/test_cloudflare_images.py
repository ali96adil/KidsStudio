import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kidsstudio.cloudflare_images import CloudflareImageError, generate_image


class CloudflareImageTests(unittest.TestCase):
    def test_disabled_never_calls_network(self):
        with patch("kidsstudio.cloudflare_images.request.urlopen") as net:
            with self.assertRaises(CloudflareImageError):
                generate_image("red balloon", "/tmp/unused.png", model="@cf/example")
            net.assert_not_called()

    def test_credentials_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(CloudflareImageError):
                generate_image("red balloon", "/tmp/unused.png", model="@cf/example", enabled=True)

    def test_invalid_model_rejected_before_network(self):
        with patch("kidsstudio.cloudflare_images.request.urlopen") as net:
            with self.assertRaises(ValueError):
                generate_image("red balloon", "/tmp/unused.png", model="../../bad", account_id="abc", api_token="secret", enabled=True)
            net.assert_not_called()

    def test_writes_png_without_overwrite(self):
        class Response:
            headers = {"Content-Type": "image/png"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
        # This test verifies transport framing, not full image decoding.
        Response.read = lambda self, count: bytes.fromhex("89504e470d0a1a0a") + b"data"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "image.png"
            with patch("kidsstudio.cloudflare_images.request.urlopen", return_value=Response()):
                self.assertEqual(generate_image("balloon", p, model="@cf/example", account_id="abc", api_token="secret", enabled=True), p)
            with self.assertRaises(FileExistsError):
                generate_image("balloon", p, model="@cf/example", account_id="abc", api_token="secret", enabled=True)
