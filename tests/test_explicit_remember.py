"""Explicit 'remember X' should land immediately — a user who says "remember this"
has confirmed it, so it shouldn't wait for repetition. consolidate_corpus exposes
min_promote_count so the explicit path uses 1 while ambient capture keeps the
repetition gate (default 2)."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.store import EvidenceStore


def _record_observation(root: Path, slug: str):
    store = EvidenceStore(root / "evidence.jsonl", domain=mem.memory_domain())
    store.record("observation", {
        "slug": slug, "name": slug, "kind": "semantic",
        "description": f"User prefers {slug}", "match": [slug], "body": f"User prefers {slug}."})
    return store.load()


def test_single_observation_not_promoted_by_default(tmp_path: Path) -> None:
    records = _record_observation(tmp_path, "concise")
    result = mem.consolidate_corpus(tmp_path, records, write=True)            # default gate = 2
    assert not (tmp_path / "memory" / "concise" / "SKILL.md").exists()


def test_single_observation_promoted_with_min_count_1(tmp_path: Path) -> None:
    records = _record_observation(tmp_path, "concise")
    result = mem.consolidate_corpus(tmp_path, records, write=True, min_promote_count=1)
    unit_file = tmp_path / "memory" / "concise" / "SKILL.md"
    assert unit_file.exists()
    unit = mem.MemoryUnit.from_text(unit_file.read_text())
    assert unit.frontmatter["status"] == "active" and "concise" in unit.match_terms
