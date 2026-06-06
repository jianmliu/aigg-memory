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


def _deep_due(root: str) -> bool:
    """App-owned cadence: run the deep clean (compact + curate) every Nth dream. The
    engine ships no scheduler, so the trigger lives here — a tiny counter file per root.
    N comes from AIGG_MEMORY_DEEP_EVERY (default 10); 0 disables the deep clean."""
    every = int(os.environ.get("AIGG_MEMORY_DEEP_EVERY", "10") or 0)
    if every <= 0:
        return False
    path = os.path.join(root, ".dream_count")
    try:
        n = int(open(path).read().strip()) + 1 if os.path.exists(path) else 1
        with open(path, "w") as fh:
            fh.write(str(n))
        return n % every == 0
    except Exception:
        return False


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

    # 2) Dream only when the readiness signal says there's enough new evidence
    status = run(["consolidation-status", "--root", root, "--evidence", evidence])
    recommended = True
    if status and status.stdout.strip():
        try:
            recommended = bool(json.loads(status.stdout).get("recommended", True))
        except Exception:
            recommended = True
    if recommended:
        import datetime
        # the offline maintenance pass. LIGHT (consolidate + reconcile) every time; the
        # periodic DEEP clean (compact + curate) every Nth dream. Authority gate: only
        # this speaker's asserted evidence is consolidated, even if the file was tampered.
        cmd = ["dream", "--root", root, "--evidence", evidence, "--write", "--commit",
               "--allowed-principal", PRINCIPAL]
        if use_model:
            cmd += ["--aigg-url", aigg_url, "--model", os.environ.get("AIGG_MEMORY_MODEL", "gpt-4o-mini"),
                    "--now", datetime.datetime.now().astimezone().isoformat()]
            if os.environ.get("AIGG_MEMORY_AIGG_KEY"):
                cmd += ["--aigg-key", os.environ["AIGG_MEMORY_AIGG_KEY"]]
            if _deep_due(root):              # deep clean needs a model (curate)
                cmd.append("--deep")
        run(cmd)

    try:
        os.remove(transcript)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
sys.exit(0)
