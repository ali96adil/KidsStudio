"""CI-only complete private handoff for an actually FFmpeg-encoded colors MP4.

Real: SHA, MP4 playback check, source evidence writer, review-note writer,
reviewed Mac->Pi handoff logic, Pi atomic receiver and uploader journal/chunks.
SIMULATED: owner viewing/listening (CI CANNOT REVIEW CONTENT), SSH transport,
Google token and PRIVATE YouTube service. No real account, Pi, DNS or network.
All files stay in one ephemeral 0700 working directory; never artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import types
from unittest.mock import patch

from kidsstudio.mac_pilot_evidence import (
    collect_mac_pilot_evidence, record_mac_pilot_review,
)
from kidsstudio.pi_transfer_receive import receive_private_video
from kidsstudio.reviewed_mac_pi_handoff import (
    MacPiReviewGateError, transfer_reviewed_mac_pilot,
)
from kidsstudio.transfer_verify import verify_staged_file
from kidsstudio.pi_youtube_private_upload import (
    YouTubePrivateError, execute_private_upload, _load_journal,
)


_SESSION = ("https://www.googleapis.com/upload/youtube/v3/videos?"
            "uploadType=resumable&upload_id=CI_ONLY_SYNTHETIC_VIDEO")
_FAKE_VIDEO_ID = "ciVideo-001"


class OfflineMockSSH:
    """Runs the actual Pi stdin receiver in-process, never starts SSH."""
    def __init__(self, pi_inbox: Path):
        self.pi_inbox = pi_inbox
        self.calls = 0

    def __call__(self, argv, **kwargs):
        if (argv[:2] != ["ssh", "-T"] or "StrictHostKeyChecking=yes" not in argv
                or "BatchMode=yes" not in argv
                or kwargs["check"] is not False):
            raise AssertionError("Unexpected Mac->Pi private SSH requirements.")
        self.calls += 1
        remote = shlex.split(argv[-1])
        if remote[:3] != ["python3", "-m", "kidsstudio.pi_transfer_receive"]:
            raise AssertionError("Unexpected destination or remote program.")
        def val(flag):
            return remote[remote.index(flag) + 1]
        report = receive_private_video(
            destination_root=self.pi_inbox,
            destination_name=val("--destination-name"),
            expected_sha256=val("--expected-sha256"),
            expected_bytes=int(val("--expected-bytes")),
            source=kwargs["stdin"])
        kwargs["stdout"].write(json.dumps(report).encode("utf8"))
        return types.SimpleNamespace(returncode=0)


class OfflineFakeYouTube:
    """Only an in-memory private resumable upload model; no HTTP calls."""
    def __init__(self):
        self.started = 0
        self.ack = 0
        self.total = None
        self.metadata = None
        self.confirmations = 0

    def start(self, *, token, metadata, size):
        if token != "CI_ONLY_ACCESS_TOKEN_123456789":
            raise AssertionError("Unexpected fake token.")
        self.started += 1
        self.total = size
        self.metadata = metadata
        if (metadata["status"]["privacyStatus"] != "private"
                or metadata["status"]["selfDeclaredMadeForKids"] is not True
                or "publishAt" in metadata["status"]):
            raise AssertionError("CI metadata must never request public publication.")
        return _SESSION

    def probe(self, *, session, token, size):
        if session != _SESSION or size != self.total:
            raise AssertionError("Wrong fake upload session.")
        return (308, {"range": f"bytes=0-{self.ack-1}"} if self.ack else {}, b"")

    def send_chunk(self, *, session, token, data, start, total):
        if (session != _SESSION or start != self.ack or total != self.total
                or not data):
            raise AssertionError("Synthetic upload chunk mismatch.")
        self.ack += len(data)
        if self.ack >= self.total:
            return 201, {}, json.dumps({
                "id": _FAKE_VIDEO_ID,
                "status": {"privacyStatus": "private"},
            }).encode()
        return 308, {"range": f"bytes=0-{self.ack-1}"}, b""

    def video_status(self, *, token, video_id):
        if video_id != _FAKE_VIDEO_ID:
            raise AssertionError("Unexpected fake video id.")
        self.confirmations += 1
        return {"privacyStatus": "private"}


def check_offline_full_private_chain(
    *, base: Path, ready: Path, video_name: str, expected_sha256: str,
) -> dict:
    """Run complete same-byte private chain; never authorize real transfer."""
    base = base.resolve(strict=True)
    ready = ready.resolve(strict=True)
    if not ready.is_relative_to(base):
        raise ValueError("Real CI video must belong to the private test root.")
    proof = base / "mock-owner-proof"
    inbox = base / "mock-pi-inbox"
    journal_root = base / "mock-pi-journal"
    for directory in (proof, inbox, journal_root):
        directory.mkdir(mode=0o700)
    evidence_name = video_name.removesuffix(".mp4") + ".evidence.json"

    # Simulate only platform identity + Git checkout qualification. The
    # independently executed MP4 playback/sha check remains FULLY REAL.
    fake_host = {
        "status": "SUPERVISED_TESTS_READY",
        "host_system": "Darwin",
        "source_commit": "b" * 40,
        "source_checkout_clean": True,
        "synthetic_review_pipeline": "OFFLINE_REVIEW_PIPELINE_PASS",
    }
    with patch("kidsstudio.mac_pilot_evidence.platform.system",
               return_value="Darwin"), patch(
                   "kidsstudio.mac_pilot_evidence.qualify_host",
                   return_value=fake_host):
        collected = collect_mac_pilot_evidence(
            episode_id="colors_ar_01", video_root=str(ready),
            video_name=video_name, expected_sha256=expected_sha256,
            evidence_root=str(proof), evidence_name=evidence_name,
        )
    if collected["status"] != "MAC_PILOT_EVIDENCE_RECORDED_REVIEW_PENDING":
        raise AssertionError("Cannot create technical proof for real synthetic MP4.")
    ssh = OfflineMockSSH(inbox)
    args = dict(
        video_root=str(ready), evidence_root=str(proof),
        evidence_name=evidence_name,
        pi_host="mock-pi.local", pi_user="ciuser", runner=ssh,
    )
    try:
        transfer_reviewed_mac_pilot(**args, execute=True)
    except MacPiReviewGateError:
        pass
    else:
        raise AssertionError("Unreviewed synthetic video should never transfer.")
    if ssh.calls != 0:
        raise AssertionError("Review gate made an SSH call before approval.")
    # THIS IS A TEST FIXTURE, NOT AN ACTUAL OWNER: fake assertions are
    # explicitly confined to the CI temporary directory and are deleted.
    review = record_mac_pilot_review(
        evidence_root=str(proof), evidence_name=evidence_name,
        video_root=str(ready), video_name=video_name,
        expected_sha256=expected_sha256, review_outcome="ACCEPTED_PRIVATE",
        reviewer_notes="CI SIMULATED APPROVAL ONLY -- NO PERSON WATCHED THIS",
        reviewed_full_video=True, reviewed_arabic_voice=True,
    )
    if review["review_outcome"] != "ACCEPTED_PRIVATE":
        raise AssertionError("Synthetic review fixture failed.")
    preview = transfer_reviewed_mac_pilot(**args)
    if (preview["status"] != "MAC_PI_REVIEWED_TRANSFER_PREVIEW_ONLY"
            or preview["ssh_connection_performed"] is not False
            or ssh.calls != 0):
        raise AssertionError("Offline transfer preview unexpectedly connected.")
    received = transfer_reviewed_mac_pilot(**args, execute=True)
    if (received["status"] != "MAC_PI_REVIEWED_PRIVATE_TRANSFER_VERIFIED"
            or ssh.calls != 1):
        raise AssertionError("Mock SSH receiver failed exact SHA handoff.")
    stored = verify_staged_file(
        root=str(inbox), relative_path=video_name,
        expected_sha256=expected_sha256)
    if stored["status"] != "VERIFIED" or stored["bytes"] != received["bytes"]:
        raise AssertionError("Pi inbox bytes do not match reviewed Mac video.")

    # Explicit upload authorization here is ONLY a CI TEST FIXTURE:
    # fake Google token, service, video ID and no actual network capability.
    fake = OfflineFakeYouTube()
    record = journal_root / "private-test-state.json"
    token = lambda: "CI_ONLY_ACCESS_TOKEN_123456789"
    with patch("kidsstudio.pi_youtube_private_upload.HTTPSYouTubeTransport",
               side_effect=AssertionError("Never instantiate real network transport.")):
        uploaded = execute_private_upload(
            private_root=str(inbox), relative_path=video_name,
            expected_sha256=expected_sha256,
            episode_id="colors_ar_01", title="CI synthetic colors sample",
            description="CI test only; no human voice", language="ar",
            journal_file=str(record), owner_authorized=True,
            made_for_kids_confirmed=True, transport=fake,
            token_provider=token)
    if (uploaded["status"] != "PRIVATE_UPLOAD_CONFIRMED"
            or uploaded["video_id"] != _FAKE_VIDEO_ID
            or fake.started != 1 or fake.ack != stored["bytes"]
            or fake.confirmations != 1 or
            uploaded["publication_approved"] is not False):
        raise AssertionError("Simulated private upload chain failed.")
    journal = _load_journal(record)
    if (journal["state"] != "PRIVATE_UPLOAD_CONFIRMED"
            or journal["media_sha256"] != expected_sha256
            or journal.get("session_url")):
        raise AssertionError("Synthetic upload journal incorrect or not finalized.")
    return {
        "status": "OFFLINE_REAL_MP4_TO_FAKE_PI_TO_FAKE_YOUTUBE_PRIVATE_PASSED",
        "real_mp4_sha256_matched_on_both_local_hosts": True,
        "real_media_bytes_passed_to_actual_pi_receiver_code": True,
        "real_private_upload_chunk_and_journal_logic_exercised": True,
        "simulated_owner_review_only_no_human_review": True,
        "mock_ssh_no_network": True,
        "mock_google_no_network_no_oauth": True,
        "youtube_video_id_is_fake": True,
        "actual_pi_tested": False,
        "actual_youtube_upload_performed": False,
        "owner_publication_approved": False,
    }
