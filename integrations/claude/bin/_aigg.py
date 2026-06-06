"""Shared helpers for the aigg-memory Claude Code hooks.

Hooks MUST be robust: a memory hiccup must never break the conversation. So every
public helper swallows errors and the hook scripts always exit 0 with valid output.
The actual memory work is shelled out to the installed `aigg-memory` CLI (configured
via env), so the hook only needs stdlib python3 — not the package importable here.

Config (env):
  AIGG_MEMORY_ROOT    memory root (per-user = a per-user root). Default ~/.aigg-memory
  AIGG_MEMORY_CMD     the CLI command.                          Default "aigg-memory"
  AIGG_MEMORY_PROFILE_QUERY / _N   what/how-much to inject at session start
  AIGG_MEMORY_EXTRACTOR / _AIGG_URL / _AIGG_KEY / _MODEL   session-end extraction
"""
import json
import os
import shlex
import subprocess
import sys

ROOT = os.environ.get("AIGG_MEMORY_ROOT", os.path.expanduser("~/.aigg-memory"))
# may be a multi-token command, e.g. "python3 -m aigg_memory.cli" (venv / not installed)
CMD_TOKENS = shlex.split(os.environ.get("AIGG_MEMORY_CMD", "aigg-memory"))
CORPUS_DIR = os.path.join(ROOT, "memory")
EVIDENCE = os.path.join(ROOT, "evidence.jsonl")
SESSIONS_DIR = os.path.join(ROOT, ".sessions")


def read_stdin_json():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def run_cli(args, timeout=90):
    """Run the aigg-memory CLI; return the CompletedProcess, or None on failure."""
    try:
        return subprocess.run([*CMD_TOKENS, *args], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def cli(args, timeout=20):
    """Run the aigg-memory CLI; return parsed JSON stdout, or None on any failure."""
    out = run_cli(args, timeout)
    if out is None or out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return None


def emit_context(event, text):
    """Emit the hook's additionalContext envelope and exit 0 (the only safe exit)."""
    payload = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text or ""}}
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def recall_block(query, n_best, retriever="hybrid"):
    """Recall units for `query` and format a compact context block (or '' if none)."""
    if not os.path.isdir(CORPUS_DIR) or not query.strip():
        return ""
    data = cli(["recall", query, "--root", ROOT, "--n-best", str(n_best), "--retriever", retriever])
    units = (data or {}).get("units") or []
    if not units:
        return ""
    lines = []
    for u in units:
        desc = (u.get("description") or u.get("name") or "").strip()
        if not desc:
            continue
        tag = " (related)" if u.get("relation") == "dependency" else ""
        lines.append(f"- {desc}{tag}")
    return "\n".join(lines)
