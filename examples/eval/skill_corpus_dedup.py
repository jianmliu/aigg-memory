"""Validation #1 from docs/aigg_skill_design.md — dedup rate on a REAL skill registry.

Imports a tree of Agent-Skills `SKILL.md` files (default: the tier1+tier2 slice of the local
skill-corpus) into an aigg-memory corpus as `kind=procedural, status=candidate` units, then runs
the kernel's `compact` (dry-run) at several thresholds and reports the near-duplicate clusters.

Deterministic and model-free: the default hash embedder embeds the unit's *routing surface*
(name + description + match terms) — exactly the surface a registry router sees, so a cluster
here means "these skills are indistinguishable to routing", the operative sense of duplicate.

Usage:  python3 examples/eval/skill_corpus_dedup.py [corpus_root ...]
"""
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from aigg_memory.memory import MemoryUnit, compact_corpus, load_corpus  # noqa: E402

DEFAULT_TREES = ["/Volumes/T7-Data/skill-corpus/tier1-official",
                 "/Volumes/T7-Data/skill-corpus/tier2-community"]
THRESHOLDS = [0.95, 0.90, 0.85, 0.80]


def _frontmatter(text: str) -> dict:
    """Parse just name/description out of an Agent-Skills SKILL.md (tolerant, no yaml dep)."""
    fm = {}
    if text.startswith("---"):
        for line in text[3:].split("\n---", 1)[0].splitlines():
            m = re.match(r"^(name|description):\s*(.+)$", line.strip())
            if m:
                fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm


def import_tree(tree: Path, root: Path, corpus: str) -> int:
    n = 0
    for p in sorted(tree.rglob("SKILL.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)
        name = fm.get("name") or p.parent.name
        registry = p.relative_to(tree).parts[0] if len(p.relative_to(tree).parts) > 1 else tree.name
        slug = re.sub(r"[^a-z0-9_]+", "_", f"{registry}__{name}".lower()).strip("_")
        terms = [t for t in re.split(r"[-_\s]+", name.lower()) if len(t) > 2][:6]
        unit = {"name": name, "description": fm.get("description", ""), "kind": "procedural",
                "match": {"user_intent": terms or [name.lower()]}, "id": slug,
                "status": "candidate", "asserted_by": registry}
        out = root / corpus / slug / "SKILL.md"
        if out.exists():    # same registry+name twice in a tree -> first wins, count skipped
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        body = text.split("\n---", 1)[-1] if text.startswith("---") else text
        out.write_text(MemoryUnit(unit, body[:2000]).to_text(), encoding="utf-8")
        n += 1
    return n


def main() -> None:
    trees = [Path(a) for a in sys.argv[1:]] or [Path(t) for t in DEFAULT_TREES]
    with tempfile.TemporaryDirectory() as tmp:
        root, corpus = Path(tmp), "skills"
        total = sum(import_tree(t, root, corpus) for t in trees if t.exists())
        print(f"\n=== skill-corpus dedup (validation #1) — {total} skills imported ===\n")
        for th in THRESHOLDS:
            t0 = time.time()
            res = compact_corpus(root, corpus, threshold=th, write=False)
            dt = time.time() - t0
            groups = res.merged
            dupes = sum(len(g["folded"]) for g in groups)
            print(f"threshold {th:.2f}:  {len(groups):3d} near-duplicate groups   "
                  f"({dupes} redundant units)   [{dt:.1f}s]")
            for g in groups[:8]:
                print(f"   · {g['into']}  ⇐  {', '.join(g['folded'])}")
            if len(groups) > 8:
                print(f"   … and {len(groups) - 8} more groups")
            print()


if __name__ == "__main__":
    main()
