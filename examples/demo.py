"""A tiny end-to-end aigg-memory demo: a game NPC that remembers a player.

    python examples/demo.py

No external services, no LLM, no framework — just aigg-memory (only PyYAML).
It walks the whole memory cycle: encode → consolidate (Dream) → recall → navigate.
"""
import tempfile
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.index import select_and_count
from aigg_memory.store import EvidenceStore

ROOT = Path(tempfile.mkdtemp(prefix="aigg_demo_"))
EVIDENCE = ROOT / "evidence.jsonl"


def observe(payload):
    EvidenceStore(EVIDENCE, domain=mem.memory_domain()).record("observation", payload)


def line(title):
    print(f"\n{'─' * 60}\n{title}")


print(f"NPC '酒剑仙' remembers a player.   corpus: {ROOT}")

# 1) ENCODE — the player interacts; observations are recorded online (cheap).
#    (Each fact seen twice → strong enough for Dream to promote it.)
line("Day 1 — the player talks to the NPC; observations recorded")
for _ in range(2):
    observe({"slug": "player_youxia", "name": "游侠", "kind": "semantic",
             "description": "游侠是个好奇剑法的访客,论剑后好感升高",
             "match": ["游侠", "好感", "visitor"], "body": "游侠初见好奇剑法;再访论剑,好感升到高位。",
             "deps": ["concept_swordsmanship"]})        # this memory depends on the swordsmanship concept
for _ in range(2):
    observe({"slug": "concept_swordsmanship", "name": "剑法", "kind": "procedural",
             "description": "剑意源于心,醉中悟剑", "match": ["剑法", "剑意", "swordsmanship"],
             "body": "1. 静心  2. 观剑  3. 醉而忘形,剑随意动"})
print(f"  recorded {len([l for l in EVIDENCE.read_text().splitlines() if l.strip()])} observations")

# 2) CONSOLIDATE (Dream) — the NPC 'sleeps'; repeated observations become typed units.
line("Night — the NPC sleeps; Dream consolidation writes typed memory")
records = EvidenceStore(EVIDENCE, domain=mem.memory_domain()).load()
result = mem.consolidate_corpus(ROOT, records, write=True)
for path in result.written:
    print("  wrote", path)
print("\n  memory/player_youxia/SKILL.md:\n")
print("   " + (ROOT / "memory" / "player_youxia" / "SKILL.md").read_text().replace("\n", "\n   "))

# 3) RECALL — the player returns; the NPC pulls relevant memory for context.
#    Semantic recall + include_deps: querying "游侠来访" also pulls in the
#    swordsmanship prerequisite the player memory depends on, even though the
#    query never mentioned it.
line("Day 2 — the player returns; NPC recalls context for '游侠来访'")
units, total = select_and_count(ROOT, "memory", "游侠来访", retriever="semantic", include_deps=True)
for u in units:
    tag = "↳ dependency" if u.get("relation") == "dependency" else f"score {u['score']}"
    print(f"  • {u['name']} [{u['kind']}] ({tag})\n      {u['description']}")

# 4) NAVIGATE — the dependency graph (MemoryMakefile): what depends on what.
line("MemoryMakefile — the dependency graph (edit-time navigation)")
for slug, node in mem.build_memorymakefile(ROOT, "memory")["memories"].items():
    print(f"  {slug}: depends_on={node['depends_on']}  depended_by={node['depended_by']}")

print(f"\n{'─' * 60}\nDone. Inspect the corpus at: {ROOT}")
