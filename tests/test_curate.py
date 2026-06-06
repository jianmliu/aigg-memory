"""curate = LLM value-triage of UNIQUE units: the cleanup that statistics can't do.
A unique 'is this worth keeping?' is a semantic judgment (like contradiction /
dependency), so a model decides. Cost-aware: a cheap structural filter narrows
candidates (active, not pinned/locked, not load-bearing), the LLM judges keep /
trivial / uncertain, and only HIGH-CONFIDENCE trivial is archived — non-destructively,
erring toward keeping (deleting useful memory is worse than keeping a little noise;
git keeps it anyway). pinned/locked are never even candidates."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory import extract as ex
from aigg_memory.extract import AIGGCurator, parse_curation


def test_prompts_anchor_value_on_user_input_not_assistant_output() -> None:
    """Memory's value criterion is valuable USER-provided info; the assistant's own
    output is not memory. Both the extraction and curation prompts must say so."""
    for prompt in (ex._EXTRACTION_SYSTEM, ex._CURATION_SYSTEM):
        assert "user" in prompt.lower()
        assert "assistant" in prompt.lower()   # explicitly excludes the assistant's output


def _unit(root: Path, slug, desc, **fm):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": [slug]}, "id": slug, "status": "active"}
    f.update(fm)
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


def test_parse_curation_tolerant_defaults_to_keep() -> None:
    assert parse_curation('[{"id":"a","verdict":"trivial","reason":"smalltalk"}]') == \
        [{"slug": "a", "verdict": "trivial", "reason": "smalltalk"}]
    # unknown / missing verdict -> 'keep' (never delete on a parse ambiguity)
    assert parse_curation('[{"id":"a","verdict":"???"}]')[0]["verdict"] == "keep"
    assert parse_curation('[{"id":"a"}]')[0]["verdict"] == "keep"
    assert parse_curation("junk") == []


def test_curate_archives_trivial_keeps_the_rest(tmp_path: Path) -> None:
    _unit(tmp_path, "weather_today", "It was raining when we talked")
    _unit(tmp_path, "prefers_metric", "User prefers metric units")
    _unit(tmp_path, "maybe_paris", "User might visit Paris someday")
    curator = AIGGCurator(base_url="x", transport=lambda t:
        '[{"id":"weather_today","verdict":"trivial","reason":"ephemeral"},'
        ' {"id":"prefers_metric","verdict":"keep","reason":"durable preference"},'
        ' {"id":"maybe_paris","verdict":"uncertain","reason":"hypothetical"}]')
    out = mem.curate(tmp_path, "memory", curator, write=True)

    assert out["archived"] == ["weather_today"]
    assert [u["slug"] for u in out["uncertain"]] == ["maybe_paris"]
    st = lambda s: mem.MemoryUnit.from_text((tmp_path / "memory" / s / "SKILL.md").read_text()).frontmatter["status"]
    assert st("weather_today") == "archived"      # clear noise -> gone (non-destructive)
    assert st("prefers_metric") == "active"       # useful -> kept
    assert st("maybe_paris") == "active"          # uncertain -> kept (don't guess)


def test_curate_never_touches_pinned_or_locked(tmp_path: Path) -> None:
    _unit(tmp_path, "persona", "You are a gruff dwarf", locked=True)
    _unit(tmp_path, "identity", "User's name is Alex", pinned=True)
    curator = AIGGCurator(base_url="x", transport=lambda t:    # would call everything trivial
        '[{"id":"persona","verdict":"trivial"},{"id":"identity","verdict":"trivial"}]')
    out = mem.curate(tmp_path, "memory", curator, write=True)
    assert out["reviewed"] == 0 and out["archived"] == []     # neither was even a candidate
    for s in ("persona", "identity"):
        assert mem.MemoryUnit.from_text((tmp_path / "memory" / s / "SKILL.md").read_text()).frontmatter["status"] == "active"


def test_curate_skips_load_bearing_units(tmp_path: Path) -> None:
    _unit(tmp_path, "base_concept", "the token budget concept")
    _unit(tmp_path, "uses_it", "the budget protocol", deps=["base_concept"])   # depends on base_concept
    curator = AIGGCurator(base_url="x", transport=lambda t: '[{"id":"base_concept","verdict":"trivial"}]')
    out = mem.curate(tmp_path, "memory", curator, write=True)
    # base_concept is depended-on -> excluded from candidates, never archived
    assert "base_concept" not in out["archived"]
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "base_concept" / "SKILL.md").read_text()).frontmatter["status"] == "active"


def test_curate_dry_run_flags_but_does_not_archive(tmp_path: Path) -> None:
    _unit(tmp_path, "weather_today", "It was raining")
    curator = AIGGCurator(base_url="x", transport=lambda t: '[{"id":"weather_today","verdict":"trivial"}]')
    out = mem.curate(tmp_path, "memory", curator, write=False)
    assert out["trivial"] == ["weather_today"] and out["archived"] == []
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "weather_today" / "SKILL.md").read_text()).frontmatter["status"] == "active"
