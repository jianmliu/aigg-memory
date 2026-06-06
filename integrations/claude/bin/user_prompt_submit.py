#!/usr/bin/env python3
"""UserPromptSubmit hook: two jobs per turn —
  1. recall memory relevant to THIS message and inject it before the model answers;
  2. capture the message to the session transcript (cheap), for session-end Dream.

Capture is deliberately light: just append the raw line. Extraction (heuristic or
AIGG) runs once at session end, not per turn — cheaper, and matches 'consolidate
offline'."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import SESSIONS_DIR, emit_context, read_stdin_json, recall_block  # noqa: E402

data = read_stdin_json()
prompt = (data.get("prompt") or "").strip()
session_id = (data.get("session_id") or "session").replace("/", "_")

# 1) capture (best-effort; never break the turn)
if prompt:
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        with open(os.path.join(SESSIONS_DIR, f"{session_id}.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"user: {prompt}\n")
    except Exception:
        pass

# 2) recall relevant memory for this message
N = int(os.environ.get("AIGG_MEMORY_TURN_N", "4"))
block = recall_block(prompt, N)
if block:
    emit_context("UserPromptSubmit",
                 "Relevant memory for this message (from earlier conversations):\n" + block)
emit_context("UserPromptSubmit", "")
