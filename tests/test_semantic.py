"""Semantic retrieval over the index's vectors table.

The default embedder is a deterministic, zero-dependency feature-hashing embedder
(lexical + character-bigram overlap — catches morphological / CJK variants that
exact-substring keyword matching misses). Real semantics is an opt-in extra.
"""
from pathlib import Path

import pytest

from aigg_memory import memory as mem
from aigg_memory.embed import HashEmbedder, get_embedder
from aigg_memory.index import CorpusIndex, select_and_count


def _unit(root: Path, slug, desc, match, kind="semantic", body="b", status="active"):
    fm = {"name": slug, "description": desc, "kind": kind,
          "match": {"user_intent": match}, "id": slug, "status": status}
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")


def test_semantic_recall_finds_variants_keyword_misses(tmp_path: Path) -> None:
    _unit(tmp_path, "budget", "token budget contract", ["token budget"], body="about budgets and cost")
    _unit(tmp_path, "weather", "weather forecast", ["weather"], body="sunny tomorrow")

    # keyword: the unit's term "token budget" is not a substring of "budgets" -> miss
    kw, _ = select_and_count(tmp_path, "memory", "how do budgets work", retriever="keyword")
    assert "budget" not in [u["name"] for u in kw]

    # semantic (hash): shared features (budget/budgets bigrams) -> hit
    sem, _ = select_and_count(tmp_path, "memory", "how do budgets work", retriever="semantic")
    assert sem and sem[0]["name"] == "budget"


def test_semantic_kind_filter_and_archived_excluded(tmp_path: Path) -> None:
    _unit(tmp_path, "proc", "sword technique steps", ["sword"], kind="procedural", body="grip the sword")
    _unit(tmp_path, "fact", "sword theory", ["sword"], kind="semantic", body="the way of the sword")
    _unit(tmp_path, "old", "retired sword master", ["sword"], status="archived", body="sword")

    sem, _ = select_and_count(tmp_path, "memory", "tell me about the sword", retriever="semantic", kinds=["semantic"])
    names = [u["name"] for u in sem]
    assert "fact" in names and "proc" not in names and "old" not in names


def test_semantic_with_include_deps(tmp_path: Path) -> None:
    _unit(tmp_path, "token_concept", "what a token is", ["token"], body="a token is a unit")
    p = tmp_path / "memory" / "budget" / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = {"name": "budget", "description": "token budget contract", "kind": "semantic",
          "match": {"user_intent": ["token budget"]}, "id": "budget", "status": "active",
          "deps": ["token_concept"]}
    p.write_text(mem.MemoryUnit(fm, "about budgets").to_text(), encoding="utf-8")

    units, _ = select_and_count(tmp_path, "memory", "budgets", retriever="semantic", include_deps=True)
    names = [u["name"] for u in units]
    assert "budget" in names and "token_concept" in names  # prerequisite pulled in


def test_default_embedder_is_hash_real_semantics_is_gated() -> None:
    assert isinstance(get_embedder(), HashEmbedder)
    try:
        import sentence_transformers  # noqa: F401
        installed = True
    except ImportError:
        installed = False
    if not installed:
        with pytest.raises(RuntimeError):
            get_embedder("all-MiniLM-L6-v2")  # the embedding extra is required


def test_vectors_persist_in_index(tmp_path: Path) -> None:
    _unit(tmp_path, "x", "alpha beta", ["alpha"], body="body")
    idx = CorpusIndex(tmp_path, "memory")
    idx.embed(HashEmbedder())
    import sqlite3
    con = sqlite3.connect(str(idx.db_path))
    assert con.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 1
    con.close()
