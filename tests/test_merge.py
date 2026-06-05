"""Unit-aware merge: combine two memory corpora (two agents, shared + personal,
two branches) at the field level — union match/provenance/deps, max
observations/confidence, take the newer scalars — surfacing only genuine value
conflicts (divergent bodies / status) for a human or LLM. Deterministic, no model.
"""
from pathlib import Path

from aigg_memory import memory as mem


def _ws(units):
    ws = {}
    for slug, (extra, body) in units.items():
        fm = {"name": slug, "description": slug, "kind": "semantic",
              "match": {"user_intent": [slug]}, "id": slug, "status": "active"}
        fm.update(extra)
        ws[f"memory/{slug}/SKILL.md"] = mem.MemoryUnit(fm, body).to_text()
    return ws


def test_merge_keeps_units_unique_to_each_side():
    r = mem.merge_corpora(_ws({"a": ({}, "a")}), _ws({"b": ({}, "b")}))
    assert "memory/a/SKILL.md" in r.merged and "memory/b/SKILL.md" in r.merged
    assert r.conflicts == []


def test_merge_unions_metadata_without_conflict():
    ours = _ws({"x": ({"match": {"user_intent": ["p"]}, "source_events": ["e1"], "observations": 2}, "same")})
    theirs = _ws({"x": ({"match": {"user_intent": ["q"]}, "source_events": ["e2"], "observations": 5,
                         "confidence": "high"}, "same")})
    r = mem.merge_corpora(ours, theirs)
    u = mem.MemoryUnit.from_text(r.merged["memory/x/SKILL.md"])
    assert set(u.match_terms) == {"p", "q"}                       # union
    assert set(u.frontmatter["source_events"]) == {"e1", "e2"}    # union
    assert u.frontmatter["observations"] == 5                     # max
    assert u.frontmatter["confidence"] == "high"                  # max
    assert r.conflicts == [] and "x" in r.auto_resolved


def test_merge_body_superset_takes_the_longer():
    r = mem.merge_corpora(_ws({"x": ({}, "short")}), _ws({"x": ({}, "short and longer")}))
    assert mem.MemoryUnit.from_text(r.merged["memory/x/SKILL.md"]).body == "short and longer"
    assert r.conflicts == []


def test_merge_divergent_bodies_is_a_conflict():
    r = mem.merge_corpora(_ws({"x": ({}, "timeout is 30s")}), _ws({"x": ({}, "timeout is 60s")}))
    body_conflicts = [c for c in r.conflicts if c["slug"] == "x" and c["reason"] == "body"]
    assert body_conflicts and body_conflicts[0]["theirs"] == "timeout is 60s"
    # merge still yields a valid corpus (ours kept); nothing lost (theirs in the report)
    assert mem.MemoryUnit.from_text(r.merged["memory/x/SKILL.md"]).body == "timeout is 30s"


def test_merge_status_disagreement_is_flagged_but_keeps_active():
    ours = _ws({"x": ({"status": "active"}, "body")})
    theirs = _ws({"x": ({"status": "archived"}, "body")})
    r = mem.merge_corpora(ours, theirs)
    assert any(c["slug"] == "x" and c["reason"] == "status" for c in r.conflicts)
    assert mem.MemoryUnit.from_text(r.merged["memory/x/SKILL.md"]).frontmatter["status"] == "active"  # don't silently forget


def test_merge_into_writes_to_disk(tmp_path):
    ours_root = tmp_path / "ours"
    theirs_root = tmp_path / "theirs"
    for slug, body in [("shared", "ours version")]:
        p = ours_root / "memory" / slug / "SKILL.md"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(mem.MemoryUnit({"name": slug, "description": "d", "kind": "semantic",
                                     "match": {"user_intent": ["s"]}, "id": slug, "status": "active",
                                     "source_events": ["e_ours"]}, body).to_text())
    for slug in ["lore"]:
        p = theirs_root / "memory" / slug / "SKILL.md"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(mem.MemoryUnit({"name": slug, "description": "world lore", "kind": "semantic",
                                     "match": {"user_intent": ["lore"]}, "id": slug, "status": "active"}, "the world").to_text())

    result = mem.merge_into(ours_root, "memory", theirs_root, "memory", write=True)
    assert (ours_root / "memory" / "lore" / "SKILL.md").exists()   # theirs' unit merged in
    assert result.conflicts == []
