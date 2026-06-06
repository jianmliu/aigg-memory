#!/usr/bin/env python3
"""SessionEnd hook: the offline 'Dream' pass — for the CURRENT SPEAKER's memory only.

  transcript --(extract, model w/ fallback)--> evidence --(gated consolidate)--> units
            --(reconcile new statements vs that speaker's memory)--> git commit

Everything is scoped to SPEAKER_ROOT: an owner session updates the owner profile; a
stranger's session updates only BASE/people/<id>. The owner profile and persona can
NOT be changed by talking to someone else. Always exits 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import (PRINCIPAL, SPEAKER_ROOT, evidence_path, read_stdin_json,  # noqa: E402
                   run_cli as run, sessions_dir)


def main() -> None:
    data = read_stdin_json()
    session_id = (data.get("session_id") or "session").replace("/", "_")
    transcript = os.path.join(sessions_dir(SPEAKER_ROOT), f"{session_id}.txt")
    if not os.path.exists(transcript):
        return
    root, evidence = SPEAKER_ROOT, evidence_path(SPEAKER_ROOT)

    # 1) extract -> evidence, stamped with WHO is speaking (the authenticated principal /
    #    EOA) so authority + provenance flow to the units. (model when configured — a local
    #    URL stays offline — else heuristic)
    ingest = ["ingest", "--transcript", transcript, "--evidence", evidence, "--asserted-by", PRINCIPAL]
    aigg_url = os.environ.get("AIGG_MEMORY_AIGG_URL")
    use_model = aigg_url and os.environ.get("AIGG_MEMORY_EXTRACTOR", "aigg") != "heuristic"
    if use_model:
        ingest += ["--extractor", "aigg", "--aigg-url", aigg_url, "--fallback-heuristic",
                   "--model", os.environ.get("AIGG_MEMORY_MODEL", "gpt-4o-mini")]
        if os.environ.get("AIGG_MEMORY_AIGG_KEY"):
            ingest += ["--aigg-key", os.environ["AIGG_MEMORY_AIGG_KEY"]]
    run(ingest)

    # 2) consolidate only when the readiness signal says there's enough new evidence
    status = run(["consolidation-status", "--root", root, "--evidence", evidence])
    recommended = True
    if status and status.stdout.strip():
        try:
            recommended = bool(json.loads(status.stdout).get("recommended", True))
        except Exception:
            recommended = True
    if recommended:
        # authority gate: only consolidate evidence asserted by THIS speaker — so even a
        # tampered evidence file can't smuggle another principal's facts into this root.
        run(["consolidate-corpus", "--root", root, "--evidence", evidence, "--write", "--format", "json",
             "--allowed-principal", PRINCIPAL])
        # 3) reconcile new statements vs this speaker's memory (needs a model). Locked units
        #    (persona / owner-set facts) are never auto-changed; uncertain -> needs_review.
        if use_model:
            import datetime
            recon = ["reconcile", "--root", root, "--write", "--aigg-url", aigg_url,
                     "--model", os.environ.get("AIGG_MEMORY_MODEL", "gpt-4o-mini"),
                     "--now", datetime.datetime.now().astimezone().isoformat()]
            if os.environ.get("AIGG_MEMORY_AIGG_KEY"):
                recon += ["--aigg-key", os.environ["AIGG_MEMORY_AIGG_KEY"]]
            run(recon)
        run(["commit", "--root", root, "--message", f"session {session_id}: consolidate memory"])

    try:
        os.remove(transcript)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
sys.exit(0)
