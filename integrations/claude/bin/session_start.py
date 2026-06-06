#!/usr/bin/env python3
"""SessionStart hook: inject the durable profile — the facts past conversations
learned about this user — so the assistant knows you from turn one.

(MVP: the 'profile' is recalled against a configurable anchor query. A first-class
pinned self-profile is a planned improvement.)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import emit_context, read_stdin_json, recall_block  # noqa: E402

read_stdin_json()  # consume stdin

QUERY = os.environ.get("AIGG_MEMORY_PROFILE_QUERY",
                       "user preferences identity name role projects goals communication style")
N = int(os.environ.get("AIGG_MEMORY_PROFILE_N", "8"))

block = recall_block(QUERY, N)
if block:
    emit_context("SessionStart",
                 "Memory — durable facts about this user, recalled from earlier conversations:\n"
                 + block
                 + "\n(Context from past sessions; verify before acting on anything consequential.)")
emit_context("SessionStart", "")
