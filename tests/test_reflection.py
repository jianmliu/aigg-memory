"""Reflection = the synthesis layer above Dream: from *facts* to *beliefs*. Dream
preserves facts; reflect GENERATES higher-level interpretations (`kind=belief`) and
records their provenance as `derived_from` edges — a subgraph of the MemoryMakefile.
A belief is never ground truth (no fact `asserted_by`, lower confidence), is revisable,
and is marked `stale` when a supporting fact changes (blast-radius reuse)."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGReflector, parse_reflections
from aigg_memory.index import CorpusIndex


def _unit(root: Path, slug, desc, match, **fm):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": match}, "id": slug, "status": "active"}
    f.update(fm)
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


# --- parse ---------------------------------------------------------------

def test_parse_reflections_tolerant() -> None:
    out = parse_reflections(
        '```json\n[{"slug":"b1","name":"B","description":"d","derived_from":["x","y"]}]\n```')
    assert out == [{"slug": "b1", "name": "B", "description": "d", "body": "",
                    "apply": "", "derived_from": ["x", "y"], "confidence": "medium"}]
    # an item with no derived_from (no cited sources) is dropped — a belief must cite evidence
    assert parse_reflections('[{"slug":"b","name":"B"}]') == []
    # an item with no slug is dropped
    assert parse_reflections('[{"name":"B","derived_from":["x"]}]') == []
    assert parse_reflections("junk") == []


def test_reflector_backend_stub() -> None:
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"on_a_quest","name":"On a quest","description":"d","derived_from":["f1","f2"]}]')
    beliefs = r.reflect([{"slug": "f1", "description": "visited 5 times"},
                         {"slug": "f2", "description": "always asks about swords"}])
    assert beliefs[0]["slug"] == "on_a_quest" and beliefs[0]["derived_from"] == ["f1", "f2"]


# --- reflect (generative pass) -------------------------------------------

def test_reflect_synthesizes_belief_with_edges(tmp_path: Path) -> None:
    _unit(tmp_path, "visits_often", "Player visited the sage five times", ["player", "visit", "sage"])
    _unit(tmp_path, "asks_swords", "Player always asks about swordsmanship", ["player", "sword", "ask"])
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"player_on_quest","name":"Player is on a sword quest",'
        '"description":"The player is questing to master the sword",'
        '"apply":"Offer sword training","derived_from":["visits_often","asks_swords"]}]')

    out = mem.reflect(tmp_path, "memory", r, threshold=0.0, write=True)
    assert "player_on_quest" in out["written"]

    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "player_on_quest" / "SKILL.md").read_text())
    assert u.kind == "belief"
    assert u.frontmatter["status"] == "candidate"          # needs-review, not auto-active
    assert u.frontmatter["asserted_by"] == "self"          # the agent's inference, not a fact
    assert "asserted_by" not in {"player", "owner"}        # never a ground-truth asserter
    assert sorted(u.frontmatter["derived_from"]) == ["asks_swords", "visits_often"]
    assert u.frontmatter["apply"] == "Offer sword training"


def test_reflect_drops_hallucinated_sources(tmp_path: Path) -> None:
    _unit(tmp_path, "fact_real", "A real fact about the player", ["player", "fact"])
    _unit(tmp_path, "fact_two", "Another real fact about the player", ["player", "fact"])
    # belief b1 cites a non-existent source -> dropped entirely; b2 cites a real one -> kept
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"b_bad","name":"bad","description":"d","derived_from":["ghost_fact"]},'
        '{"slug":"b_ok","name":"ok","description":"d","derived_from":["fact_real","ghost_fact"]}]')
    out = mem.reflect(tmp_path, "memory", r, threshold=0.0, write=True)

    assert out["written"] == ["b_ok"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "b_ok" / "SKILL.md").read_text())
    assert u.frontmatter["derived_from"] == ["fact_real"]   # the ghost source is filtered out


def test_reflect_dry_run_writes_nothing(tmp_path: Path) -> None:
    _unit(tmp_path, "f1", "fact one about the player", ["player", "one"])
    _unit(tmp_path, "f2", "fact two about the player", ["player", "two"])
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"belief_x","name":"x","description":"d","derived_from":["f1","f2"]}]')
    out = mem.reflect(tmp_path, "memory", r, threshold=0.0, write=False)

    assert out["reflections"] and out["written"] == []
    assert not (tmp_path / "memory" / "belief_x").exists()


# --- graph: derived_from compiles, doesn't pollute depends_on ------------

def test_derived_from_compiles_into_graph(tmp_path: Path) -> None:
    _unit(tmp_path, "fact_a", "fact a about the player", ["player", "a"])
    _unit(tmp_path, "fact_b", "fact b about the player", ["player", "b"])
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"belief_q","name":"q","description":"d","derived_from":["fact_a","fact_b"]}]')
    mem.reflect(tmp_path, "memory", r, threshold=0.0, write=True)

    idx = CorpusIndex(tmp_path, "memory")
    idx.sync()
    assert idx.derived_from("belief_q") == ["fact_a", "fact_b"]   # belief -> supporting facts
    assert idx.supports("fact_a") == ["belief_q"]                 # reverse: facts -> belief
    assert idx.depends_on("belief_q") == []                       # does NOT pollute depends_on


def test_belief_recall_pulls_supporting_facts(tmp_path: Path) -> None:
    _unit(tmp_path, "fact_a", "fact a about the player", ["player", "alpha"])
    _unit(tmp_path, "fact_b", "fact b about the player", ["player", "beta"])
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"belief_quest","name":"quest belief","description":"d",'
        '"derived_from":["fact_a","fact_b"]}]')
    mem.reflect(tmp_path, "memory", r, threshold=0.0, write=True)

    units, _ = __import__("aigg_memory.index", fromlist=["select_and_count"]).select_and_count(
        tmp_path, "memory", "quest belief", include_deps=True)
    slugs = {u["slug"] for u in units}
    assert "belief_quest" in slugs
    assert {"fact_a", "fact_b"} <= slugs        # the supporting facts ride along


# --- invalidation: stale propagation -------------------------------------

def test_mark_stale_dependents(tmp_path: Path) -> None:
    _unit(tmp_path, "fact_a", "fact a", ["a"])
    _unit(tmp_path, "belief_z", "a belief resting on fact a", ["z"],
          kind="belief", status="candidate", asserted_by="self", derived_from=["fact_a"])

    marked = mem.mark_stale_dependents(tmp_path, "memory", ["fact_a"])
    assert marked == ["belief_z"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "belief_z" / "SKILL.md").read_text())
    assert u.frontmatter["stale"] is True
    assert u.frontmatter["status"] == "candidate"   # still active, just flagged (not a status)


def test_reconcile_marks_derived_belief_stale(tmp_path: Path) -> None:
    _unit(tmp_path, "loc_sh", "User lives in Shanghai", ["lives", "location"])
    _unit(tmp_path, "loc_bj", "User lives in Beijing", ["lives", "location"])
    rr = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"belief_home","name":"home","description":"d","derived_from":["loc_sh"]}]')
    mem.reflect(tmp_path, "memory", rr, threshold=0.0, write=True)

    judge = type("J", (), {"judge": staticmethod(lambda a, b:
        {"relation": "temporal", "current": "loc_bj", "reason": "moved"})})()
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")

    assert "belief_home" in out["stale_marked"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "belief_home" / "SKILL.md").read_text())
    assert u.frontmatter["stale"] is True

    # a re-reflect clears the stale flag (the belief is regenerated)
    mem.reflect(tmp_path, "memory", rr, threshold=0.0, write=True)
    u2 = mem.MemoryUnit.from_text((tmp_path / "memory" / "belief_home" / "SKILL.md").read_text())
    assert not u2.frontmatter.get("stale")


def test_reflect_never_rewrites_locked_belief(tmp_path: Path) -> None:
    _unit(tmp_path, "fact_a", "fact a", ["a"])
    _unit(tmp_path, "belief_locked", "owner cornerstone belief", ["core"],
          kind="belief", locked=True, derived_from=["fact_a"])
    # reflect proposes an update to the locked belief slug -> must be refused
    r = AIGGReflector(base_url="x", transport=lambda t:
        '[{"slug":"belief_locked","name":"HIJACK","description":"overwritten",'
        '"derived_from":["fact_a"]}]')
    out = mem.reflect(tmp_path, "memory", r, threshold=0.0, write=True)

    assert "belief_locked" not in out["written"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "belief_locked" / "SKILL.md").read_text())
    assert u.frontmatter["name"] == "belief_locked"   # untouched
    # and a locked belief is never marked stale either
    mem.mark_stale_dependents(tmp_path, "memory", ["fact_a"])
    u2 = mem.MemoryUnit.from_text((tmp_path / "memory" / "belief_locked" / "SKILL.md").read_text())
    assert not u2.frontmatter.get("stale")
