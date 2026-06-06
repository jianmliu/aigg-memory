#!/usr/bin/env python3
"""SessionStart hook: inject two cards so the agent knows WHO IT IS and WHO IT'S WITH —
  1. its persona (BASE/self) — owner-authored, the same in every conversation;
  2. the current speaker's profile (BASE/owner if the owner, else BASE/people/<id>).

The owner's private profile is injected ONLY in an owner session (SPEAKER_ROOT is the
owner root only when the principal is the owner) — a stranger never sees it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import (SELF_ROOT, SPEAKER_IS_OWNER, SPEAKER_ROOT,  # noqa: E402
                   emit_context, profile_block, read_stdin_json)

read_stdin_json()
if os.environ.get("AIGG_MEMORY_REENTRY"):
    emit_context("SessionStart", "")  # nested `claude -p` (claude-cli backend) — inject nothing
CAP = int(os.environ.get("AIGG_MEMORY_PROFILE_N", "20"))

parts = []
persona = profile_block(SELF_ROOT, CAP)
if persona:
    parts.append("Your persona — who you are, set by your owner (do not contradict this):\n" + persona)

speaker = profile_block(SPEAKER_ROOT, CAP)
if speaker:
    who = "your owner" if SPEAKER_IS_OWNER else "the person you're talking to"
    parts.append(f"What you know about {who} (from earlier conversations):\n" + speaker)

emit_context("SessionStart", ("\n\n".join(parts) +
             "\n(Context from earlier; verify before acting on anything consequential.)") if parts else "")
