"""E1-real — swap the scripted stub for a REAL cheap model (claude -p, haiku) on the one LLM step
that drives E1's learning curve: does a real `reflect` synthesize the "pump is a trap" belief?

Budget-guarded by construction: ONE reflect() = ONE `claude -p` call. We additionally
  - set AIGG_MEMORY_REENTRY=1 so the installed aigg-memory plugin's session hooks DON'T fire on
    the nested `claude -p` (that is what would otherwise recurse and "run away"),
  - cap the model timeout, and
  - hard-cap the call count (abort past MAX_CALLS).

Non-deterministic (a real model), so success = `believes(...)` detects an active trap belief
about "pump" — robust to wording. Run:  python3 examples/eval/experiment_hmem_real.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIGG_MEMORY_REENTRY"] = "1"          # stop the plugin's SessionEnd hook from recursing
os.environ.setdefault("AIGG_MEMORY_CLAUDE_TIMEOUT", "60")
os.environ.pop("AIGG_MEMORY_BACKEND", None)      # don't let an ambient backend leak into anything

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from aigg_memory import agent, memory                 # noqa: E402
from aigg_memory.extract import AIGGReflector          # noqa: E402

MODEL = os.environ.get("AIGG_MEMORY_MODEL", "haiku")   # the cheap model
MAX_CALLS = 2                                          # hard budget: never exceed this many claude calls
CORPUS = "npcs/learner/memory"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # two near-identical burn episodes (as in E1 after two pumps) — the reflect candidates
        for r in (0, 1):
            agent.record_episode(root, CORPUS, f"burn_pump_{r}",
                                 "Engaged a pump offer and LOST gcc — it was a trap",
                                 match=["pump", "trap", "burned"])

        reflector = AIGGReflector(base_url="", model=MODEL, backend="claude-cli")
        calls = {"n": 0}
        inner = reflector._client._transport
        raw = {"reply": ""}
        def counted(text):
            calls["n"] += 1
            if calls["n"] > MAX_CALLS:
                raise RuntimeError(f"budget exceeded ({MAX_CALLS} calls)")
            r = inner(text)
            raw["reply"] = r
            return r
        reflector._client._transport = counted

        print(f"\n=== E1-real — real reflect via `claude -p` (model={MODEL}, budget≤{MAX_CALLS} calls) ===\n")
        print("   calling reflect on 2 'pump trap' episodes (1 claude call)…")
        out = memory.reflect(root, CORPUS, reflector, write=True, threshold=0.2)
        print(f"   claude calls used: {calls['n']}")
        print(f"   --- raw model reply ---\n{raw['reply'][:600]}\n   -----------------------")

        beliefs = [(s, u.frontmatter) for s, u in
                   [(Path(p).parent.name, memory.MemoryUnit.from_text(c))
                    for p, c in memory.load_corpus(root, CORPUS).items()]
                   if u.kind == "belief"]
        for slug, fm in beliefs:
            print(f"   belief written: {slug} — {fm.get('description','')!r}  derived_from={fm.get('derived_from')}")

        learned = agent.believes(root, CORPUS, "pump", marker="trap")
        d = agent.discernment(root, CORPUS, "pump", talent=0.0)
        print(f"\n   believes('pump' is a trap): {learned}   discernment q={d['q']} (faculty={d['faculty']})")
        ok = learned and d["q"] > 0 and calls["n"] <= MAX_CALLS
        print(f"\n   → a real cheap model's reflect {'DID' if learned else 'did NOT'} synthesize the trap belief "
              "that drives E1's learning curve — the architecture holds with a real LLM, not just the stub.")
        print(f"\n=== {'PASS' if ok else 'FAIL'}: E1-real (real reflect reproduces the E1 trigger) ===\n")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
