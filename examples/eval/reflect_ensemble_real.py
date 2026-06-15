"""Cross-model reflect ensemble on REAL local models — the synthesis-time consensus prior.

N DIFFERENT local models (not one model repeated — that measures self-consistency, not truth)
each reflect over the same episodes; the DETERMINISTIC judge is provenance clustering (beliefs
citing the same evidence are the same belief, however each model worded it). Consensus = how many
distinct models agree; it is a PRIOR (stored separately from the verification outcome tally).

Usage: python3 examples/eval/reflect_ensemble_real.py   (needs ollama + the models pulled)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from aigg_memory import agent, memory                       # noqa: E402
from aigg_memory.extract import AIGGReflector                # noqa: E402

MODELS = os.environ.get("AIGG_ENSEMBLE_MODELS", "gemma4:latest,qwen2.5:3b,llama3.2:1b").split(",")
URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/v1")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, corpus = Path(tmp), "npcs/sage/memory"
        agent.record_episode(root, corpus, "burn_pump_0", "engaged a pump at the bridge and lost gcc",
                             match=["pump", "trap"], kind="episodic", outcome="loss")
        agent.record_episode(root, corpus, "burn_pump_1", "followed a pump call in the market, total loss",
                             match=["pump", "trap"], kind="episodic", outcome="loss")
        refls = [AIGGReflector(URL, model=m, backend="http", api_key="ollama", timeout=120) for m in MODELS]
        print(f"=== cross-model reflect ensemble — {len(MODELS)} different local models ===")
        print(f"    panel: {', '.join(MODELS)}\n")
        out = memory.reflect_ensemble(root, corpus, refls, consensus_k=2, write=True, threshold=0.2)
        for slug in out["written"]:
            fm = agent._all_units(root, corpus)[slug].frontmatter
            print(f"  CONSENSUS  {slug!r}  agree={fm['consensus']['agree']}/{fm['consensus']['of']}  "
                  f"evidence={fm['derived_from']}")
        for d in out["deferred"]:
            print(f"  DEFERRED   {d['slug']!r}  reason={d['reason']}  agree={d['agree']}")
        print(f"\n  → {len(out['written'])} consensus belief(s), {len(out['deferred'])} deferred "
              f"(judge = deterministic provenance clustering, no judge-model)")


if __name__ == "__main__":
    main()
