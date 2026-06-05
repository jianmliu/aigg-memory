"""Compaction = automatic merge + defragmentation + redundancy removal.

An offline pass that clusters near-duplicate units by semantic similarity, folds
each cluster into one canonical unit (union of match/provenance, supersedes
records what was folded), and removes the redundant files. App-triggered, like
Dream; conservative by a high similarity threshold; dry-run by default.
"""
from pathlib import Path

from aigg_memory import memory as mem


def _unit(root: Path, slug, desc, match, kind="semantic", observations=1, body="b", status="active"):
    fm = {"name": slug, "description": desc, "kind": kind, "match": {"user_intent": match},
          "id": slug, "status": status, "observations": observations, "source_events": [f"ev_{slug}"]}
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")


def test_compact_merges_near_duplicates(tmp_path: Path) -> None:
    # two near-identical units about the budget + one unrelated
    _unit(tmp_path, "budget_a", "token budget contract", ["token budget"], observations=3, body="budgets and cost")
    _unit(tmp_path, "budget_b", "token budget contract", ["token budget", "cost"], observations=2, body="budgets and cost")
    _unit(tmp_path, "weather", "weather forecast", ["weather"], body="sunny")

    # dry-run finds the cluster, writes nothing
    dry = mem.compact_corpus(tmp_path, threshold=0.8, write=False)
    assert any(len(c) == 2 for c in dry.clusters) and dry.written == []
    assert (tmp_path / "memory" / "budget_b" / "SKILL.md").exists()

    result = mem.compact_corpus(tmp_path, threshold=0.8, write=True)
    # the two budget units folded into one canonical (the one with more observations)
    assert result.merged and result.merged[0]["into"] == "budget_a"
    assert result.merged[0]["folded"] == ["budget_b"]
    assert not (tmp_path / "memory" / "budget_b" / "SKILL.md").exists()   # redundant file removed
    assert (tmp_path / "memory" / "weather" / "SKILL.md").exists()        # unrelated untouched

    canon = mem.MemoryUnit.from_text((tmp_path / "memory" / "budget_a" / "SKILL.md").read_text(encoding="utf-8"))
    assert set(canon.match_terms) == {"token budget", "cost"}             # match unioned
    assert "budget_b" in canon.frontmatter["supersedes"]                  # provenance of the fold
    assert set(canon.frontmatter["source_events"]) == {"ev_budget_a", "ev_budget_b"}  # evidence unioned


def test_compact_does_not_merge_across_kinds(tmp_path: Path) -> None:
    _unit(tmp_path, "sem", "sword theory", ["sword"], kind="semantic", body="the sword")
    _unit(tmp_path, "proc", "sword theory", ["sword"], kind="procedural", body="the sword")
    result = mem.compact_corpus(tmp_path, threshold=0.8, write=True)
    assert result.merged == []                                           # different kinds never merge
    assert (tmp_path / "memory" / "sem" / "SKILL.md").exists()
    assert (tmp_path / "memory" / "proc" / "SKILL.md").exists()


def test_compact_leaves_distinct_units_alone(tmp_path: Path) -> None:
    _unit(tmp_path, "a", "alpha topic", ["alpha"], body="alpha")
    _unit(tmp_path, "b", "beta topic", ["beta"], body="beta")
    result = mem.compact_corpus(tmp_path, threshold=0.8, write=True)
    assert result.merged == [] and result.removed == []
