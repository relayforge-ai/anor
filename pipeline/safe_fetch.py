"""Safe secondary HTTP fetches for pipeline media (SSRF / size hardening).

Primary endpoints (LLM_URL / IMAGE_URL / TTS_URL) are operator-configured.
Secondary URLs come from *upstream responses* (e.g. image generation returns
a download URL) and must not be able to pivot the host into:
  - non-HTTP schemes (file://, gopher://, …)
  - cloud instance-metadata endpoints
  - unbounded downloads that OOM the worker

Redirects are disabled on secondary fetches so a 302 cannot hop to metadata.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Well-known cloud metadata hosts — never fetch even if http(s)
_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata",
        "metadata.internal",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def max_media_bytes() -> int:
    """Cap for secondary media downloads (images). Default 25 MiB."""
    return _env_int("ANOR_MAX_MEDIA_BYTES", 25 * 1024 * 1024)


def validate_http_url(url: str) -> urllib.parse.ParseResult:
    """Allow only http(s) URLs with a host; reject userinfo and metadata hosts.

    Raises ValueError with a short reason on rejection.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    url = url.strip()
    if len(url) > 2048:
        raise ValueError("URL exceeds 2048 characters")
    if any(c in url for c in ("\n", "\r", "\x00")):
        raise ValueError("URL contains control characters")

    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"URL scheme not allowed: {scheme or '(empty)'}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL missing host")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL userinfo (credentials) not allowed")

    if host in _BLOCKED_HOSTS:
        raise ValueError(f"blocked host: {host}")

    # Link-local IPv4 range used by cloud metadata (covers 169.254.0.0/16)
    if host.startswith("169.254."):
        raise ValueError(f"blocked link-local host: {host}")

    return parsed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on secondary fetches (prevents open-redirect SSRF)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirects not allowed for secondary media fetch → {newurl}",
            headers,
            fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def read_response_limited(resp, max_bytes: int) -> bytes:  # noqa: ANN001
    """Read an HTTP response body with a hard size cap."""
    if max_bytes <= 0:
        return resp.read()
    chunks: list[bytes] = []
    total = 0
    # Honour Content-Length early when present
    cl = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
    if cl:
        try:
            if int(cl) > max_bytes:
                raise ValueError(
                    f"Content-Length {cl} exceeds max {max_bytes} bytes"
                )
        except ValueError as e:
            if "exceeds max" in str(e):
                raise
            # non-integer CL — ignore and stream
    while True:
        to_read = 65536 if max_bytes <= 0 else min(65536, max_bytes - total + 1)
        chunk = resp.read(to_read)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"response exceeds max {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def safe_get_bytes(
    url: str,
    *,
    max_bytes: Optional[int] = None,
    timeout: float = 120.0,
    api_key: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> bytes:
    """GET ``url`` after validation; no redirects; size-capped body.

    Raises ValueError for URL policy violations, urllib.error for transport.
    """
    validate_http_url(url)
    limit = max_media_bytes() if max_bytes is None else max_bytes
    hdrs = {"Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    if api_key:
        hdrs["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=None, headers=hdrs, method="GET")
    with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
        return read_response_limited(resp, limit)
