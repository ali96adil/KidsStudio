"""Tests for durable M68 short identity and private staging registry."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry, ShortRegistryError


class ShortRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        queue = StudioQueue(Path(self.tmp.name) / "queue.sqlite")
        queue.initialize()
        self.registry = ShortRegistry(queue)
        self.registry.initialize()

    def test_idempotent_registration_without_upload(self):
        args = dict(short_id="colors-short-01", source_episode_id="colors",
                    media_sha256="a" * 64)
        first = self.registry.register(**args)
        again = self.registry.register(**args)
        self.assertEqual(first, again)
        self.assertFalse(first["youtube_upload_authorized"])

    def test_different_short_cannot_reuse_same_video(self):
        self.registry.register(short_id="colors-short-01",
                               source_episode_id="colors", media_sha256="a" * 64)
        with self.assertRaises(ShortRegistryError):
            self.registry.register(short_id="colors-short-02",
                                   source_episode_id="colors", media_sha256="a" * 64)

    def test_verified_staging_still_not_approved(self):
        self.registry.register(short_id="colors-short-01",
                               source_episode_id="colors", media_sha256="a" * 64)
        receipt = {"status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
                   "short_id": "colors-short-01",
                   "source_episode_id": "colors", "sha256": "a" * 64,
                   "youtube_upload_authorized": False,
                   "public_release_authorized": False}
        result = self.registry.mark_staged(
            short_id="colors-short-01", media_sha256="a" * 64,
            transfer_receipt=receipt)
        self.assertEqual(result["status"], "PI_STAGED_NOT_APPROVED")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_wrong_staging_receipt_rejected(self):
        self.registry.register(short_id="colors-short-01",
                               source_episode_id="colors", media_sha256="a" * 64)
        with self.assertRaises(ShortRegistryError):
            self.registry.mark_staged(short_id="colors-short-01",
                                      media_sha256="a" * 64, transfer_receipt={})
