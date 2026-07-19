"""HTTP byte-range parsing for media streaming (RFC 7233 subset).

Supports a single range unit (first of multi-range requests):
  bytes=0-499     closed range
  bytes=500-      open-ended from offset
  bytes=-500      suffix (last N bytes)

Unsatisfiable ranges return status 416 (caller sends Content-Range: bytes */size).
Malformed units that cannot be parsed also return 416 rather than silently
serving the full body (avoids surprising clients and full-file bandwidth waste).
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class ByteRange(NamedTuple):
    """Inclusive byte range result for a file of known size."""

    status: int  # 200 full | 206 partial | 416 unsatisfiable
    start: int
    end: int  # inclusive

    @property
    def length(self) -> int:
        if self.status == 416 or self.end < self.start:
            return 0
        return self.end - self.start + 1


def parse_byte_range(range_header: Optional[str], size: int) -> ByteRange:
    """Parse a Range header against a resource size.

    When ``range_header`` is absent/empty, returns full-content 200.
    When size is 0, Range is ignored (200 empty).
    """
    if size <= 0:
        return ByteRange(200, 0, -1)

    full = ByteRange(200, 0, size - 1)
    if not range_header:
        return full

    h = range_header.strip()
    if not h.lower().startswith("bytes="):
        # Unknown unit — ignore per common server practice
        return full

    # First range only (multi-range rare for HTML5 video)
    unit = h[6:].split(",", 1)[0].strip()
    if "-" not in unit:
        return ByteRange(416, 0, 0)

    start_s, end_s = unit.split("-", 1)
    start_s = start_s.strip()
    end_s = end_s.strip()

    # Suffix: bytes=-N  (last N bytes)
    if start_s == "":
        if end_s == "":
            return ByteRange(416, 0, 0)
        try:
            suffix = int(end_s)
        except ValueError:
            return ByteRange(416, 0, 0)
        if suffix <= 0:
            return ByteRange(416, 0, 0)
        if suffix >= size:
            return ByteRange(206, 0, size - 1)
        return ByteRange(206, size - suffix, size - 1)

    try:
        start = int(start_s)
    except ValueError:
        return ByteRange(416, 0, 0)

    if start < 0 or start >= size:
        return ByteRange(416, 0, 0)

    if end_s == "":
        end = size - 1
    else:
        try:
            end = int(end_s)
        except ValueError:
            return ByteRange(416, 0, 0)
        if end < start:
            return ByteRange(416, 0, 0)
        end = min(end, size - 1)

    return ByteRange(206, start, end)
