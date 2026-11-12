"""Explicit operator-controlled, resumable YouTube PRIVATE uploader for Pi.

No ambient daemon, no auto retry after ambiguous initiation, no public API,
no source modifications. Network is possible ONLY via --execute-private-upload.
A local CLI flag is an operator assertion, NOT authenticated owner identity.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import tempfile
import time
from typing import Callable
from urllib.parse import urlencode, urlsplit
from .optional_tool_evidence import ToolEvidenceError, private_evidence_file, read_private_json
from .youtube_private_dry_run import build_private_upload_dry_run
from .transfer_verify import verify_staged_file


_CHUNK = 1024 * 1024
_MAX_RESPONSE = 128 * 1024
_SESSION_HOSTS = frozenset({"www.googleapis.com", "upload.googleapis.com"})
_VIDEO_ID = re.compile(r"^[a-zA-Z0-9_-]{8,32}$")
_RANGE = re.compile(r"^bytes=0-(\d+)$")
_INIT_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos?"
    "uploadType=resumable&part=snippet%2Cstatus&notifySubscribers=false"
)
_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubePrivateError(ValueError):
    """No remote/private request body or credential is included in this exception."""


def _safe_session_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 4096:
        raise YouTubePrivateError("Invalid resumable session.")
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname not in _SESSION_HOSTS
                or p.port not in (None, 443) or p.username or p.password
                or p.fragment or not p.path.startswith("/upload/youtube/v3/videos")
                or "upload_id=" not in p.query):
            raise YouTubePrivateError("Untrusted resumable session endpoint.")
    except ValueError as exc:
        raise YouTubePrivateError("Untrusted resumable session endpoint.") from exc
    return url


def _private_journal_path(filename: str) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(filename)))
    parent = path.parent
    if path.suffix != ".json" or any(p.is_symlink() for p in (path, *path.parents)):
        raise YouTubePrivateError("Private journal must be real .json file.")
    if any((p / ".git").exists() for p in (parent, *parent.parents)):
        raise YouTubePrivateError("Journal must be outside Git.")
    if not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise YouTubePrivateError("Private journal parent (0700) required.")
    if os.name == "posix" and parent.stat().st_uid != os.getuid():
        raise YouTubePrivateError("Private journal owner mismatch.")
    if path.exists():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or (os.name == "posix" and info.st_uid != os.getuid())):
            raise YouTubePrivateError("Existing upload journal must be owner-private.")
    return path


@contextmanager
def _journal_lock(path: Path):
    lock = path.with_name(path.name + ".lock")
    if lock.is_symlink():
        raise YouTubePrivateError("Journal lock is a symlink.")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise YouTubePrivateError("Private journal lock required.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise YouTubePrivateError("Concurrent upload for this journal blocked.") from exc
        yield
    finally:
        os.close(fd)


def _save_journal(path: Path, data: dict, *, create: bool = False) -> None:
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > 16_384:
        raise YouTubePrivateError("Journal too large.")
    if create:
        fd = os.open(
            path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        if not path.exists() or path.is_symlink():
            raise YouTubePrivateError("Journal vanished or changed.")
        fd, tempname = tempfile.mkstemp(prefix=".youtube-state-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tempname, path)
        finally:
            if os.path.exists(tempname):
                os.unlink(tempname)
    dirfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def _load_journal(path: Path) -> dict:
    return read_private_json(str(path.parent), path.name)


def _expect_token(token: str) -> str:
    if (not isinstance(token, str) or not 12 <= len(token) <= 4096
            or any(c in token for c in "\r\n\t ")):
        raise YouTubePrivateError("Invalid OAuth access token.")
    return token


class HTTPSYouTubeTransport:
    """Only fixed Google HTTPS destinations; redirects are never followed."""
    def __init__(self, *, timeout: int = 75):
        self.timeout = timeout

    def _request(self, url: str, method: str, headers: dict,
                 data: bytes = b"") -> tuple[int, dict, bytes]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.port not in (None, 443):
            raise YouTubePrivateError("HTTPS Google endpoint required.")
        if parsed.hostname not in _SESSION_HOSTS | {"oauth2.googleapis.com"}:
            raise YouTubePrivateError("Non-Google upload endpoint refused.")
        connection = http.client.HTTPSConnection(
            parsed.hostname, timeout=self.timeout,
            context=ssl.create_default_context())
        try:
            target = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.request(method, target, body=data, headers=headers)
            response = connection.getresponse()
            if response.length is not None and response.length > _MAX_RESPONSE:
                raise YouTubePrivateError("Oversized Google API response.")
            body = response.read(_MAX_RESPONSE + 1)
            if len(body) > _MAX_RESPONSE:
                raise YouTubePrivateError("Oversized Google API response.")
            return response.status, {k.lower(): v for k, v in response.getheaders()}, body
        finally:
            connection.close()

    def refresh(self, client_id: str, client_secret: str, refresh_token: str) -> tuple[str, int]:
        payload = urlencode({
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        }).encode("ascii")
        code, _, body = self._request(
            "https://oauth2.googleapis.com/token", "POST",
            {"Content-Type": "application/x-www-form-urlencoded",
             "Content-Length": str(len(payload))}, payload)
        if code != 200:
            raise YouTubePrivateError("OAuth refresh refused; inspect Google account settings.")
        try:
            result = json.loads(body)
            token = _expect_token(result["access_token"])
            ttl = int(result["expires_in"])
            if not 120 <= ttl <= 86400:
                raise ValueError("Invalid TTL")
        except (ValueError, KeyError, TypeError) as exc:
            raise YouTubePrivateError("OAuth refresh response malformed.") from exc
        return token, ttl

    def start(self, *, token: str, metadata: dict, size: int) -> str:
        payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        code, headers, _ = self._request(_INIT_URL, "POST", {
            "Authorization": "Bearer " + _expect_token(token),
            "Content-Type": "application/json; charset=UTF-8",
            "Content-Length": str(len(payload)),
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        }, payload)
        if code != 200:
            raise YouTubePrivateError("YouTube session initiation failed.")
        return _safe_session_url(headers.get("location", ""))

    def probe(self, *, session: str, token: str, size: int) -> tuple[int, dict, bytes]:
        return self._request(_safe_session_url(session), "PUT", {
            "Authorization": "Bearer " + _expect_token(token),
            "Content-Length": "0",
            "Content-Range": f"bytes */{size}",
        })

    def send_chunk(self, *, session: str, token: str, data: bytes,
                   start: int, total: int) -> tuple[int, dict, bytes]:
        if not data or len(data) > _CHUNK or not 0 <= start < total:
            raise YouTubePrivateError("Invalid upload chunk.")
        end = start + len(data) - 1
        if end >= total:
            raise YouTubePrivateError("Chunk exceeds media length.")
        return self._request(_safe_session_url(session), "PUT", {
            "Authorization": "Bearer " + _expect_token(token),
            "Content-Type": "video/mp4",
            "Content-Length": str(len(data)),
            "Content-Range": f"bytes {start}-{end}/{total}",
        }, data)

    def video_status(self, *, token: str, video_id: str) -> dict:
        if not _VIDEO_ID.fullmatch(video_id):
            raise YouTubePrivateError("Invalid YouTube video id.")
        code, _, raw = self._request(
            _VIDEO_URL + "?part=status&id=" + video_id, "GET",
            {"Authorization": "Bearer " + _expect_token(token)})
        if code != 200:
            raise YouTubePrivateError("Remote private-visibility verification failed.")
        try:
            data = json.loads(raw)
            items = data["items"]
            if not isinstance(items, list) or len(items) != 1 or items[0]["id"] != video_id:
                raise ValueError("Unexpected video")
            status = items[0]["status"]
            if not isinstance(status, dict):
                raise ValueError("Unexpected status")
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise YouTubePrivateError("Unverified remote video status.") from exc
        return status


class TokenProvider:
    def __init__(self, credentials: dict, transport: HTTPSYouTubeTransport):
        self.credentials = credentials
        self.transport = transport
        self.token: str | None = None
        self.expires_at = 0.0

    def __call__(self) -> str:
        if self.token is None or time.monotonic() >= self.expires_at - 90:
            self.token, ttl = self.transport.refresh(
                self.credentials["client_id"],
                self.credentials["client_secret"],
                self.credentials["refresh_token"])
            self.expires_at = time.monotonic() + ttl
        return self.token


def load_private_oauth(path: str) -> dict:
    file = Path(os.path.abspath(os.path.expanduser(path)))
    data = read_private_json(str(file.parent), file.name)
    if set(data) != {"client_id", "client_secret", "refresh_token"}:
        raise YouTubePrivateError("Expected existing owner-authorized OAuth credentials.")
    if not all(isinstance(x, str) and 12 <= len(x) <= 4096
               and "\n" not in x and "\r" not in x for x in data.values()):
        raise YouTubePrivateError("Malformed OAuth credentials.")
    return data


def _offset(code: int, headers: dict, body: bytes, *, total: int) -> tuple[int | None, str | None]:
    if code in (200, 201):
        try:
            parsed = json.loads(body)
            video_id = parsed["id"]
            status = parsed["status"]
            if not isinstance(video_id, str) or not _VIDEO_ID.fullmatch(video_id):
                raise ValueError("Video id missing")
            if not isinstance(status, dict) or status.get("privacyStatus") != "private":
                raise ValueError("Video status not private")
        except (ValueError, KeyError, TypeError) as exc:
            raise YouTubePrivateError("Upload completed without confirmed PRIVATE status.") from exc
        return None, video_id
    if code == 308:
        range_header = headers.get("range")
        if range_header is None:
            return 0, None
        matched = _RANGE.fullmatch(range_header)
        if not matched:
            raise YouTubePrivateError("Invalid remote upload byte range.")
        offset = int(matched.group(1)) + 1
        if offset >= total:
            raise YouTubePrivateError("Remote upload range is inconsistent.")
        return offset, None
    raise YouTubePrivateError("YouTube resumable operation not confirmed.")


def _fingerprint(*, episode_id: str, sha: str, size: int,
                 title: str, description: str, language: str) -> str:
    return hashlib.sha256(json.dumps({
        "episode": episode_id, "sha256": sha, "size": size, "title": title,
        "description": description, "language": language,
        "privacy": "private", "made_for_kids": True,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def execute_private_upload(
    *, private_root: str, relative_path: str, expected_sha256: str,
    episode_id: str, title: str, description: str, language: str,
    journal_file: str, owner_authorized: bool, made_for_kids_confirmed: bool,
    transport: HTTPSYouTubeTransport | None = None,
    token_provider: Callable[[], str] | None = None,
    max_chunks_per_run: int = 4096,
) -> dict:
    """One foreground, explicitly authorized upload or safe resume."""
    if owner_authorized is not True or made_for_kids_confirmed is not True:
        raise YouTubePrivateError("Explicit private upload and kids-audience confirmation required.")
    if type(max_chunks_per_run) is not int or not 1 <= max_chunks_per_run <= 65536:
        raise YouTubePrivateError("Invalid chunk limit.")
    preview = build_private_upload_dry_run(
        private_root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256, episode_id=episode_id,
        title=title, description=description, language=language,
        owner_private_upload_authorized=True)
    if preview["status"] != "DRY_RUN_READY":
        raise YouTubePrivateError("Video integrity and private handoff gate not passed.")
    file = private_evidence_file(private_root, relative_path, max_bytes=20 * 1024**3)
    total = preview["artifact_bytes"]
    if not total:
        raise YouTubePrivateError("Empty media file cannot be uploaded.")
    journal_path = _private_journal_path(journal_file)
    fingerprint = _fingerprint(
        episode_id=episode_id, sha=preview["artifact_sha256"], size=total,
        title=title, description=description, language=language)
    backend = transport or HTTPSYouTubeTransport()
    if token_provider is None:
        raise YouTubePrivateError("Explicit OAuth token provider is required.")
    with _journal_lock(journal_path):
        if journal_path.exists():
            record = _load_journal(journal_path)
            state = record.get("state")
            if (record.get("schema_version") != 1
                    or record.get("intent_sha256") != fingerprint
                    or record.get("media_sha256") != preview["artifact_sha256"]
                    or type(record.get("media_bytes")) is not int
                    or record.get("media_bytes") != total
                    or record.get("media_name") != relative_path
                    or record.get("episode_id") != episode_id
                    or (state in {"PRIVATE_UPLOAD_CONFIRMED", "REMOTE_COMPLETED_UNVERIFIED"}
                        and (not isinstance(record.get("video_id"), str)
                             or not _VIDEO_ID.fullmatch(record["video_id"])
                             or "session_url" in record))
                    or (state == "SESSION_ACTIVE" and "video_id" in record)):
                raise YouTubePrivateError("Upload journal is not for this exact immutable request.")
            if state == "PRIVATE_UPLOAD_CONFIRMED":
                # A persisted confirmation is historical evidence only: check
                # the current remote visibility before reporting it again.
                remote = backend.video_status(
                    token=token_provider(), video_id=record["video_id"])
                if remote.get("privacyStatus") != "private":
                    raise YouTubePrivateError("Previously private video is not private now.")
                return {
                    "status": "PRIVATE_UPLOAD_CONFIRMED", "video_id": record["video_id"],
                    "publication_approved": False, "upload_submitted": True,
                    "from_existing_journal": True,
                }
            if state not in {"SESSION_ACTIVE", "REMOTE_COMPLETED_UNVERIFIED"}:
                raise YouTubePrivateError("Ambiguous pre-session journal: do not restart upload automatically.")
            if state == "REMOTE_COMPLETED_UNVERIFIED":
                remote = backend.video_status(
                    token=token_provider(), video_id=record["video_id"])
                if remote.get("privacyStatus") != "private":
                    raise YouTubePrivateError("YouTube did not confirm private visibility.")
                record["state"] = "PRIVATE_UPLOAD_CONFIRMED"
                _save_journal(journal_path, record)
                return {"status": record["state"], "video_id": record["video_id"],
                        "upload_submitted": True, "publication_approved": False}
        else:
            # Persist operator intent BEFORE requesting any new session.
            record = {"schema_version": 1, "intent_sha256": fingerprint,
                      "state": "INITIATION_UNCERTAIN",
                      "media_sha256": preview["artifact_sha256"],
                      "media_bytes": total,
                      # Non-sensitive exact content/version anchors for the
                      # offline post-PRIVATE owner review on this Pi.
                      "media_name": relative_path,
                      "episode_id": episode_id}
            # Refreshing OAuth cannot itself create a video. Do it before
            # persisting the upload-initiation uncertainty journal, so an
            # invalid/expired refresh token does not block a never-started upload.
            first_token = token_provider()
            _save_journal(journal_path, record, create=True)
            session = backend.start(
                token=first_token,
                metadata=preview["youtube_request_preview"],
                size=total)
            record["state"] = "SESSION_ACTIVE"
            record["session_url"] = _safe_session_url(session)
            _save_journal(journal_path, record)
        session = _safe_session_url(record["session_url"])

        def finish(video_id: str) -> dict:
            # On failed verification, preserve a durable video ID for later
            # investigation; never create a second upload.
            record["state"] = "REMOTE_COMPLETED_UNVERIFIED"
            record["video_id"] = video_id
            record.pop("session_url", None)
            _save_journal(journal_path, record)
            check = verify_staged_file(
                root=private_root, relative_path=relative_path,
                expected_sha256=expected_sha256)
            if check["status"] != "VERIFIED":
                raise YouTubePrivateError("Local video changed during upload.")
            remote = backend.video_status(token=token_provider(), video_id=video_id)
            if remote.get("privacyStatus") != "private":
                raise YouTubePrivateError("YouTube returned non-private video status.")
            record["state"] = "PRIVATE_UPLOAD_CONFIRMED"
            _save_journal(journal_path, record)
            return {
                "status": "PRIVATE_UPLOAD_CONFIRMED", "video_id": video_id,
                "upload_submitted": True, "publication_approved": False,
            }

        # Always query the real session on every invocation, even after
        # uncertain network failures. No session means no automatic restart.
        offset, finished_id = _offset(
            *backend.probe(session=session, token=token_provider(), size=total),
            total=total)
        if finished_id:
            return finish(finished_id)
        with file.open("rb") as media:
            # Fail if an attacker/user swapped the file after checksum validation.
            info = os.fstat(media.fileno())
            if info.st_size != total or not stat.S_ISREG(info.st_mode):
                raise YouTubePrivateError("Media changed before chunk streaming.")
            for _ in range(max_chunks_per_run):
                if offset is None or offset >= total:
                    raise YouTubePrivateError("Remote upload offset inconsistent.")
                media.seek(offset)
                data = media.read(min(_CHUNK, total - offset))
                if not data:
                    raise YouTubePrivateError("Cannot read upload chunk.")
                code, headers, body = backend.send_chunk(
                    session=session, token=token_provider(),
                    data=data, start=offset, total=total)
                next_offset, finished_id = _offset(code, headers, body, total=total)
                if finished_id:
                    return finish(finished_id)
                if next_offset is None or next_offset <= offset:
                    raise YouTubePrivateError("Upload made no confirmed progress.")
                offset = next_offset
        return {"status": "UPLOAD_PAUSED_RESUMABLE", "bytes_remote_acknowledged": offset,
                "upload_submitted": True, "publication_approved": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Foreground YouTube PRIVATE uploader (Pi only)")
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--language", choices=["ar", "en"], default="ar")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--oauth-json", required=True)
    parser.add_argument("--execute-private-upload", action="store_true")
    parser.add_argument("--owner-authorized", action="store_true")
    parser.add_argument("--confirm-made-for-kids", action="store_true")
    parser.add_argument("--max-chunks-per-run", type=int, default=4096)
    args = parser.parse_args(argv)
    if not args.execute_private_upload:
        print(json.dumps({"status": "NOT_EXECUTED",
                          "publication_approved": False, "network_called": False}))
        return 1
    try:
        credentials = load_private_oauth(args.oauth_json)
        backend = HTTPSYouTubeTransport()
        result = execute_private_upload(
            private_root=args.private_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256, episode_id=args.episode_id,
            title=args.title, description=args.description, language=args.language,
            journal_file=args.journal,
            owner_authorized=args.owner_authorized,
            made_for_kids_confirmed=args.confirm_made_for_kids,
            max_chunks_per_run=args.max_chunks_per_run,
            transport=backend, token_provider=TokenProvider(credentials, backend))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "PRIVATE_UPLOAD_CONFIRMED" else 1
    except (YouTubePrivateError, ToolEvidenceError, ValueError, OSError,
            KeyError, TypeError, http.client.HTTPException):
        # Never leak private session URL, OAuth credentials, remote error body,
        # local video paths, title or description.
        print(json.dumps({"status": "PRIVATE_UPLOAD_BLOCKED_OR_UNCERTAIN",
                          "check_private_journal": True,
                          "publication_approved": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
