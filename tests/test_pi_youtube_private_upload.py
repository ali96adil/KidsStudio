from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kidsstudio.pi_youtube_private_upload import (
    YouTubePrivateError, HTTPSYouTubeTransport, TokenProvider,
    _safe_session_url, _offset, _load_journal, execute_private_upload,
    load_private_oauth, main,
)


SESSION = ("https://www.googleapis.com/upload/youtube/v3/videos?"
           "uploadType=resumable&upload_id=TEST123&part=snippet,status")
VIDEO = "testVideo-11"


class FakeYouTube:
    def __init__(self, *, reject_start=False, fail_chunk_number=None,
                 final_private=True, probe_returns_final=False):
        self.started = 0
        self.calls = []
        self.ack = 0
        self.metadata = None
        self.reject_start = reject_start
        self.fail_chunk_number = fail_chunk_number
        self.final_private = final_private
        self.probe_returns_final = probe_returns_final
        self.total = None

    def start(self, *, token, metadata, size):
        self.started += 1
        self.metadata = metadata
        self.total = size
        self.calls.append(("start", size))
        if self.reject_start:
            raise YouTubePrivateError("simulated ambiguous initiation")
        return SESSION

    def probe(self, *, session, token, size):
        self.calls.append(("probe", size))
        if session != SESSION or size != self.total:
            raise AssertionError("Incorrect session")
        if self.probe_returns_final:
            return 201, {}, json.dumps({
                "id": VIDEO,
                "status": {"privacyStatus": "private"},
            }).encode()
        if self.ack:
            return 308, {"range": f"bytes=0-{self.ack-1}"}, b""
        return 308, {}, b""

    def send_chunk(self, *, session, token, data, start, total):
        self.calls.append(("chunk", start, len(data)))
        if self.fail_chunk_number == sum(x[0] == "chunk" for x in self.calls):
            raise YouTubePrivateError("temporary network drop")
        if session != SESSION or start != self.ack or total != self.total:
            raise AssertionError("Duplicate/out-of-order upload")
        self.ack += len(data)
        if self.ack == self.total:
            return 201, {}, json.dumps({
                "id": VIDEO,
                "status": {"privacyStatus": "private" if self.final_private else "public"},
            }).encode()
        return 308, {"range": f"bytes=0-{self.ack-1}"}, b""

    def video_status(self, *, token, video_id):
        self.calls.append(("verify", video_id))
        if video_id != VIDEO:
            raise AssertionError("Unknown video")
        return {"privacyStatus": "private" if self.final_private else "public"}


class PrivateUploaderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.file = self.root / "episode.mp4"
        self.file.write_bytes(b"KIDS_STUDIO_FAKE_MP4_NOT_PLAYABLE_" * 80000)
        self.file.chmod(0o600)
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.journal = self.root / "upload-state.json"

    def upload(self, backend=None, **changes):
        settings = {
            "private_root": str(self.root),
            "relative_path": "episode.mp4",
            "expected_sha256": self.sha,
            "episode_id": "colors_ar_001",
            "title": "تعلم الألوان",
            "description": "أصلي وآمن",
            "language": "ar",
            "journal_file": str(self.journal),
            "owner_authorized": True,
            "made_for_kids_confirmed": True,
            "transport": backend or FakeYouTube(),
            "token_provider": lambda: "FAKE_ACCESS_TOKEN_12345",
        }
        settings.update(changes)
        return execute_private_upload(**settings)

    def test_complete_private_upload_provenance_and_journal(self):
        backend = FakeYouTube()
        result = self.upload(backend)
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(result["video_id"], VIDEO)
        self.assertFalse(result["publication_approved"])
        self.assertEqual(backend.started, 1)
        self.assertEqual(backend.metadata["status"]["privacyStatus"], "private")
        self.assertTrue(backend.metadata["status"]["selfDeclaredMadeForKids"])
        self.assertNotIn("publishAt", backend.metadata["status"])
        self.assertEqual(backend.ack, self.file.stat().st_size)
        stored = _load_journal(self.journal)
        self.assertEqual(stored["state"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(stored["video_id"], VIDEO)
        self.assertNotIn("session_url", stored)
        self.assertEqual(self.journal.stat().st_mode & 0o077, 0)

    def test_finished_upload_does_not_duplicate_on_repeat(self):
        backend = FakeYouTube()
        self.upload(backend)
        repeated = self.upload(backend)
        self.assertEqual(repeated["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertTrue(repeated["from_existing_journal"])
        self.assertEqual(backend.started, 1)

    def test_confirmed_upload_rechecks_remote_visibility(self):
        backend = FakeYouTube()
        self.upload(backend)
        backend.final_private = False
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(backend.started, 1)
        self.assertEqual(_load_journal(self.journal)["state"], "PRIVATE_UPLOAD_CONFIRMED")

    def test_oauth_failure_does_not_create_ambiguous_upload_journal(self):
        backend = FakeYouTube()
        def failed_oauth():
            raise YouTubePrivateError("simulated OAuth denial")
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=failed_oauth)
        self.assertFalse(self.journal.exists())
        self.assertEqual(backend.calls, [])

    def test_explicit_authorization_required_before_network_or_journal(self):
        backend = FakeYouTube()
        for changes in ({"owner_authorized": False},
                        {"made_for_kids_confirmed": False}):
            with self.assertRaises(YouTubePrivateError):
                self.upload(backend, **changes)
        self.assertEqual(backend.calls, [])
        self.assertFalse(self.journal.exists())

    def test_internal_mux_candidate_blocks_uploader_before_network_or_journal(self):
        candidate = self.root / "verified-candidate.mp4"
        candidate.write_bytes(self.file.read_bytes())
        candidate.chmod(0o600)
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        backend = FakeYouTube()
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(
                backend, relative_path=candidate.name,
                expected_sha256=digest, token_provider=token_provider)
        self.assertEqual(backend.calls, [])
        self.assertEqual(token_calls, [])
        self.assertFalse(self.journal.exists())

    def test_wrong_sha_blocks_no_journal_no_network(self):
        backend = FakeYouTube()
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, expected_sha256="0" * 64)
        self.assertEqual(backend.calls, [])
        self.assertFalse(self.journal.exists())

    def test_private_media_permission_required(self):
        backend = FakeYouTube()
        self.file.chmod(0o644)
        with self.assertRaises(ValueError):
            self.upload(backend)
        self.assertEqual(backend.calls, [])

    def test_session_initiation_failure_leaves_ambiguous_journal(self):
        backend = FakeYouTube(reject_start=True)
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(_load_journal(self.journal)["state"], "INITIATION_UNCERTAIN")
        backend.reject_start = False
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(backend.started, 1)

    def test_mid_chunk_failure_resumes_without_second_session(self):
        backend = FakeYouTube(fail_chunk_number=2)
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(_load_journal(self.journal)["state"], "SESSION_ACTIVE")
        self.assertEqual(backend.started, 1)
        backend.fail_chunk_number = None
        result = self.upload(backend)
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(backend.started, 1)
        self.assertGreaterEqual(sum(c[0] == "probe" for c in backend.calls), 2)

    def test_lost_chunk_response_recovers_from_remote_ack_not_stale_local_offset(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        original_send = backend.send_chunk
        lost_response = [True]

        def accept_then_disconnect(**kwargs):
            result = original_send(**kwargs)
            if lost_response[0]:
                lost_response[0] = False
                raise YouTubePrivateError("synthetic response lost after remote acknowledgement")
            return result

        backend.send_chunk = accept_then_disconnect
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        acknowledged = backend.ack
        self.assertGreater(acknowledged, 0)
        self.assertEqual(_load_journal(self.journal)["state"], "SESSION_ACTIVE")

        # Older or interrupted clients may leave a stale local progress hint.
        # Recovery must probe the resumable endpoint and use its confirmed range.
        record = _load_journal(self.journal)
        record["bytes_remote_acknowledged"] = self.file.stat().st_size
        _save_journal(self.journal, record)
        result = self.upload(backend)

        self.assertEqual(result["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(backend.started, 1)
        self.assertEqual(backend.ack, self.file.stat().st_size)
        chunk_starts = [call[1] for call in backend.calls if call[0] == "chunk"]
        self.assertEqual(chunk_starts[0], 0)
        self.assertEqual(chunk_starts[1], acknowledged)

    def test_lost_final_response_recovers_video_id_from_existing_session_probe(self):
        backend = FakeYouTube()
        original_send = backend.send_chunk

        def lose_final_response(**kwargs):
            result = original_send(**kwargs)
            if result[0] in (200, 201):
                raise YouTubePrivateError("synthetic final response lost")
            return result

        backend.send_chunk = lose_final_response
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(backend.ack, self.file.stat().st_size)
        self.assertEqual(_load_journal(self.journal)["state"], "SESSION_ACTIVE")
        self.assertEqual(backend.started, 1)
        chunks_before_resume = sum(call[0] == "chunk" for call in backend.calls)

        backend.probe_returns_final = True
        result = self.upload(backend)

        self.assertEqual(result["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(result["video_id"], VIDEO)
        self.assertEqual(backend.started, 1)
        self.assertEqual(sum(call[0] == "probe" for call in backend.calls), 2)
        self.assertEqual(sum(call[0] == "chunk" for call in backend.calls),
                         chunks_before_resume)

    def test_invalid_active_session_recovery_fails_before_token_or_transport(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        self.upload(backend, max_chunks_per_run=1)
        record = _load_journal(self.journal)
        record["session_url"] = "https://attacker.example/upload?upload_id=stolen"
        _save_journal(self.journal, record)
        calls_before = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, calls_before)
        self.assertEqual(token_calls, [])
        self.assertEqual(_load_journal(self.journal)["session_url"],
                         "https://attacker.example/upload?upload_id=stolen")

    def test_active_session_missing_url_is_a_safe_recovery_error(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        self.upload(backend, max_chunks_per_run=1)
        record = _load_journal(self.journal)
        record.pop("session_url")
        _save_journal(self.journal, record)
        calls_before = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, calls_before)
        self.assertEqual(token_calls, [])
        self.assertNotIn("session_url", _load_journal(self.journal))

    def test_pause_after_one_chunk_then_resume(self):
        backend = FakeYouTube()
        first = self.upload(backend, max_chunks_per_run=1)
        self.assertEqual(first["status"], "UPLOAD_PAUSED_RESUMABLE")
        self.assertGreater(first["bytes_remote_acknowledged"], 0)
        second = self.upload(backend)
        self.assertEqual(second["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(backend.started, 1)

    def test_private_journal_does_not_expose_session_in_stdout(self):
        backend = FakeYouTube()
        result = self.upload(backend, max_chunks_per_run=1)
        self.assertNotIn(SESSION, str(result))
        self.assertIn("session_url", _load_journal(self.journal))
        self.assertEqual(self.journal.stat().st_mode & 0o077, 0)

    def test_resumable_journal_anchor_mismatches_block_before_side_effects(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        first = self.upload(backend, max_chunks_per_run=1)
        self.assertEqual(first["status"], "UPLOAD_PAUSED_RESUMABLE")
        baseline = _load_journal(self.journal)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        for field, value in (
            ("media_name", "different-episode.mp4"),
            ("episode_id", "different_episode"),
            ("media_sha256", "0" * 64),
            ("media_bytes", baseline["media_bytes"] + 1),
        ):
            with self.subTest(field=field):
                changed = dict(baseline, **{field: value})
                _save_journal(self.journal, changed)
                before_calls = list(backend.calls)
                with self.assertRaises(YouTubePrivateError):
                    self.upload(backend, token_provider=token_provider)
                self.assertEqual(backend.calls, before_calls)
                self.assertEqual(token_calls, [])
                self.assertEqual(_load_journal(self.journal)[field], value)
                _save_journal(self.journal, baseline)

    def test_changed_metadata_cannot_use_existing_session(self):
        backend = FakeYouTube()
        self.upload(backend, max_chunks_per_run=1)
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, title="different")
        self.assertEqual(backend.started, 1)

    def test_public_server_upload_response_rejected(self):
        backend = FakeYouTube(final_private=False)
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertNotEqual(_load_journal(self.journal)["state"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(backend.started, 1)

    def test_private_insert_but_public_subsequent_lookup_blocks(self):
        backend = FakeYouTube()
        def other_status(*, token, video_id):
            return {"privacyStatus": "public"}
        backend.video_status = other_status
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(_load_journal(self.journal)["state"], "REMOTE_COMPLETED_UNVERIFIED")
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(backend.started, 1)

    def test_existing_completed_state_verified_on_separate_run(self):
        backend = FakeYouTube()
        backend.video_status = lambda *, token, video_id: (_ for _ in ()).throw(
            YouTubePrivateError("timeout"))
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(_load_journal(self.journal)["state"], "REMOTE_COMPLETED_UNVERIFIED")
        backend.video_status = lambda *, token, video_id: {"privacyStatus": "private"}
        result = self.upload(backend)
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_CONFIRMED")
        self.assertEqual(backend.started, 1)

    def test_changed_media_is_not_uploaded_again(self):
        backend = FakeYouTube()
        self.upload(backend, max_chunks_per_run=1)
        self.file.write_bytes(b"changed")
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(backend.started, 1)

    def test_confirmed_journal_invalid_video_id_blocks_before_token_or_transport(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        self.upload(backend)
        record = _load_journal(self.journal)
        record["video_id"] = "invalid!"
        _save_journal(self.journal, record)
        before_calls = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, before_calls)
        self.assertEqual(token_calls, [])

    def test_unverified_completed_journal_invalid_video_id_blocks_before_side_effects(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        backend.video_status = lambda *, token, video_id: (_ for _ in ()).throw(
            YouTubePrivateError("synthetic status interruption"))
        with self.assertRaises(YouTubePrivateError):
            self.upload(backend)
        self.assertEqual(_load_journal(self.journal)["state"],
                         "REMOTE_COMPLETED_UNVERIFIED")
        record = _load_journal(self.journal)
        record["video_id"] = "invalid!"
        _save_journal(self.journal, record)
        before_calls = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, before_calls)
        self.assertEqual(token_calls, [])

    def test_session_active_journal_with_video_id_is_rejected_before_side_effects(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        self.upload(backend, max_chunks_per_run=1)
        record = _load_journal(self.journal)
        self.assertEqual(record["state"], "SESSION_ACTIVE")
        record["video_id"] = VIDEO
        _save_journal(self.journal, record)
        before_calls = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, before_calls)
        self.assertEqual(token_calls, [])

    def test_confirmed_journal_with_session_url_is_rejected_before_side_effects(self):
        from kidsstudio.pi_youtube_private_upload import _save_journal

        backend = FakeYouTube()
        self.upload(backend)
        record = _load_journal(self.journal)
        self.assertEqual(record["state"], "PRIVATE_UPLOAD_CONFIRMED")
        record["session_url"] = SESSION
        _save_journal(self.journal, record)
        before_calls = list(backend.calls)
        token_calls = []

        def token_provider():
            token_calls.append(True)
            return "FAKE_ACCESS_TOKEN_12345"

        with self.assertRaises(YouTubePrivateError):
            self.upload(backend, token_provider=token_provider)
        self.assertEqual(backend.calls, before_calls)
        self.assertEqual(token_calls, [])

    def test_untrusted_upload_session_hostname_rejected(self):
        for url in (
            "http://www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
            "https://attacker.example/upload/youtube/v3/videos?upload_id=x",
            "https://www.googleapis.com.evil.test/upload/youtube/v3/videos?upload_id=x",
            "https://user:pass@www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
            "https://www.googleapis.com/youtube/v3/videos?upload_id=x",
        ):
            with self.subTest(url=url), self.assertRaises(YouTubePrivateError):
                _safe_session_url(url)

    def test_resumable_range_rejected_when_nonmonotonic_or_invalid(self):
        with self.assertRaises(YouTubePrivateError):
            _offset(308, {"range": "bytes=100-500"}, b"", total=1000)
        with self.assertRaises(YouTubePrivateError):
            _offset(308, {"range": "bytes=0-999"}, b"", total=1000)
        self.assertEqual(_offset(308, {}, b"", total=1000), (0, None))

    def test_resumable_range_with_oversized_integer_is_a_safe_error(self):
        header = "bytes=0-" + ("9" * 5000)
        with self.assertRaises(YouTubePrivateError):
            _offset(308, {"range": header}, b"", total=1000)

    def test_private_oauth_file_permissions_enforced(self):
        oauth = self.root / "oauth.json"
        oauth.write_text(json.dumps({
            "client_id": "SYNTHETIC_CLIENT_ID",
            "client_secret": "SYNTHETIC_CLIENT_SECRET",
            "refresh_token": "SYNTHETIC_REFRESH_TOKEN",
        }))
        oauth.chmod(0o600)
        creds = load_private_oauth(str(oauth))
        self.assertEqual(creds["client_id"], "SYNTHETIC_CLIENT_ID")
        oauth.chmod(0o644)
        with self.assertRaises(ValueError):
            load_private_oauth(str(oauth))

    def test_private_oauth_refresh_cache(self):
        class FakeRefresh:
            def __init__(self):
                self.calls = 0
            def refresh(self, client_id, client_secret, refresh_token):
                self.calls += 1
                return "FAKE_ACCESS_TOKEN_12345", 3600
        transport = FakeRefresh()
        provider = TokenProvider({
            "client_id": "testclient",
            "client_secret": "testsecret",
            "refresh_token": "testrefresh",
        }, transport)
        self.assertEqual(provider(), provider())
        self.assertEqual(transport.calls, 1)

    def test_cli_no_execute_does_not_touch_oauth_or_video(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main([
                "--private-root", "/not/existing",
                "--relative-path", "episode.mp4",
                "--expected-sha256", "0" * 64,
                "--episode-id", "colors", "--title", "Colors",
                "--journal", str(self.journal),
                "--oauth-json", "/no/credential/file",
            ])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "NOT_EXECUTED")
        self.assertFalse(self.journal.exists())

    def test_cli_explicit_but_missing_credentials_redacted(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main([
                "--private-root", str(self.root),
                "--relative-path", "episode.mp4",
                "--expected-sha256", self.sha,
                "--episode-id", "colors", "--title", "Colors",
                "--journal", str(self.journal),
                "--oauth-json", "/no/credential/file",
                "--execute-private-upload", "--owner-authorized",
                "--confirm-made-for-kids",
            ])
        self.assertEqual(status, 2)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
