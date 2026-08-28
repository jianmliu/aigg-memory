"""Confidence-weighted recall — the aigg answer to Headlong's recency-decay compaction: rank
recalled units by VERIFIED CORRECTNESS, not age. A verified-true belief outranks an unverified
one; a refuted (stale) belief is dropped by default. Unverified carries the 0.5 Laplace prior.
"""
from pathlib import Path

from aigg_memory import agent
from aigg_memory.memory import MemoryUnit


def _belief(root, corpus, slug, *, confidence=None, stale=False):
    fm = {"name": slug, "description": "pump offers are traps", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": slug, "status": "active", "asserted_by": "self"}
    if confidence is not None:
        fm["verification"] = {"hits": 3, "misses": 0, "confidence": confidence}
    if stale:
        fm["stale"] = True
    p = root / corpus / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(MemoryUnit(fm, "pump is a trap").to_text(), encoding="utf-8")


def test_recall_ranks_by_verified_confidence(tmp_path):
    corpus = "npcs/me/memory"
    _belief(tmp_path, corpus, "trap_high", confidence=0.85)   # verified-true
    _belief(tmp_path, corpus, "trap_prior")                    # unverified -> 0.5 prior
    _belief(tmp_path, corpus, "trap_stale", stale=True)        # refuted
    out = agent.recall(tmp_path, corpus, "pump", kinds=["belief"], n_best=5)
    slugs = [u["slug"] for u in out]
    assert slugs[0] == "trap_high"                             # correctness beats the prior
    assert "trap_prior" in slugs
    assert "trap_stale" not in slugs                           # refuted dropped by default
    assert out[0]["confidence"] == 0.85


def test_include_stale_surfaces_refuted_last(tmp_path):
    corpus = "npcs/me/memory"
    _belief(tmp_path, corpus, "trap_high", confidence=0.85)
    _belief(tmp_path, corpus, "trap_stale", stale=True, confidence=0.2)
    out = agent.recall(tmp_path, corpus, "pump", kinds=["belief"], include_stale=True)
    slugs = [u["slug"] for u in out]
    assert slugs == ["trap_high", "trap_stale"]               # refuted included but ranked last


def test_unverified_uses_the_prior(tmp_path):
    corpus = "npcs/me/memory"
    _belief(tmp_path, corpus, "trap_prior")
    out = agent.recall(tmp_path, corpus, "pump", kinds=["belief"])
    assert out and out[0]["confidence"] == 0.5                # (0+1)/(0+0+2)


def test_recall_endpoint(tmp_path: Path) -> None:
    from aigg_memory.server import dispatch
    corpus = "npcs/me/memory"
    _belief(tmp_path, corpus, "trap_high", confidence=0.85)
    _belief(tmp_path, corpus, "trap_stale", stale=True)
    status, env = dispatch("POST", "/memory/recall",
                           {"corpus": corpus, "request": "pump", "kinds": ["belief"]}, tmp_path)
    assert status == 200 and env["ok"]
    slugs = [u["slug"] for u in env["data"]["units"]]
    assert slugs == ["trap_high"]                            # stale dropped, verified surfaced
    status, _ = dispatch("POST", "/memory/recall", {"corpus": corpus}, tmp_path)
    assert status == 400                                     # request required
