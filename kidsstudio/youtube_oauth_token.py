"""Refresh a local YouTube OAuth access token without storing it in source code.

Requires a pre-authorized refresh token; this module does not initiate OAuth
consent and never calls YouTube publishing endpoints.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
MAX_TOKEN_RESPONSE = 16 * 1024

class OAuthTokenError(RuntimeError):
    pass

def parse_token_response(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise OAuthTokenError("invalid OAuth response")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise OAuthTokenError("OAuth access token missing")
    if payload.get("token_type", "Bearer").lower() != "bearer":
        raise OAuthTokenError("unexpected token type")
    return token

def refresh_access_token(client_id: str, client_secret: str, refresh_token: str, *, timeout: float = 10) -> str:
    for name, value in (("client_id", client_id), ("client_secret", client_secret), ("refresh_token", refresh_token)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " required")
    data = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_TOKEN_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise OAuthTokenError("OAuth refresh failed") from exc
    if len(raw) > MAX_TOKEN_RESPONSE:
        raise OAuthTokenError("OAuth response too large")
    try:
        return parse_token_response(json.loads(raw))
    except (ValueError, UnicodeDecodeError, AttributeError) as exc:
        raise OAuthTokenError("invalid OAuth JSON") from exc
