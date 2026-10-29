"""Refuse to commit or push anything that looks like an API key.

Run by the git hooks in tools/hooks (pre-commit scans what is staged, pre-push scans
every commit in the history). It looks for:
  - the real Meta key itself, if one is saved on this machine (never printed);
  - .env files;
  - well-known key shapes (sk-..., ghp_..., AKIA..., private key blocks);
  - a key-like name (api_key, token, secret, password, bearer) set to a long literal.
A line that must contain such text on purpose can end with "secret-scan: ok".

Exit code 0 means clean, 1 means something was found (the commit or push stops).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.meta.key import find_key  # noqa: E402

ALLOW = "secret-scan: ok"

SHAPES = [
    ("an OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("an AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{24,}")),
]

# name = "long literal", name: 'long literal', NAME=longliteral
ASSIGNED = re.compile(
    r"""(?ix)
    (api[_-]?key|secret|token|password|passwd)\w*   # a key-like name
    ["']?\s*[:=]\s*                                  # = or :
    ["']([A-Za-z0-9_\-\.\+/=]{20,})["']              # a quoted long literal
    """
)
ASSIGNED_ENV = re.compile(r"(?i)^\s*\w*(API_KEY|SECRET|TOKEN|PASSWORD)\w*\s*=\s*([^\s#\"'<]{20,})\s*$")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise SystemExit(f"secret_scan: git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def added_lines(diff: str) -> list[tuple[str, str]]:
    """(file, line) for every added line in a unified diff."""
    found, current = [], "?"
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            found.append((current, line[1:]))
    return found


def scan_lines(lines: list[tuple[str, str]], real_key: str | None) -> list[str]:
    problems = []
    for where, text in lines:
        if ALLOW in text:
            continue
        if real_key and len(real_key) >= 8 and real_key in text:
            problems.append(f"{where}: contains your real META_API_KEY")
            continue
        for what, pattern in SHAPES:
            if pattern.search(text):
                problems.append(f"{where}: looks like {what}")
                break
        else:
            if ASSIGNED.search(text) or ASSIGNED_ENV.search(text):
                problems.append(f"{where}: a key-like name is set to a long literal")
    return problems


def scan_names(names: list[str]) -> list[str]:
    bad = []
    for name in names:
        base = name.rsplit("/", 1)[-1]
        if base == ".env.example":
            continue
        if base == ".env" or base.endswith(".env") or base.startswith(".env."):
            bad.append(f"{name}: .env files hold secrets and are never committed")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="scan what is about to be committed")
    mode.add_argument("--history", action="store_true", help="scan every commit")
    args = ap.parse_args(argv)

    real_key, _where = find_key()
    if args.staged:
        names = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
        diff = _git("diff", "--cached", "--unified=0", "--no-color")
    else:
        names = _git("log", "--all", "--name-only", "--format=", "--diff-filter=ACMR").splitlines()
        diff = _git("log", "--all", "-p", "--unified=0", "--no-color", "--format=")

    problems = scan_names(names) + scan_lines(added_lines(diff), real_key)
    if problems:
        print("secret_scan: refused. Found:", file=sys.stderr)
        for p in sorted(set(problems)):
            print("  - " + p, file=sys.stderr)
        print("Move the secret to META_API_KEY or a .env file, then try again.", file=sys.stderr)
        return 1
    print(f"secret_scan: clean ({'staged changes' if args.staged else 'whole history'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
