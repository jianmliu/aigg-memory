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
    if os.environ.get("AIGG_MEMORY_REENTRY"):
        return  # re-entry guard: a nested `claude -p` (claude-cli backend) must not recurse
    data = read_stdin_json()
    session_id = (data.get("session_id") or "session").replace("/", "_")
    transcript = os.path.join(sessions_dir(SPEAKER_ROOT), f"{session_id}.txt")
    if not os.path.exists(transcript):
        return
    root, evidence = SPEAKER_ROOT, evidence_path(SPEAKER_ROOT)

    # inference backend: HTTP (AIGG_MEMORY_AIGG_URL — a local URL stays offline) or claude-cli
    # (`claude -p` — uses the Claude Code login, no API key). claude-cli would re-enter THIS
    # hook, so set a guard the nested invocation's hooks check (top) before spawning it.
    backend = os.environ.get("AIGG_MEMORY_BACKEND", "http")
    aigg_url = os.environ.get("AIGG_MEMORY_AIGG_URL")
    model = os.environ.get("AIGG_MEMORY_MODEL", "gpt-4o-mini")
    use_model = backend == "claude-cli" or (aigg_url and os.environ.get("AIGG_MEMORY_EXTRACTOR", "aigg") != "heuristic")

    def model_args():
        if backend == "claude-cli":
            return ["--backend", "claude-cli", "--model", model]
        a = ["--aigg-url", aigg_url, "--model", model]
        if os.environ.get("AIGG_MEMORY_AIGG_KEY"):
            a += ["--aigg-key", os.environ["AIGG_MEMORY_AIGG_KEY"]]
        return a

    if backend == "claude-cli":
        os.environ["AIGG_MEMORY_REENTRY"] = "1"  # break hook recursion in the nested `claude -p`

    # 1) extract -> evidence, stamped with WHO is speaking (provenance + authority) and
    #    WHICH conversation it came from (origin-session)
    ingest = ["ingest", "--transcript", transcript, "--evidence", evidence,
              "--asserted-by", PRINCIPAL, "--origin-session", session_id]
    if use_model:
        ingest += ["--extractor", "aigg", "--fallback-heuristic"] + model_args()
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
        # ambient promotion gate: default 2 (a fact must recur to earn a unit — cheap,
        # reliable precision). Set AIGG_MEMORY_AMBIENT_MINCOUNT=1 for AGGRESSIVE capture
        # (one mention sticks) — safe only because the deep clean (curate) is the janitor;
        # warn if it's on without a model (no janitor). Explicit "remember" is unaffected.
        mincount = os.environ.get("AIGG_MEMORY_AMBIENT_MINCOUNT", "2")
        if mincount != "2" and not use_model:
            sys.stderr.write("aigg-memory: AMBIENT_MINCOUNT < 2 without a model — aggressive "
                             "capture has no curate janitor; noise may accumulate.\n")
        cmd = ["dream", "--root", root, "--evidence", evidence, "--write", "--commit",
               "--allowed-principal", PRINCIPAL, "--min-count", mincount]
        if use_model:
            cmd += model_args() + ["--now", datetime.datetime.now().astimezone().isoformat()]
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
