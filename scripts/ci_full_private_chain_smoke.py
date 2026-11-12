"""CI-only complete private handoff for an actually FFmpeg-encoded colors MP4.

Real: SHA, MP4 playback check, technical Mac→Pi QA-only handoff,
Pi atomic receiver, uploader journal/chunks and post-PRIVATE review note writer.
SIMULATED: Mac host identity, owner reviewing ONLY AFTER private upload,
SSH transport, Google token and PRIVATE YouTube service. No real account, Pi, DNS or network.
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
from kidsstudio.technical_mac_pi_handoff import (
    transfer_technical_private_pilot,
)
from kidsstudio.transfer_verify import verify_staged_file
from kidsstudio.pi_youtube_private_upload import (
    YouTubePrivateError, execute_private_upload, _load_journal,
)
from kidsstudio.pi_private_draft_review import (
    inspect_uploaded_private_draft, record_post_private_draft_review,
)
from kidsstudio.pi_private_draft_inbox import build_private_draft_inbox
from kidsstudio.pi_private_draft_web import render_mobile_dashboard


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
    # Legacy optional pre-review sender remains fail-closed, but it is
    # NOT the default for this owner's PRIVATE-first review workflow.
    try:
        transfer_reviewed_mac_pilot(**args, execute=True)
    except MacPiReviewGateError:
        pass
    else:
        raise AssertionError("Legacy reviewed-only path accepted no owner note.")
    if ssh.calls != 0:
        raise AssertionError("Legacy review gate called SSH before approval.")
    # Owner review is intentionally still pending. The SHA/codec/host
    # evidence alone qualifies an exact source for PRIVATE staging.
    preview = transfer_technical_private_pilot(**args)
    if (preview["status"] != "MAC_PI_QA_ONLY_TRANSFER_PREVIEW_NO_SSH"
            or preview["ssh_connection_performed"] is not False
            or preview["owner_review_pending_until_youtube_private_draft"] is not True
            or ssh.calls != 0):
        raise AssertionError("QA-only private transfer preview not offline.")
    received = transfer_technical_private_pilot(**args, execute=True)
    if (received["status"] != "MAC_PI_QA_ONLY_PRIVATE_TRANSFER_VERIFIED"
            or ssh.calls != 1):
        raise AssertionError("Mock SSH receiver failed exact SHA private handoff.")
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
    # Now show exact PRIVATE journal + Pi MP4 SHA + YouTube video ID is
    # eligible for an OFFLINE operator note; no live Google status query.
    note_dir = base / "mock-pi-owner-private-reviews"
    note_dir.mkdir(mode=0o700)
    review_args = dict(
        private_root=str(inbox), relative_path=video_name,
        expected_sha256=expected_sha256, episode_id="colors_ar_01",
        journal_file=str(record), video_id=_FAKE_VIDEO_ID,
    )
    post_private = inspect_uploaded_private_draft(**review_args)
    if (post_private["status"] != "PI_PRIVATE_DRAFT_REVIEW_ELIGIBLE_OFFLINE"
            or post_private["youtube_current_privacy_live_rechecked"] is not False):
        raise AssertionError("Post-private Pi review not SHA/video bound.")
    # Batch 64: assemble the REAL Pi inbox status from the actual uploader
    # journal and exact SHA, before any (simulated) owner review.
    inbox_params = dict(
        journal_root=str(journal_root), private_root=str(inbox),
        review_root=str(note_dir))
    before_review = build_private_draft_inbox(**inbox_params)
    if (before_review["counts"]["NEEDS_OWNER_REVIEW_PRIVATE"] != 1
            or before_review["counts"]["BLOCKED_LOCAL_EVIDENCE"] != 0
            or before_review["youtube_current_privacy_live_rechecked"] is not False):
        raise AssertionError("Fresh fake PRIVATE upload missing from local inbox.")
    # Render the same real-MP4 status using the mobile HTML page's production
    # renderer; all identifiers and review-note bodies stay local/private.
    html_before = render_mobile_dashboard(
        before_review, csrf="CI-only-long-cryptographic-frontend-nonce-001")
    if ("بانتظار المراجعة" not in html_before
            or _FAKE_VIDEO_ID in html_before
            or "youtube.com" in html_before.lower()):
        raise AssertionError("Private mobile HTML did not show pending state safely.")
    recorded = record_post_private_draft_review(
        **review_args, review_root=str(note_dir),
        review_outcome="REVISION_REQUIRED",
        reviewer_notes="CI SIMULATED ONLY — no human watched this fake video",
        reviewed_private_youtube_draft=True, save_review=True)
    saved_note = note_dir / recorded["review_evidence_name"]
    saved = json.loads(saved_note.read_text(encoding="utf-8"))
    if (recorded["status"] != "PI_PRIVATE_DRAFT_REVIEW_RECORDED"
            or saved["video_sha256"] != expected_sha256
            or saved["youtube_video_id"] != _FAKE_VIDEO_ID
            or saved["publication_approved"] is not False
            or saved_note.stat().st_mode & 0o077):
        raise AssertionError("Post-PRIVATE local review proof is not safely bound.")
    after_review = build_private_draft_inbox(**inbox_params)
    if (after_review["counts"]["REVISION_REQUIRED_PRIVATE"] != 1
            or after_review["counts"]["NEEDS_OWNER_REVIEW_PRIVATE"] != 0
            or after_review["counts"]["BLOCKED_LOCAL_EVIDENCE"] != 0
            or after_review["items"][0]["youtube_video_id"] is not None
            or after_review["publication_approved"] is not False):
        raise AssertionError("Post-private local inbox ignored a revision or leaked ID.")
    html_after = render_mobile_dashboard(
        after_review, csrf="CI-only-long-cryptographic-frontend-nonce-001")
    if ("يحتاج تعديل" not in html_after
            or recorded["review_evidence_name"] in html_after
            or _FAKE_VIDEO_ID in html_after):
        raise AssertionError("Private mobile HTML did not reflect revision safely.")
    # Legacy optional Mac note remains available, but does NOT authorize
    # upload or public release. No actual human observed the sample.
    review = record_mac_pilot_review(
        evidence_root=str(proof), evidence_name=evidence_name,
        video_root=str(ready), video_name=video_name,
        expected_sha256=expected_sha256, review_outcome="REVISION_REQUIRED",
        reviewer_notes="CI simulated post-PRIVATE draft review — NO HUMAN WATCHED",
        reviewed_full_video=False, reviewed_arabic_voice=False,
    )
    if (review["review_outcome"] != "REVISION_REQUIRED"
            or review["publication_approved"] is not False):
        raise AssertionError("Post-private synthetic review note failed.")
    return {
        "status": "OFFLINE_REAL_MP4_TO_FAKE_PI_TO_FAKE_YOUTUBE_PRIVATE_PASSED",
        "real_mp4_sha256_matched_on_both_local_hosts": True,
        "real_media_bytes_passed_to_actual_pi_receiver_code": True,
        "real_private_upload_chunk_and_journal_logic_exercised": True,
        "private_upload_happened_before_simulated_owner_review": True,
        "pi_private_draft_note_sha_video_id_bound": True,
        "pi_private_draft_inbox_pending_to_revision_verified": True,
        "mobile_private_html_pending_to_revision_verified": True,
        "human_owner_review_actually_performed": False,
        "mock_ssh_no_network": True,
        "mock_google_no_network_no_oauth": True,
        "youtube_video_id_is_fake": True,
        "actual_pi_tested": False,
        "actual_youtube_upload_performed": False,
        "owner_publication_approved": False,
    }
