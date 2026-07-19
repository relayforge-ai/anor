"""HMAC-signed Scholar membership tokens for expensive API ops.

When ``ANOR_MEMBER_SECRET`` is set, LLM forks and video job enqueues require a
valid short-lived token (header ``X-ANOR-Member`` or ``Authorization: Bearer``).

When the secret is unset (local/dev/CI default), expensive ops remain open but
rate-limited — matching prior behavior.

Demo unlock: ``POST /api/member/demo`` issues a token (rate-limited). Production
Stripe webhooks should call ``issue_token`` after payment instead.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional


def member_secret() -> str:
    return (os.environ.get("ANOR_MEMBER_SECRET") or "").strip()


def enforcement_enabled() -> bool:
    """True when expensive endpoints require a valid member token."""
    if (os.environ.get("ANOR_MEMBER_ENFORCE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True
    return bool(member_secret())


def token_ttl_s() -> int:
    raw = (os.environ.get("ANOR_MEMBER_TTL_S") or "").strip()
    try:
        return max(60, int(raw)) if raw else 86_400  # 24h default
    except ValueError:
        return 86_400


def issue_token(plan: str = "scholar", *, ttl_s: Optional[int] = None) -> Optional[str]:
    """Issue a signed token. Returns None if no secret configured."""
    secret = member_secret()
    if not secret:
        # Dev mode: opaque demo marker (not cryptographically verified)
        return f"dev:{plan}:{int(time.time()) + (ttl_s or token_ttl_s())}"
    exp = int(time.time()) + int(ttl_s if ttl_s is not None else token_ttl_s())
    plan_clean = "".join(c for c in plan if c.isalnum() or c in "_-")[:32] or "scholar"
    body = f"v1.{plan_clean}.{exp}"
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: Optional[str]) -> tuple[bool, str]:
    """Return (ok, reason)."""
    if not token or not isinstance(token, str):
        return False, "missing_token"
    token = token.strip()
    if len(token) > 512:
        return False, "token_too_long"

    secret = member_secret()
    if not secret:
        # Dev tokens: accept any non-empty when enforcement is only via ENFORCE flag
        if token.startswith("dev:"):
            parts = token.split(":")
            if len(parts) >= 3:
                try:
                    exp = int(parts[-1])
                    if exp < int(time.time()):
                        return False, "token_expired"
                except ValueError:
                    return False, "bad_token"
            return True, "dev"
        # If enforce is on without secret, reject (misconfiguration)
        if enforcement_enabled():
            return False, "server_misconfigured"
        return True, "open"

    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return False, "bad_token"
    _v, plan, exp_s, sig = parts
    body = f"v1.{plan}.{exp_s}"
    expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False, "bad_signature"
    try:
        exp = int(exp_s)
    except ValueError:
        return False, "bad_token"
    if exp < int(time.time()):
        return False, "token_expired"
    return True, plan


def extract_token(handler) -> Optional[str]:
    """Read member token from request headers."""
    direct = handler.headers.get("X-ANOR-Member") or handler.headers.get("X-Anor-Member")
    if direct:
        return direct.strip()
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def require_member(handler) -> Optional[tuple[int, dict]]:
    """If enforcement is on and token invalid, return (status, error_body). Else None."""
    if not enforcement_enabled():
        return None
    token = extract_token(handler)
    ok, reason = verify_token(token)
    if ok:
        return None
    return (
        401,
        {
            "error": "Scholar membership required for this action",
            "code": "member_required",
            "reason": reason,
        },
    )
