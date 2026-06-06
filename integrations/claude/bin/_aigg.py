"""Shared helpers for the aigg-memory Claude Code hooks.

Hooks MUST be robust: a memory hiccup must never break the conversation. So every
public helper swallows errors and the hook scripts always exit 0 with valid output.
The actual memory work is shelled out to the installed `aigg-memory` CLI (configured
via env), so the hook only needs stdlib python3.

Principal-scoped memory — the agent talks to different people, and a conversation
must only write the *speaker's own* memory:
  BASE/self            the agent's persona card (owner-authored, locked; loop never writes it)
  BASE/owner           the owner profile (updated only in an owner session)
  BASE/people/<id>     one corpus per other interlocutor (isolated)
The host app authenticates the speaker and passes AIGG_MEMORY_PRINCIPAL; writes go to
that principal's root, so a stranger's chat can never touch the owner/self memory.

Config (env):
  AIGG_MEMORY_ROOT      base dir.                          Default ~/.aigg-memory
  AIGG_MEMORY_OWNER     the owner's principal id.          Default "owner"
  AIGG_MEMORY_PRINCIPAL authenticated current speaker.     Default = owner (single-owner)
  AIGG_MEMORY_CMD       the CLI.                           Default "aigg-memory"
  AIGG_MEMORY_AIGG_URL / _KEY / _MODEL / _EXTRACTOR        session-end extraction/reconcile
"""
import json
import os
import shlex
import subprocess
import sys

BASE = os.environ.get("AIGG_MEMORY_ROOT", os.path.expanduser("~/.aigg-memory"))
OWNER = os.environ.get("AIGG_MEMORY_OWNER", "owner")
PRINCIPAL = os.environ.get("AIGG_MEMORY_PRINCIPAL", OWNER)
CMD_TOKENS = shlex.split(os.environ.get("AIGG_MEMORY_CMD", "aigg-memory"))


def _scope_root(*parts):
    return os.path.join(BASE, *parts)


def _safe(component):  # defense-in-depth: a principal id must not escape its dir
    return (component or "anon").replace("/", "_").replace("\\", "_").replace("..", "_").strip() or "anon"


SELF_ROOT = _scope_root("self")     # persona (owner-authored, locked)
OWNER_ROOT = _scope_root("owner")   # owner profile
# where THIS speaker's memory is recalled from AND written to:
SPEAKER_ROOT = OWNER_ROOT if PRINCIPAL == OWNER else _scope_root("people", _safe(PRINCIPAL))
SPEAKER_IS_OWNER = PRINCIPAL == OWNER


def corpus_dir(root):
    return os.path.join(root, "memory")


def evidence_path(root):
    return os.path.join(root, "evidence.jsonl")


def sessions_dir(root):
    return os.path.join(root, ".sessions")


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
    out = run_cli(args, timeout)
    if out is None or out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return None


def emit_context(event, text):
    """Emit the hook's additionalContext envelope and exit 0 (the only safe exit)."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text or ""}},
                     ensure_ascii=False))
    sys.exit(0)


def profile_block(root, cap=20):
    """Format the pinned profile of a scope (persona / owner / speaker) as a block."""
    if not os.path.isdir(corpus_dir(root)):
        return ""
    data = cli(["profile", "--root", root])
    rows = (data or {}).get("profile") or []
    lines = [f"- {(r.get('description') or r.get('name') or '').strip()}"
             for r in rows[:cap] if (r.get("description") or r.get("name"))]
    return "\n".join(lines)


def recall_block(root, query, n_best, retriever="hybrid"):
    """Recall units in a scope for `query` and format a compact context block."""
    if not os.path.isdir(corpus_dir(root)) or not query.strip():
        return ""
    data = cli(["recall", query, "--root", root, "--n-best", str(n_best), "--retriever", retriever])
    units = (data or {}).get("units") or []
    lines = []
    for u in units:
        desc = (u.get("description") or u.get("name") or "").strip()
        if desc:
            lines.append(f"- {desc}{' (related)' if u.get('relation') == 'dependency' else ''}")
    return "\n".join(lines)
