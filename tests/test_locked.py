"""`locked` = owner-authored, protected from the automatic loop. For an agent, the
pinned self-profile is a persona card (人设卡): set by the owner, never auto-updated
by what the conversation says. So reconcile / contradiction detection must NEVER
archive a locked unit — a genuine conflict against it defers to the owner instead.

(Orthogonal to `pinned`: pinned = always injected; locked = don't auto-mutate. A
persona card is both; a learned user fact is pinned-but-not-locked.)"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGContradictionDetector, AIGGReconciler


def _unit(root: Path, slug, desc, match, **fm):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": match}, "id": slug, "status": "active"}
    f.update(fm)
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


def test_edit_locks_and_unlocks(tmp_path: Path) -> None:
    _unit(tmp_path, "persona", "You are a gruff dwarven blacksmith", ["who are you"])
    mem.edit_unit(tmp_path, "memory", "persona", locked=True)
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "persona" / "SKILL.md").read_text()).frontmatter["locked"] is True


def test_merge_keeps_lock_if_either_side_locked() -> None:
    out = mem._merge_frontmatter({"name": "x", "locked": True}, {"name": "x"})
    assert out["locked"] is True


def test_reconcile_never_archives_locked_persona(tmp_path: Path) -> None:
    # owner-set persona, and a conversational claim that contradicts it
    _unit(tmp_path, "persona", "You are a gruff dwarven blacksmith", ["who are you", "role"], locked=True, pinned=True)
    _unit(tmp_path, "claim", "You are a cheerful elf", ["who are you", "role"])
    # even if the judge says the claim is 'current', a locked old must NOT be archived
    judge = AIGGReconciler(base_url="x", transport=lambda t:
        '{"relation":"correction","current":"claim","reason":"user said so"}')
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-06")

    assert out["reconciled"] == []                                   # nothing auto-applied
    assert out["needs_review"] and out["needs_review"][0].get("locked") is True
    persona = mem.MemoryUnit.from_text((tmp_path / "memory" / "persona" / "SKILL.md").read_text())
    assert persona.frontmatter["status"] == "active"                # persona untouched


def test_contradiction_does_not_archive_locked_loser(tmp_path: Path) -> None:
    _unit(tmp_path, "persona", "The agent's name is Thorin", ["name"], locked=True)
    _unit(tmp_path, "claim", "The agent's name is Bilbo", ["name"])
    detector = AIGGContradictionDetector(base_url="x", transport=lambda t:
        '[{"a":"claim","b":"persona","winner":"claim","reason":"?"}]')  # would archive the locked persona
    out = mem.detect_contradictions(tmp_path, "memory", detector, threshold=0.3, write=True)

    assert out["resolved"] == []
    assert any(p.get("locked") for p in out["needs_review"])
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "persona" / "SKILL.md").read_text()).frontmatter["status"] == "active"
