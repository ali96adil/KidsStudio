"""Explicit, audited, zero-paid-by-default AI chat router.

Supports narrowly-scoped OpenAI-compatible /v1/chat/completions endpoints.
Credentials are read only from environment variables; never stored in Git,
job payloads or output reports. It never auto-discovers providers or costs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib import request, error

KEY = re.compile(r"^[A-Z][A-Z0-9_]{3,99}$")
ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
ROLES = frozenset({"script_draft", "editorial_review"})
MAX_CONFIG = 64_000
MAX_RESPONSE = 512_000


class AIRouterError(ValueError):
    """Local configuration error or failed chat request (no remote body leaks)."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _endpoint(url: str) -> str:
    if not isinstance(url, str):
        raise AIRouterError("Endpoint must be a URL string.")
    p = urlparse(url)
    try:
        port = p.port
    except ValueError as exc:
        raise AIRouterError("Invalid provider port.") from exc
    local = p.hostname in {"localhost", "127.0.0.1"}
    if (p.scheme != "https" and not (local and p.scheme == "http")):
        raise AIRouterError("Provider URL must be HTTPS or explicit loopback HTTP.")
    if (not p.hostname or p.username or p.password or p.fragment or p.query
            or p.path.rstrip("/") != "/v1/chat/completions"):
        raise AIRouterError("Use a direct /v1/chat/completions endpoint, no URL credentials or query.")
    if port is not None and not 1 <= port <= 65535:
        raise AIRouterError("Invalid provider port.")
    return url


class AIConfig:
    def __init__(self, path: str | Path):
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size > MAX_CONFIG:
            raise AIRouterError("Private provider config missing or too large.")
        try:
            cfg = json.loads(source.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise AIRouterError("Invalid provider JSON config.") from exc
        if not isinstance(cfg, dict) or cfg.get("schema_version") != 1:
            raise AIRouterError("Expected versioned provider configuration.")
        providers = cfg.get("providers")
        routes = cfg.get("routes")
        if not isinstance(providers, list) or not 1 <= len(providers) <= 12:
            raise AIRouterError("Configure 1–12 named providers.")
        if not isinstance(routes, dict) or not routes or set(routes) - ROLES:
            raise AIRouterError("Unexpected/empty AI routes.")
        self.providers: dict[str, dict[str, Any]] = {}
        for item in providers:
            if not isinstance(item, dict):
                raise AIRouterError("Provider entry must be an object.")
            name = item.get("id")
            if not isinstance(name, str) or not ID.fullmatch(name) or name in self.providers:
                raise AIRouterError("Duplicate or invalid provider id.")
            url = _endpoint(item.get("endpoint"))
            model = item.get("model")
            env = item.get("api_key_env")
            mode = item.get("billing")
            if not isinstance(model, str) or not 1 <= len(model) <= 120:
                raise AIRouterError("Invalid model.")
            if env is not None and (
                not isinstance(env, str) or not KEY.fullmatch(env)
            ):
                raise AIRouterError("api_key_env must be a safe environment variable name.")
            if urlparse(url).hostname not in {"localhost", "127.0.0.1"} and env is None:
                raise AIRouterError("Remote providers must use an API key environment variable.")
            if mode not in ("free", "paid"):
                raise AIRouterError("Each provider must explicitly declare billing=free|paid.")
            limit = item.get("max_output_tokens", 1000)
            if type(limit) is not int or not 1 <= limit <= 4096:
                raise AIRouterError("max_output_tokens must be 1..4096.")
            self.providers[name] = {
                "id": name, "endpoint": url, "model": model,
                "api_key_env": env, "billing": mode,
                "max_output_tokens": limit,
            }
        self.routes: dict[str, list[str]] = {}
        for role, choices in routes.items():
            if role not in ROLES or not isinstance(choices, list) or not choices:
                raise AIRouterError("Each route requires a nonempty ordered provider list.")
            if len(choices) != len(set(choices)) or any(c not in self.providers for c in choices):
                raise AIRouterError("Route references unknown or duplicated providers.")
            self.routes[role] = choices


class ChatRouter:
    def __init__(self, config: AIConfig, *, opener: Any | None = None):
        self.config = config
        self.opener = opener if opener is not None else request.build_opener(
            request.ProxyHandler({}), NoRedirect()
        )

    def complete(
        self, *, role: str, system_prompt: str, user_prompt: str,
        allow_paid: bool = False, allow_fallback: bool = False,
        different_from: str | None = None, max_output_tokens: int = 800,
    ) -> dict[str, Any]:
        if role not in self.config.routes:
            raise AIRouterError("No approved provider route for this role.")
        if type(allow_paid) is not bool or type(allow_fallback) is not bool:
            raise AIRouterError("Explicit paid/fallback settings must be boolean.")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 4096:
            raise AIRouterError("Invalid max output tokens.")
        for prompt in (system_prompt, user_prompt):
            if not isinstance(prompt, str) or not 1 <= len(prompt) <= 12_000:
                raise AIRouterError("Prompt must contain 1..12000 characters.")
        providers = [
            self.config.providers[choice]
            for choice in self.config.routes[role]
            if choice != different_from
            and (allow_paid or self.config.providers[choice]["billing"] == "free")
        ]
        if not providers:
            raise AIRouterError("No eligible approved provider (billing/independence gate).")
        if not allow_fallback:
            providers = providers[:1]
        prompt_hash = hashlib.sha256(
            (system_prompt + "\x00" + user_prompt).encode("utf-8")
        ).hexdigest()
        for index, provider in enumerate(providers):
            env_var = provider["api_key_env"]
            key = os.environ.get(env_var) if env_var else None
            if env_var and not key:
                # Never try a different provider on missing credentials by default.
                raise AIRouterError(f"Missing required environment variable: {env_var}")
            payload = {
                "model": provider["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": min(max_output_tokens, provider["max_output_tokens"]),
                "temperature": 0.3,
                "stream": False,
            }
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = "Bearer " + key
            req = request.Request(
                provider["endpoint"], method="POST",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
            )
            try:
                with self.opener.open(req, timeout=75) as response:
                    raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise AIRouterError("AI response exceeded size limit.")
                decoded = json.loads(raw)
                content = decoded["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise AIRouterError("AI provider returned empty/non-text response.")
                if len(content) > 60_000:
                    raise AIRouterError("AI answer exceeded text cap.")
                return {
                    "provider_id": provider["id"],
                    "model": provider["model"],
                    "role": role,
                    "billing_policy": provider["billing"],
                    "prompt_sha256": prompt_hash,
                    "answer": content,
                    "answer_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "failover_used": index > 0,
                    "output_token_cap": payload["max_tokens"],
                }
            except (error.URLError, TimeoutError, OSError, KeyError, IndexError,
                    TypeError, ValueError) as exc:
                # No exception body, HTTP response, Authorization value or prompts in logs.
                if index == len(providers) - 1:
                    raise AIRouterError(
                        f"Approved AI provider failed for role {role} "
                        f"(provider={provider['id']}); check local provider logs."
                    ) from None
        raise AIRouterError("No eligible provider completed the request.")
