"""reconcile = the orchestration of 'a new statement updates memory': cheap semantic
similarity narrows candidate pairs, an LLM judge says how they relate and which is
now true, and we route — correction (old was WRONG → archive) vs temporal change (old
was true BEFORE → archive + valid_to, new gets valid_from) vs none vs uncertain
(→ needs_review, don't guess). Reuses the contradiction-detection machinery; adds the
correction/temporal split and direction (which fact is current)."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGReconciler, parse_reconciliation


def _unit(root: Path, slug, desc, match, **fm):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": match}, "id": slug, "status": "active"}
    f.update(fm)
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


def test_parse_reconciliation_tolerant() -> None:
    assert parse_reconciliation('```json\n{"relation":"temporal","current":"b","reason":"moved"}\n```') == \
        {"relation": "temporal", "current": "b", "reason": "moved"}
    assert parse_reconciliation("junk") == {"relation": "uncertain", "current": "", "reason": ""}
    # an unknown relation degrades to uncertain (defer, don't guess)
    assert parse_reconciliation('{"relation":"whatever","current":"b"}')["relation"] == "uncertain"


def test_correction_archives_the_wrong_one(tmp_path: Path) -> None:
    _unit(tmp_path, "name_old", "User's name is Alexander", ["name"])
    _unit(tmp_path, "name_new", "User's name is Alex", ["name"])
    judge = AIGGReconciler(base_url="x", transport=lambda t:
        '{"relation":"correction","current":"name_new","reason":"corrected"}')
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")

    assert out["reconciled"] and out["reconciled"][0]["relation"] == "correction"
    old = mem.MemoryUnit.from_text((tmp_path / "memory" / "name_old" / "SKILL.md").read_text())
    new = mem.MemoryUnit.from_text((tmp_path / "memory" / "name_new" / "SKILL.md").read_text())
    assert old.frontmatter["status"] == "archived" and old.frontmatter["superseded_by"] == "name_new"
    assert "name_old" in new.frontmatter["supersedes"]
    assert "valid_to" not in old.frontmatter            # a correction is not a temporal change


def test_temporal_change_sets_validity(tmp_path: Path) -> None:
    _unit(tmp_path, "loc_sh", "User lives in Shanghai", ["lives", "location"])
    _unit(tmp_path, "loc_bj", "User lives in Beijing", ["lives", "location"])
    judge = AIGGReconciler(base_url="x", transport=lambda t:
        '{"relation":"temporal","current":"loc_bj","reason":"moved"}')
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")

    assert out["reconciled"][0]["relation"] == "temporal"
    old = mem.MemoryUnit.from_text((tmp_path / "memory" / "loc_sh" / "SKILL.md").read_text())
    new = mem.MemoryUnit.from_text((tmp_path / "memory" / "loc_bj" / "SKILL.md").read_text())
    assert old.frontmatter["status"] == "archived" and old.frontmatter["valid_to"] == "2026-06-06"
    assert old.frontmatter["superseded_by"] == "loc_bj"
    assert new.frontmatter["valid_from"] == "2026-06-06"   # the new fact becomes current as of now


def test_none_leaves_everything_untouched(tmp_path: Path) -> None:
    _unit(tmp_path, "a", "User likes tea", ["drink"])
    _unit(tmp_path, "b", "User likes coffee", ["drink"])     # both true — not a conflict
    judge = AIGGReconciler(base_url="x", transport=lambda t: '{"relation":"none"}')
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")
    assert out["reconciled"] == [] and out["needs_review"] == []
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "a" / "SKILL.md").read_text()).frontmatter["status"] == "active"


def test_uncertain_defers_to_human(tmp_path: Path) -> None:
    _unit(tmp_path, "a", "User's budget is 1000", ["budget"])
    _unit(tmp_path, "b", "User's budget is 2000", ["budget"])
    judge = AIGGReconciler(base_url="x", transport=lambda t:
        '{"relation":"uncertain","reason":"cannot tell if corrected or changed"}')
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")
    assert out["reconciled"] == []
    assert [(p["a"], p["b"]) for p in out["needs_review"]] == [("a", "b")]
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "a" / "SKILL.md").read_text()).frontmatter["status"] == "active"
