"""Opt-in OmniRoute profile builder for KidsStudio's existing text AI router.

Creates configuration only; performs zero requests and never reads credentials.
The gateway must independently enforce provider pinning and privacy constraints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .ai_router import AIConfig, AIRouterError

_GATEWAY_ENDPOINT = "http://127.0.0.1:20128/v1/chat/completions"
_KEY_ENV = "KIDS_OMNIROUTE_KEY"
_LOCAL_PREFIXES = frozenset({
    "ollama", "lmstudio", "llamacpp", "mlx-qwen", "mlx-gemma",
    "vllm", "llamafile", "ooba", "xinference",
})
_MODEL = re.compile(r"[a-z][a-z0-9._-]{1,39}/[A-Za-z0-9][A-Za-z0-9._:/+-]{0,109}\Z")
_RESERVED = frozenset({"auto", "combo", "combos", "omniroute"})
_ROLES = (("script_draft", "omni_draft"), ("editorial_review", "omni_review"))


class OmniRouteProfileError(ValueError):
    """A proposed gateway profile is unsafe or incomplete."""


def _model_info(model: str) -> tuple[str, bool]:
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise OmniRouteProfileError("Use an explicit provider/model ID.")
    prefix = model.split("/", 1)[0]
    if prefix in _RESERVED:
        raise OmniRouteProfileError("Automatic and combo routes are not allowed.")
    return prefix, prefix in _LOCAL_PREFIXES


def build_omniroute_profile(*, draft_model: str, review_model: str | None = None,
                            allow_external_profile: bool = False,
                            max_output_tokens: int = 1200) -> dict:
    """Return a conservative AIConfig-v1 profile without using the gateway.

    Any model outside the known local provider prefix list is treated as paid,
    even if its third-party provider advertises a free tier. This is a policy
    classification, not a statement about the actual invoice.
    """
    if type(allow_external_profile) is not bool:
        raise OmniRouteProfileError("External-profile authorization must be boolean.")
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 1200:
        raise OmniRouteProfileError("Output limit must be 1..1200 tokens.")
    draft_prefix, draft_local = _model_info(draft_model)
    entries = [(draft_model, draft_local)]
    if review_model is not None:
        review_prefix, review_local = _model_info(review_model)
        if review_prefix == draft_prefix:
            raise OmniRouteProfileError(
                "Independent review needs a different pinned provider prefix.")
        entries.append((review_model, review_local))
    if not allow_external_profile and any(not local for _, local in entries):
        raise OmniRouteProfileError("External model routes require explicit opt-in.")
    providers = []
    routes: dict[str, list[str]] = {}
    for (role, provider_id), (model, local) in zip(_ROLES, entries):
        providers.append({
            "id": provider_id,
            "endpoint": _GATEWAY_ENDPOINT,
            "model": model,
            "api_key_env": _KEY_ENV,
            "billing": "free" if local else "paid",
            "max_output_tokens": max_output_tokens,
        })
        routes[role] = [provider_id]
    return {"schema_version": 1, "providers": providers, "routes": routes}


def _profile_bytes(profile: dict) -> bytes:
    return (json.dumps(profile, ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n").encode("utf-8")


def write_private_profile(path: str | Path, profile: dict) -> None:
    """Explicit, create-once 0600 write into an existing 0700 private directory."""
    target = Path(os.path.abspath(os.path.expanduser(str(path))))
    if target.suffix != ".json":
        raise OmniRouteProfileError("Use a .json profile file.")
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise OmniRouteProfileError("Symlinked configuration paths are forbidden.")
    if any((part / ".git").exists() for part in (target.parent, *target.parents)):
        raise OmniRouteProfileError("Profile must be outside Git.")
    parent = target.parent
    if (not parent.is_dir() or parent.stat().st_mode & 0o077
            or (os.name == "posix" and parent.stat().st_uid != os.getuid())):
        raise OmniRouteProfileError("Existing private owner-controlled directory required.")
    # Never put credentials in the profile. The key lives only in the environment.
    data = _profile_bytes(profile)
    if len(data) > 64000:
        raise OmniRouteProfileError("Profile is too large.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    if (not stat.S_ISREG(target.stat().st_mode)
            or target.stat().st_mode & 0o077):
        raise OmniRouteProfileError("Profile permissions are unsafe.")


def describe_profile(profile: dict, *, written: bool) -> dict:
    """Safe metadata: never output private file paths, keys or prompts."""
    return {
        "status": "PRIVATE_PROFILE_WRITTEN" if written else "PROFILE_PREVIEW_ONLY",
        "schema_version": 1,
        "gateway": "loopback-only",
        "profile_sha256": hashlib.sha256(_profile_bytes(profile)).hexdigest(),
        "roles": sorted(profile["routes"]),
        "provider_billing_policies": sorted(
            item["billing"] for item in profile["providers"]),
        "automatic_route": False,
        "fallback_enabled": False,
        "live_requests_performed": 0,
        "production_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly write a KidsStudio OmniRoute text profile")
    parser.add_argument("--draft-model", required=True)
    parser.add_argument("--review-model")
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    parser.add_argument("--allow-external-profile", action="store_true")
    parser.add_argument("--write-private-config", metavar="PATH")
    args = parser.parse_args(argv)
    try:
        profile = build_omniroute_profile(
            draft_model=args.draft_model, review_model=args.review_model,
            allow_external_profile=args.allow_external_profile,
            max_output_tokens=args.max_output_tokens)
        if args.write_private_config:
            write_private_profile(args.write_private_config, profile)
        result = describe_profile(
            profile, written=bool(args.write_private_config))
    except (OmniRouteProfileError, AIRouterError, OSError, ValueError):
        print(json.dumps({"status": "OMNIROUTE_PROFILE_REJECTED",
                          "live_requests_performed": 0,
                          "publication_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
