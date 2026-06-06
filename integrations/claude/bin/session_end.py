#!/usr/bin/env python3
"""SessionEnd hook: the offline 'Dream' pass for what this session said.

  transcript --(extract)--> evidence --(readiness-gated consolidate)--> typed units --(git commit)

Extraction defaults to the zero-dependency heuristic; set AIGG_MEMORY_EXTRACTOR=aigg
(+ _AIGG_URL/_KEY/_MODEL, which may point at a LOCAL model) to use a model. The
consolidation readiness signal decides whether there's enough new evidence to bother.
Always exits 0 — a failed consolidation must not disrupt session teardown."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import EVIDENCE, ROOT, SESSIONS_DIR, read_stdin_json, run_cli as run  # noqa: E402


def main() -> None:
    data = read_stdin_json()
    session_id = (data.get("session_id") or "session").replace("/", "_")
    transcript = os.path.join(SESSIONS_DIR, f"{session_id}.txt")
    if not os.path.exists(transcript):
        return

    # 1) extract this session's transcript into the (shared, cross-session) evidence store
    ingest = ["ingest", "--transcript", transcript, "--evidence", EVIDENCE]
    if os.environ.get("AIGG_MEMORY_EXTRACTOR") == "aigg" and os.environ.get("AIGG_MEMORY_AIGG_URL"):
        ingest += ["--extractor", "aigg", "--aigg-url", os.environ["AIGG_MEMORY_AIGG_URL"],
                   "--model", os.environ.get("AIGG_MEMORY_MODEL", "gpt-4o-mini")]
        if os.environ.get("AIGG_MEMORY_AIGG_KEY"):
            ingest += ["--aigg-key", os.environ["AIGG_MEMORY_AIGG_KEY"]]
    run(ingest)

    # 2) only consolidate when the readiness signal says there's enough new evidence
    status = run(["consolidation-status", "--root", ROOT, "--evidence", EVIDENCE])
    recommended = True
    if status and status.stdout.strip():
        try:
            recommended = bool(json.loads(status.stdout).get("recommended", True))
        except Exception:
            recommended = True
    if recommended:
        run(["consolidate-corpus", "--root", ROOT, "--evidence", EVIDENCE, "--write", "--format", "json"])
        run(["commit", "--root", ROOT, "--message", f"session {session_id}: consolidate memory"])

    # 3) the transcript is consumed; evidence persists (repetition across sessions promotes facts)
    try:
        os.remove(transcript)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
sys.exit(0)
