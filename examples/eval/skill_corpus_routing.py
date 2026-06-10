"""Validation #2 from docs/aigg_skill_design.md — routing quality on a REAL skill registry.

Reuses the gold-labelled tasks from skill-corpus/skill-retrieval-bench (9 task intents, each with
one gold skill) and asks: given the kernel's `select` over a pool of real skills, does the gold
skill come back — and how does precision degrade when the pool grows from the curated 248 to the
full ~4.4k community corpus (distractor robustness)?

Arms (all the kernel's own retrievers, `select_and_count(retriever=…)`):
  keyword          — term scoring over the routing surface
  semantic-hash    — cosine over the zero-dep hash embedder (the kernel default)
  hybrid-hash      — keyword + semantic merged
  semantic-minilm  — cosine over a real embedder (all-MiniLM-L6-v2), if installed

Prior reference points from the bench's own PoC (pool=226): keyword 1/9, MiniLM 8/9, oracle 9/9.

Usage: python3 examples/eval/skill_corpus_routing.py
"""
import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_corpus_dedup import import_tree           # noqa: E402
from aigg_memory.index import select_and_count       # noqa: E402

CORPUS_ROOT = Path("/Volumes/T7-Data/skill-corpus")
TASKS = CORPUS_ROOT / "skill-retrieval-bench" / "tasks.jsonl"
SMALL = ["tier1-official", "tier2-community"]
BIG = SMALL + ["tier3-community-bulk"]
K = 3   # route() returns a capped closure of <=3 (spec S2)


def _slug_of_gold(gold: str) -> str:
    # "skill.hermes.humanizer" -> "hermes__humanizer" (the importer's slug convention)
    parts = gold.split(".")
    return re.sub(r"[^a-z0-9_]+", "_", f"{parts[-2]}__{parts[-1]}".lower()).strip("_")


def run_pool(name: str, trees, tasks, arms) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, corpus = Path(tmp), "skills"
        n = sum(import_tree(CORPUS_ROOT / t, root, corpus) for t in trees)
        print(f"\n--- pool: {name} ({n} skills) ---")
        print(f"{'arm':18} {'P@1':>5} {'R@'+str(K):>5} {'MRR':>6}   avg query")
        for arm, retriever, embedder in arms:
            hits1 = hitsk = 0
            mrr = 0.0
            t0 = time.time()
            for t in tasks:
                units, _ = select_and_count(root, corpus, t["request"], n_best=K,
                                            kinds=["procedural"], retriever=retriever,
                                            embedder=embedder)
                ranked = [u["slug"] for u in units]
                gold = _slug_of_gold(t["gold"])
                if ranked[:1] == [gold]:
                    hits1 += 1
                if gold in ranked:
                    hitsk += 1
                    mrr += 1.0 / (ranked.index(gold) + 1)
            dt = (time.time() - t0) / len(tasks)
            print(f"{arm:18} {hits1:>3}/{len(tasks)} {hitsk:>3}/{len(tasks)} {mrr/len(tasks):>6.2f}   {dt:>6.2f}s")


def main() -> None:
    tasks = [json.loads(l) for l in TASKS.read_text().splitlines() if l.strip()]
    arms = [("keyword", "keyword", None),
            ("semantic-hash", "semantic", None),
            ("hybrid-hash", "hybrid", None)]
    try:
        from aigg_memory.embed import get_embedder
        arms.append(("semantic-minilm", "semantic", get_embedder("all-MiniLM-L6-v2")))
    except Exception as exc:
        print(f"[minilm unavailable: {exc}]")
    print(f"=== skill routing (validation #2) — {len(tasks)} gold tasks, top-{K} ===")
    run_pool("tier1+2 (curated)", SMALL, tasks, arms)
    run_pool("tier1+2+3 (full)", BIG, tasks, arms)


if __name__ == "__main__":
    main()
