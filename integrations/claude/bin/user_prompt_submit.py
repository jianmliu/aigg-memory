#!/usr/bin/env python3
"""UserPromptSubmit hook: recall memory relevant to this message and capture it — both
scoped to the CURRENT SPEAKER's root. A stranger's message recalls/writes only their
own corpus; it can never reach the owner or persona memory."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import SPEAKER_ROOT, emit_context, read_stdin_json, recall_block, sessions_dir  # noqa: E402

data = read_stdin_json()
if os.environ.get("AIGG_MEMORY_REENTRY"):
    emit_context("UserPromptSubmit", "")  # nested `claude -p` (claude-cli backend) — no recall/capture
prompt = (data.get("prompt") or "").strip()
session_id = (data.get("session_id") or "session").replace("/", "_")

# capture to the speaker's own transcript (best-effort)
if prompt:
    try:
        os.makedirs(sessions_dir(SPEAKER_ROOT), exist_ok=True)
        with open(os.path.join(sessions_dir(SPEAKER_ROOT), f"{session_id}.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"user: {prompt}\n")
    except Exception:
        pass

# recall the speaker's relevant memory for this message
N = int(os.environ.get("AIGG_MEMORY_TURN_N", "4"))
block = recall_block(SPEAKER_ROOT, prompt, N)
if block:
    emit_context("UserPromptSubmit", "Relevant memory for this message (from earlier conversations):\n" + block)
emit_context("UserPromptSubmit", "")
