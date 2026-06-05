"""Contradiction detection — the semantic half of conflict handling.

Embeddings can't tell contradiction from similarity (two opposite facts about the
same thing are highly similar). So: cheap semantic similarity narrows to same-topic
*candidate* pairs, then an external AIGG model judges which genuinely contradict.
Resolution archives the loser (non-destructive, restorable) and records the
supersession on the winner. Cost-aware: the LLM only sees candidates.
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGContradictionDetector, parse_contradictions


def _unit(root: Path, slug, desc, match, body):
    fm = {"name": slug, "description": desc, "kind": "semantic",
          "match": {"user_intent": match}, "id": slug, "status": "active"}
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")


def test_parse_contradictions_tolerant() -> None:
    assert parse_contradictions('```json\n[{"a":"x","b":"y","winner":"y","reason":"r"}]\n```') == \
        [{"a": "x", "b": "y", "winner": "y", "reason": "r"}]
    assert parse_contradictions("no json") == []
    assert parse_contradictions('[{"a":"x","b":"y"}]') == []  # missing winner dropped


def test_detect_and_resolve_contradiction(tmp_path: Path) -> None:
    _unit(tmp_path, "timeout_a", "the api timeout is 30 seconds", ["timeout"], "30s")
    _unit(tmp_path, "timeout_b", "the api timeout is 60 seconds", ["timeout"], "60s")
    _unit(tmp_path, "weather", "weather forecast tomorrow", ["weather"], "sunny")

    detector = AIGGContradictionDetector(base_url="x", transport=lambda text:
        '[{"a":"timeout_a","b":"timeout_b","winner":"timeout_b","reason":"60s is the corrected value"}]')
    result = mem.detect_contradictions(tmp_path, "memory", detector, threshold=0.3, write=True)

    assert result["contradictions"] and result["contradictions"][0]["winner"] == "timeout_b"
    # the loser is ARCHIVED (not deleted — restorable), winner records the supersession
    loser = mem.MemoryUnit.from_text((tmp_path / "memory" / "timeout_a" / "SKILL.md").read_text(encoding="utf-8"))
    assert loser.frontmatter["status"] == "archived" and loser.frontmatter["superseded_by"] == "timeout_b"
    winner = mem.MemoryUnit.from_text((tmp_path / "memory" / "timeout_b" / "SKILL.md").read_text(encoding="utf-8"))
    assert "timeout_a" in winner.frontmatter["supersedes"]


def test_detect_validates_winner_and_slugs(tmp_path: Path) -> None:
    _unit(tmp_path, "a", "the value is X", ["value"], "X")
    _unit(tmp_path, "b", "the value is Y", ["value"], "Y")
    # invalid: winner not one of the pair; and a ghost slug
    detector = AIGGContradictionDetector(base_url="x", transport=lambda text:
        '[{"a":"a","b":"b","winner":"c","reason":"?"},'
        ' {"a":"a","b":"ghost","winner":"a","reason":"?"}]')
    result = mem.detect_contradictions(tmp_path, "memory", detector, threshold=0.3, write=True)
    assert result["contradictions"] == []                        # both dropped by validation
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "a" / "SKILL.md").read_text()).frontmatter["status"] == "active"


def test_dry_run_does_not_modify(tmp_path: Path) -> None:
    _unit(tmp_path, "a", "the value is X", ["value"], "X")
    _unit(tmp_path, "b", "the value is Y", ["value"], "Y")
    detector = AIGGContradictionDetector(base_url="x", transport=lambda text:
        '[{"a":"a","b":"b","winner":"b","reason":"r"}]')
    result = mem.detect_contradictions(tmp_path, "memory", detector, threshold=0.3, write=False)
    assert result["contradictions"]                              # found
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "a" / "SKILL.md").read_text()).frontmatter["status"] == "active"
