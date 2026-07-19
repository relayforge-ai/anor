#!/usr/bin/env python3
"""Dependency audit for ANOR / Forked History.

1. Parse requirement files and flag unpinned / overly loose specs.
2. Optionally run ``pip-audit`` when installed (or via ``pip install pip-audit``).

Usage:
  python scripts/dep_audit.py
  python scripts/dep_audit.py --strict          # fail on unpinned deps
  python scripts/dep_audit.py --pip-audit       # also run pip-audit if available
  python scripts/dep_audit.py --pip-audit --require-pip-audit  # fail if missing
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQ_FILES = [
    ROOT / "sim" / "requirements.txt",
    ROOT / "sim" / "requirements-dev.txt",
    ROOT / "pipeline" / "requirements.txt",
]

# Lines that are only references or comments
_SKIP = re.compile(r"^\s*(#|$|-r\s)")
# Captures package and version specifier
_REQ = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)\s*((?:[<>=!~]=?|==)\s*[^;#\s]+(?:\s*,\s*[<>=!~]=?\s*[^;#\s]+)*)?"
)


def parse_requirements(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if _SKIP.match(line):
            continue
        # strip env markers
        line = line.split(";", 1)[0].strip()
        m = _REQ.match(line)
        if not m:
            continue
        name, spec = m.group(1), (m.group(2) or "").strip()
        out.append((name, spec))
    return out


def is_pinned(spec: str) -> bool:
    """True if pinned to an exact version or a reasonably tight upper bound."""
    if not spec:
        return False
    if "==" in spec or "===" in spec:
        return True
    # Accept compatible release ~= and ranges with an upper bound
    if "~=" in spec:
        return True
    if "<" in spec or "<=" in spec:
        return True
    return False


def audit_files(strict: bool) -> int:
    print("=== Requirement pin audit ===")
    issues = 0
    total = 0
    for path in REQ_FILES:
        rel = path.relative_to(ROOT)
        reqs = parse_requirements(path)
        if not path.exists():
            print(f"  skip (missing): {rel}")
            continue
        if not reqs and path.stat().st_size < 200:
            # pipeline/requirements is intentionally empty of packages
            print(f"  ok (no third-party pins required): {rel}")
            continue
        print(f"  {rel}:")
        for name, spec in reqs:
            total += 1
            pinned = is_pinned(spec)
            mark = "PINNED" if pinned else "LOOSE"
            print(f"    [{mark}] {name} {spec or '(no specifier)'}")
            if not pinned:
                issues += 1
    print(f"  packages checked: {total}, loose: {issues}")
    if strict and issues:
        print("FAIL: --strict and unpinned dependencies found", file=sys.stderr)
        return 1
    if issues:
        print("WARN: prefer upper bounds or == pins for reproducible builds")
    else:
        print("OK: all listed third-party deps have version constraints")
    return 0


def run_pip_audit(require: bool) -> int:
    print("=== pip-audit ===")
    pip_audit = shutil.which("pip-audit")
    if not pip_audit:
        # try python -m pip_audit
        try:
            subprocess.run(
                [sys.executable, "-m", "pip_audit", "--version"],
                check=True,
                capture_output=True,
            )
            cmd = [sys.executable, "-m", "pip_audit"]
        except (subprocess.CalledProcessError, FileNotFoundError):
            msg = "pip-audit not installed (pip install pip-audit)"
            if require:
                print(f"FAIL: {msg}", file=sys.stderr)
                return 1
            print(f"SKIP: {msg}")
            return 0
    else:
        cmd = [pip_audit]

    # Audit the current environment + declared requirement files that have packages
    args = list(cmd)
    for path in REQ_FILES:
        if path.exists() and parse_requirements(path):
            args.extend(["-r", str(path)])
    print("  running:", " ".join(args))
    try:
        proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        if require:
            return 1
        print("SKIP: pip-audit unavailable")
        return 0
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        print(f"FAIL: pip-audit exit {proc.returncode}", file=sys.stderr)
        return proc.returncode
    print("OK: pip-audit clean (or no vulns reported)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ANOR dependency audit")
    p.add_argument("--strict", action="store_true", help="fail on unpinned requirements")
    p.add_argument("--pip-audit", action="store_true", help="run pip-audit when available")
    p.add_argument(
        "--require-pip-audit",
        action="store_true",
        help="fail if pip-audit is not installed",
    )
    args = p.parse_args(argv)

    rc = audit_files(strict=args.strict)
    if args.pip_audit or args.require_pip_audit:
        rc = max(rc, run_pip_audit(require=args.require_pip_audit))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
