"""Safe filesystem path resolution under a root directory."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Relative media keys: "ELO-003-historical/ELO-003-historical.mp4"
_SAFE_REL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,240}$")


def safe_join(root: Path, relative: str) -> Optional[Path]:
    """Resolve ``relative`` under ``root`` or return None if unsafe.

    Rejects absolute paths, parent traversal, null bytes, and escapes via symlink
    resolution when the target would leave ``root``.
    """
    if not isinstance(relative, str) or not relative:
        return None
    if "\x00" in relative:
        return None
    raw = relative.strip()
    # Reject absolute paths and Windows drive roots before any normalization
    if raw.startswith(("/", "\\")) or (len(raw) >= 2 and raw[1] == ":"):
        return None
    if raw.startswith("~"):
        return None
    # Strip only a single optional "./" prefix — never lstrip("./") (eats "../")
    rel = raw[2:] if raw.startswith("./") else raw
    if not rel:
        return None
    if ".." in Path(rel).parts:
        return None
    if not _SAFE_REL.match(rel):
        return None

    root_r = root.resolve()
    try:
        candidate = (root_r / rel).resolve()
    except (OSError, RuntimeError):
        return None

    try:
        candidate.relative_to(root_r)
    except ValueError:
        return None
    return candidate
