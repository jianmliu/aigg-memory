"""Content-quality improvements borrowed from Claude Code's auto-memory:
  ① `apply` — actionable guidance ("how to use this fact"), surfaced on recall so a
     recalled memory is directly usable, not just a bare fact.
  ② semantic slugs — the heuristic extractor emits readable slugs (prefer_dark_mode),
     not fact_<hash>, keeping units hand-editable / navigable.
  ③ `origin_session` — which conversation a memory came from (provenance to the chat)."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import HeuristicExtractor, ingest_transcript
from aigg_memory.index import select_and_count
from aigg_memory.store import EvidenceStore


def _obs(root: Path, slug, **extra):
    store = EvidenceStore(root / "ev.jsonl", domain=mem.memory_domain())
    s = {"slug": slug, "name": slug, "kind": "semantic", "description": f"d {slug}", "match": [slug], "body": slug}
    s.update(extra)
    store.record("observation", s)
    return store.load()


# ① apply — actionable guidance

def test_apply_carried_to_unit_and_editable(tmp_path: Path) -> None:
    records = _obs(tmp_path, "dark", apply="Default to dark mode when a UI choice is open.")
    mem.consolidate_corpus(tmp_path, records, write=True, min_promote_count=1)
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "dark" / "SKILL.md").read_text())
    assert u.frontmatter["apply"] == "Default to dark mode when a UI choice is open."
    mem.edit_unit(tmp_path, "memory", "dark", apply="changed guidance")
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "dark" / "SKILL.md").read_text())
    assert u.frontmatter["apply"] == "changed guidance"


def test_apply_surfaced_on_recall(tmp_path: Path) -> None:
    records = _obs(tmp_path, "concise", apply="Keep answers short and skip preamble.")
    mem.consolidate_corpus(tmp_path, records, write=True, min_promote_count=1)
    units, _ = select_and_count(tmp_path, "memory", "concise", retriever="keyword")
    assert units and units[0].get("apply") == "Keep answers short and skip preamble."


def test_merge_carries_newer_apply() -> None:
    out = mem._merge_frontmatter({"name": "x", "apply": "old", "updated": "2025-01-01"},
                                 {"name": "x", "apply": "new", "updated": "2025-02-01"})
    assert out["apply"] == "new"


# ② semantic slugs from the heuristic

def test_heuristic_slug_is_semantic_not_hash() -> None:
    obs = HeuristicExtractor().extract("I prefer dark mode")
    assert obs
    slug = obs[0]["slug"]
    assert not slug.startswith("fact_")            # was fact_<hash>
    assert "dark" in slug or "prefer" in slug      # derived from the content


# ③ origin_session provenance

def test_origin_session_flows_to_unit(tmp_path: Path) -> None:
    recs = ingest_transcript("user: remember that I prefer tabs", HeuristicExtractor(),
                             tmp_path / "ev.jsonl", origin_session="sess-99")
    assert recs and recs[0]["summary"]["origin_session"] == "sess-99"
    mem.consolidate_corpus(tmp_path, EvidenceStore(tmp_path / "ev.jsonl", domain=mem.memory_domain()).load(),
                           write=True, min_promote_count=1)
    units = list((tmp_path / "memory").glob("*/SKILL.md"))
    assert units
    assert mem.MemoryUnit.from_text(units[0].read_text()).frontmatter.get("origin_session") == "sess-99"
