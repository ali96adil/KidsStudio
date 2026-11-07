"""Opt-in one-shot Mac-to-Pi transfer over authenticated SSH.

Local video bytes are streamed as SSH stdin to an installed Pi receiver.
No password prompting, auto discovery, queue mutation or YouTube API calls.
The receiver writes an atomic owner-private inbox file after SHA verification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
from typing import Any, Callable

from .optional_tool_evidence import ToolEvidenceError, private_evidence_file
from .pi_transfer_receive import _NAME, _SHA
from .transfer_verify import verify_staged_file

_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
_USER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_PYTHON = re.compile(r"(?:python3|/[A-Za-z0-9_./-]+)\Z")
_MAX_BYTES = 20 * 1024**3
_MAX_REPORT = 8192


class MacPiTransferError(ValueError):
    """Explicit SSH transfer was blocked or receiver response invalid."""


def _validate_options(*, host: str, user: str, port: int, remote_python: str) -> None:
    if (not isinstance(host, str) or not _HOST.fullmatch(host)
            or ".." in host or host.startswith("-") or host.endswith(".")
            or not isinstance(user, str) or not _USER.fullmatch(user)):
        raise MacPiTransferError("Invalid Pi SSH destination.")
    if type(port) is not int or not 1 <= port <= 65535:
        raise MacPiTransferError("Invalid Pi SSH port.")
    if (not isinstance(remote_python, str)
            or not _PYTHON.fullmatch(remote_python)
            or ".." in Path(remote_python).parts):
        raise MacPiTransferError("Invalid remote Python executable.")


def make_transfer_plan(
    *, video_root: str, relative_path: str, expected_sha256: str,
    destination_name: str, pi_host: str, pi_user: str,
    ssh_port: int = 22, remote_python: str = "python3",
) -> tuple[dict, Path]:
    _validate_options(host=pi_host, user=pi_user, port=ssh_port,
                      remote_python=remote_python)
    if (not isinstance(destination_name, str)
            or not _NAME.fullmatch(destination_name)
            or not isinstance(relative_path, str)
            or not relative_path.lower().endswith(".mp4")
            or not isinstance(expected_sha256, str)
            or not _SHA.fullmatch(expected_sha256)):
        raise MacPiTransferError("Invalid MP4 destination or trusted digest.")
    source = private_evidence_file(video_root, relative_path, max_bytes=_MAX_BYTES)
    checked = verify_staged_file(
        root=video_root, relative_path=relative_path,
        expected_sha256=expected_sha256, max_bytes=_MAX_BYTES)
    if checked["status"] != "VERIFIED" or checked["bytes"] == 0:
        raise MacPiTransferError("Local source MP4 did not pass SHA verification.")
    return ({
        "schema_version": 1,
        "status": "MAC_PI_TRANSFER_PREVIEW_ONLY",
        "destination_name": destination_name,
        "pi_host": pi_host,
        "pi_ssh_port": ssh_port,
        "sha256": checked["sha256"],
        "bytes": checked["bytes"],
        "source_verified_at_check_time": True,
        "ssh_connection_performed": False,
        "youtube_upload_submitted": False,
        "publication_approved": False,
    }, source)


def transfer_private_video(
    *, video_root: str, relative_path: str, expected_sha256: str,
    destination_name: str, pi_host: str, pi_user: str,
    ssh_port: int = 22, remote_python: str = "python3",
    execute: bool = False, timeout_seconds: int = 3600,
    runner: Callable[..., Any] = subprocess.run,
) -> dict:
    preview, source = make_transfer_plan(
        video_root=video_root, relative_path=relative_path,
        expected_sha256=expected_sha256, destination_name=destination_name,
        pi_host=pi_host, pi_user=pi_user, ssh_port=ssh_port,
        remote_python=remote_python)
    if execute is not True:
        return preview
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 7200:
        raise MacPiTransferError("Invalid SSH transfer timeout.")
    command = [
        remote_python, "-m", "kidsstudio.pi_transfer_receive",
        "--destination-name", destination_name,
        "--expected-sha256", preview["sha256"],
        "--expected-bytes", str(preview["bytes"]),
    ]
    args = [
        "ssh", "-T",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ClearAllForwardings=yes",
        "-o", "ForwardAgent=no",
        "-o", "PermitLocalCommand=no",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=2",
        "-p", str(ssh_port),
        f"{pi_user}@{pi_host}", shlex.join(command),
    ]
    # Remote output is captured to an anonymous bounded temporary file rather
    # than materialized in RAM. SSH diagnostics are never echoed to callers.
    with source.open("rb") as video, tempfile.TemporaryFile(mode="w+b") as output:
        info = os.fstat(video.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size != preview["bytes"]
                or info.st_mode & 0o077):
            raise MacPiTransferError("Source file changed before SSH transfer.")
        try:
            result = runner(
                args, stdin=video, stdout=output, stderr=subprocess.DEVNULL,
                timeout=timeout_seconds, check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise MacPiTransferError("SSH video transfer failed or timed out.") from exc
        if getattr(result, "returncode", None) != 0:
            raise MacPiTransferError("Pi receiver rejected transfer; inspect Pi privately.")
        if output.tell() > _MAX_REPORT:
            raise MacPiTransferError("Pi receiver returned oversized receipt.")
        output.seek(0)
        try:
            remote = json.loads(output.read(_MAX_REPORT + 1))
        except (ValueError, UnicodeError) as exc:
            raise MacPiTransferError("Pi receiver returned malformed receipt.") from exc
    # Even a valid remote receipt cannot override a changed local source.
    final = verify_staged_file(
        root=video_root, relative_path=relative_path,
        expected_sha256=expected_sha256, max_bytes=_MAX_BYTES)
    if final["status"] != "VERIFIED" or final["bytes"] != preview["bytes"]:
        raise MacPiTransferError("Local video changed during transfer.")
    if (not isinstance(remote, dict)
            or type(remote.get("schema_version")) is not int
            or remote["schema_version"] != 1
            or remote.get("private_inbox_verified_at_receive") is not True
            or remote.get("status") not in {
                "PI_INBOX_RECEIVED_PRIVATE", "PI_INBOX_ALREADY_VERIFIED"
            }
            or remote.get("destination_name") != destination_name
            or remote.get("sha256") != preview["sha256"]
            or type(remote.get("bytes")) is not int
            or remote["bytes"] != preview["bytes"]
            or remote.get("publication_approved") is not False
            or remote.get("upload_submitted") is not False):
        raise MacPiTransferError("Pi receiver receipt contradicts requested private file.")
    return {
        "schema_version": 1,
        "status": "MAC_PI_PRIVATE_TRANSFER_VERIFIED",
        "pi_receiver_status": remote["status"],
        "destination_name": destination_name,
        "sha256": preview["sha256"],
        "bytes": preview["bytes"],
        "ssh_connection_performed": True,
        "remote_receipt_checked": True,
        "youtube_upload_submitted": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in Mac SSH stream to the Pi private inbox")
    parser.add_argument("--video-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--destination-name", required=True)
    parser.add_argument("--pi-host", required=True)
    parser.add_argument("--pi-user", required=True)
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--remote-python", default="python3")
    parser.add_argument("--execute-transfer", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = transfer_private_video(
            video_root=args.video_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256,
            destination_name=args.destination_name,
            pi_host=args.pi_host, pi_user=args.pi_user,
            ssh_port=args.ssh_port, remote_python=args.remote_python,
            execute=args.execute_transfer)
    except (ToolEvidenceError, MacPiTransferError, ValueError, OSError):
        print(json.dumps({
            "status": "MAC_PI_TRANSFER_BLOCKED_OR_UNCERTAIN",
            "youtube_upload_submitted": False, "publication_approved": False
        }))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "MAC_PI_PRIVATE_TRANSFER_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
