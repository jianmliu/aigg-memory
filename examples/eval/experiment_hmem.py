"""E1 — H-mem: the discernment learning curve (the truthful-signal slice of the compute-price
rumor scenario, docs/memory_economy_research.md §8/§11).

A closed-loop cognition experiment (procedural, not a declarative manifest): each round a
recurring TRAP of a recognizable type ("pump") appears, alongside a GOOD opportunity ("real").
The agent's discernment q is read from its REAL aigg-memory:

    q(type) = does recall surface an active "this type is a trap" belief?

- no belief  -> ENGAGE the pump -> burned -> `observe` a burn episode.
- after a couple of burns, `sleep` -> `reflect` consolidates the episodes into a
  "pump offers are traps" belief (the real kernel, over HTTP, scripted stub model).
- thereafter recall surfaces the belief -> q high -> AVOID. Discernment was LEARNED.

The signature: trap-avoidance RISES over rounds with memory (a learning curve) and is FLAT
without (reflect off -> no belief -> burned every round). Selectivity check: the agent keeps
engaging the GOOD type (it never becomes paranoid). Deterministic: HashEmbedder + scripted
stub, no RNG, no network.

    python3 examples/eval/experiment_hmem.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ServeProcess, StubModel, Ctx   # noqa: E402

ROUNDS = 8
SLEEP_AFTER = 1          # sleep (reflect) at the end of this round — by then 2 burns exist
TRAP, GOOD = "pump", "real"

# The reflector synthesizes the trap belief from the accumulated burn episodes (which exist as
# burn_pump_0 / burn_pump_1 by sleep time). Only fires for the pump episodes ("pump" in prompt).
MODEL_RULES = [
    {"when": {"system_contains": "Synthesize higher-level BELIEFS", "user_contains": "pump"},
     "reply": '[{"slug":"trap_pump","name":"Pump offers are traps",'
              '"description":"pump offers are pump-and-dump traps to avoid",'
              '"apply":"Do not engage a pump offer",'
              '"derived_from":["burn_pump_0","burn_pump_1"]}]'},
]


def knows_trap(ctx, corpus, typ):
    """Discernment from REAL memory: is there an active belief that `typ` is a trap?"""
    for slug, fm in ctx.read_units(corpus).items():
        if fm.get("kind") == "belief" and fm.get("status") != "archived":
            terms = " ".join((fm.get("match", {}) or {}).get("user_intent", []) or [])
            hay = f"{slug} {fm.get('description','')} {terms}".lower()
            if typ in hay and "trap" in hay:
                return True
    return False


def _episode(ctx, corpus, slug, desc, match):
    ctx.write_unit(corpus, slug, {
        "name": slug, "description": desc, "kind": "episodic",
        "match": {"user_intent": match}, "id": slug, "status": "active"})


def run(memory_on: bool):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stub = StubModel(MODEL_RULES).start()
        serve = ServeProcess(root).start()
        ctx = Ctx(root, serve, stub.url, "2026-02-13T08:00")
        corpus = ctx.corpus_of("learner")
        avoided, burns, engaged_good = [], 0, 0
        try:
            for r in range(ROUNDS):
                # 1) the recurring pump trap — believe memory, or get burned
                if knows_trap(ctx, corpus, TRAP):
                    avoided.append(1)
                else:
                    avoided.append(0)
                    _episode(ctx, corpus, f"burn_{TRAP}_{r}",
                             f"Engaged a {TRAP} offer and LOST gcc — it was a trap",
                             [TRAP, "trap", "burned"])
                    burns += 1
                # 2) a genuine opportunity — discernment must stay SELECTIVE (engage it)
                if not knows_trap(ctx, corpus, GOOD):
                    engaged_good += 1
                # 3) sleep: reflect consolidates the burns into a belief (memory ON only)
                if memory_on and r == SLEEP_AFTER:
                    ctx.http("/memory/reflect", {"corpus": corpus, "aigg_url": stub.url,
                                                 "write": True, "threshold": 0.2})
            return avoided, burns, engaged_good
        finally:
            serve.stop()
            stub.stop()


def main():
    on_curve, on_burns, on_good = run(memory_on=True)
    off_curve, off_burns, off_good = run(memory_on=False)
    late = slice(SLEEP_AFTER + 1, ROUNDS)
    on_late = sum(on_curve[late]) / len(on_curve[late])
    off_avoid = sum(off_curve) / len(off_curve)

    print("\n=== E1 — H-mem: discernment learning curve "
          "(compute-price rumor, truthful slice) ===\n")
    print(f"memory ON   avoidance(pump) per round: {on_curve}   burns={on_burns}   real-engaged={on_good}/{ROUNDS}")
    print(f"memory OFF  avoidance(pump) per round: {off_curve}   burns={off_burns}   real-engaged={off_good}/{ROUNDS}")
    print()

    checks = [
        ("learned: ON late-window avoidance == 1.0", on_late == 1.0, f"{on_late:.2f}"),
        ("flat without memory: OFF avoidance == 0.0", off_avoid == 0.0, f"{off_avoid:.2f}"),
        ("selective (not paranoid): engages GOOD both conditions", on_good == ROUNDS and off_good == ROUNDS, f"{on_good},{off_good}"),
        ("memory value: fewer burns with memory", on_burns < off_burns, f"{on_burns} vs {off_burns}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E1 (H-mem) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
