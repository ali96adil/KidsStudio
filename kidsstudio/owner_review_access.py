"""Reusable request authorization primitive; LAN access remains disabled."""
from __future__ import annotations

import secrets

MIN_TOKEN_LENGTH = 32

def authorize_bearer(header: str | None, expected_token: str) -> bool:
    """Validate a high-entropy bearer token with constant-time comparison."""
    if not isinstance(expected_token, str) or len(expected_token) < MIN_TOKEN_LENGTH:
        raise ValueError("expected token is too short")
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    supplied = header[len("Bearer "):]
    if len(supplied) > 512 or len(supplied) < MIN_TOKEN_LENGTH:
        return False
    return secrets.compare_digest(supplied, expected_token)

def new_token() -> str:
    return secrets.token_urlsafe(32)
