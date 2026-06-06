#!/usr/bin/env python3
"""SessionStart hook: inject the self-profile — the pinned facts (identity + durable
preferences) — so the assistant knows you from turn one.

The profile is the explicit 'pinned' tier over the units (set with
`aigg-memory edit <slug> --pin`), so injection is precise and deterministic, not a
guess against an anchor query."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import emit_context, profile_block, read_stdin_json  # noqa: E402

read_stdin_json()  # consume stdin

CAP = int(os.environ.get("AIGG_MEMORY_PROFILE_N", "20"))

block = profile_block(cap=CAP)
if block:
    emit_context("SessionStart",
                 "Memory — this user's profile (pinned facts from earlier conversations):\n"
                 + block
                 + "\n(Stable context about the user; verify before acting on anything consequential.)")
emit_context("SessionStart", "")
