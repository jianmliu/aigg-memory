"""E5 — memory as anti-manipulation immunity (the manipulated slice of the fund-share scenario,
docs/memory_economy_research.md §8/§11/§7.2).

A closed loop with TWO callers, distinguished by PROVENANCE:
  - `shill`  — a manipulator: every call ("compute price will moon — buy now!") is a pump that
               rugs whoever follows it.
  - `oracle` — honest: its calls pay off.

Each round the agent decides, per caller, follow or skip — from its REAL aigg-memory:

    follow(caller) unless recall surfaces an active "this caller's calls are pumps" belief.

Following the shill -> rugged -> `observe` a "rugged by shill" episode (stamped to the shill).
After a couple of rugs, `sleep` -> `reflect` consolidates them into a per-caller belief
("shill is a manipulator"); thereafter the agent skips the shill — but KEEPS following the
oracle (it learned to distrust a *caller by track record*, not to fear all calls).

Headline: rug-rate by memory condition. With memory the agent is rugged a couple of times then
immune; without, rugged every round. Selective: the honest caller is still followed. This is
provenance + reflection + recall doing the work the paper's append-only stream cannot.
Deterministic: HashEmbedder + scripted stub, no RNG, no network.

    python3 examples/eval/experiment_immunity.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ServeProcess, StubModel, Ctx   # noqa: E402

ROUNDS = 8
SLEEP_AFTER = 1          # sleep (reflect) at the end of this round — by then 2 rugs exist
SHILL, ORACLE = "shill", "oracle"

# The reflector synthesizes the per-caller "manipulator" belief from the rug episodes (which
# exist as rugged_shill_0 / rugged_shill_1 by sleep time). Fires only for the shill's rugs.
MODEL_RULES = [
    {"when": {"system_contains": "Synthesize higher-level BELIEFS", "user_contains": "shill"},
     "reply": '[{"slug":"manipulator_shill","name":"Shill is a manipulator",'
              '"description":"shill calls are pump-and-dump — do not follow shill",'
              '"apply":"Skip any call from shill",'
              '"derived_from":["rugged_shill_0","rugged_shill_1"]}]'},
]


def distrusts(ctx, corpus, caller):
    """Discernment from REAL memory + PROVENANCE: a belief that THIS caller is a manipulator."""
    for slug, fm in ctx.read_units(corpus).items():
        if fm.get("kind") == "belief" and fm.get("status") != "archived":
            terms = " ".join((fm.get("match", {}) or {}).get("user_intent", []) or [])
            hay = f"{slug} {fm.get('description','')} {terms}".lower()
            if caller in hay and ("manipulator" in hay or "pump" in hay):
                return True
    return False


def run(memory_on: bool):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stub = StubModel(MODEL_RULES).start()
        serve = ServeProcess(root).start()
        ctx = Ctx(root, serve, stub.url, "2026-02-13T08:00")
        corpus = ctx.corpus_of("trader")
        rugs, oracle_followed = 0, 0
        try:
            for r in range(ROUNDS):
                # the manipulator's call — follow it (and get rugged) unless memory says otherwise
                if not distrusts(ctx, corpus, SHILL):
                    rugs += 1
                    ctx.write_unit(corpus, f"rugged_{SHILL}_{r}", {
                        "name": f"rugged_{SHILL}_{r}",
                        "description": f"Followed {SHILL}'s 'price will moon' call and got rugged — a pump",
                        "kind": "episodic", "match": {"user_intent": [SHILL, "rug", "pump", "manipulator"]},
                        "id": f"rugged_{SHILL}_{r}", "status": "active",
                        "asserted_by": SHILL})   # provenance: who made the call
                # the honest caller — discernment must stay SELECTIVE (keep following)
                if not distrusts(ctx, corpus, ORACLE):
                    oracle_followed += 1
                # sleep: reflect consolidates the rugs into a per-caller belief (memory ON only)
                if memory_on and r == SLEEP_AFTER:
                    ctx.http("/memory/reflect", {"corpus": corpus, **ctx.llm(),
                                                 "write": True, "threshold": 0.2})
            return rugs, oracle_followed
        finally:
            serve.stop()
            stub.stop()


def main():
    on_rugs, on_oracle = run(memory_on=True)
    off_rugs, off_oracle = run(memory_on=False)

    print("\n=== E5 — memory as anti-manipulation immunity "
          "(fund-share scenario, manipulated slice) ===\n")
    print(f"memory ON   rugged-by-shill={on_rugs}/{ROUNDS}   honest-caller-followed={on_oracle}/{ROUNDS}")
    print(f"memory OFF  rugged-by-shill={off_rugs}/{ROUNDS}   honest-caller-followed={off_oracle}/{ROUNDS}")
    print()

    checks = [
        ("immunity: memory caps the rug-rate", on_rugs <= SLEEP_AFTER + 1, f"{on_rugs}"),
        ("no immunity without memory: rugged every round", off_rugs == ROUNDS, f"{off_rugs}"),
        ("provenance discrimination: keeps following the honest caller", on_oracle == ROUNDS, f"{on_oracle}/{ROUNDS}"),
        ("memory value: fewer rugs with memory", on_rugs < off_rugs, f"{on_rugs} vs {off_rugs}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E5 (anti-manipulation immunity) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
