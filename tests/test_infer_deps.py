"""LLM-built dependency graph: an external AIGG model reads the units and asserts
DIRECTED dependencies (depends_on / references / supersedes) that embeddings can't
infer. The output is validated against real slugs (no hallucinated edges) before
it's written into the units / the MemoryMakefile.
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGDependencyInferrer, parse_edges


def _unit(root: Path, slug, desc, match=None):
    fm = {"name": slug, "description": desc, "kind": "semantic",
          "match": {"user_intent": match or [slug]}, "id": slug, "status": "active"}
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, "body").to_text(), encoding="utf-8")


def test_parse_edges_tolerates_fences_and_garbage() -> None:
    assert parse_edges("```json\n[{\"from\":\"a\",\"to\":\"b\",\"rel\":\"depends_on\"}]\n```") == \
        [{"from": "a", "to": "b", "rel": "depends_on"}]
    assert parse_edges("sorry, no JSON here") == []
    assert parse_edges('[{"from":"a","rel":"depends_on"}]') == []  # missing 'to' dropped


def test_infer_validates_against_real_slugs(tmp_path: Path) -> None:
    _unit(tmp_path, "token_concept", "what a token is")
    _unit(tmp_path, "budget", "token budget contract")
    _unit(tmp_path, "onchainpal", "onchainpal budget control")

    canned = (
        '[{"from":"budget","to":"token_concept","rel":"depends_on"},'
        ' {"from":"onchainpal","to":"budget","rel":"references"},'
        ' {"from":"budget","to":"ghost","rel":"depends_on"},'      # invalid: ghost doesn't exist
        ' {"from":"budget","to":"budget","rel":"depends_on"}]'     # self-loop
    )
    inferrer = AIGGDependencyInferrer(base_url="x", transport=lambda text: canned)

    # dry-run: validated edges returned, frontmatter untouched
    dry = mem.infer_dependencies(tmp_path, "memory", inferrer, write=False)
    assert {(e["from"], e["to"]) for e in dry["edges"]} == {("budget", "token_concept"), ("onchainpal", "budget")}
    assert dry["wrote"] is False
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "budget" / "SKILL.md").read_text()).frontmatter.get("deps") is None


def test_infer_writes_directed_deps_into_units(tmp_path: Path) -> None:
    _unit(tmp_path, "token_concept", "what a token is")
    _unit(tmp_path, "budget", "token budget contract")
    canned = '[{"from":"budget","to":"token_concept","rel":"depends_on"}]'
    inferrer = AIGGDependencyInferrer(base_url="x", transport=lambda text: canned)

    result = mem.infer_dependencies(tmp_path, "memory", inferrer, write=True)
    assert result["wrote"] is True
    unit = mem.MemoryUnit.from_text((tmp_path / "memory" / "budget" / "SKILL.md").read_text(encoding="utf-8"))
    assert unit.frontmatter["deps"] == ["token_concept"]          # directed edge written into the source unit

    # and it shows up in the compiled MemoryMakefile (with the reverse edge)
    graph = mem.build_memorymakefile(tmp_path, "memory")["memories"]
    assert graph["budget"]["depends_on"] == ["token_concept"]
    assert graph["token_concept"]["depended_by"] == ["budget"]


def test_inferrer_passes_aigg_headers() -> None:
    inferrer = AIGGDependencyInferrer(base_url="x", extra_headers={"X-Task-Id": "deps-1"},
                                      transport=lambda text: "[]")
    assert inferrer.extra_headers["X-Task-Id"] == "deps-1"
    assert inferrer.infer([{"slug": "a", "description": "d"}]) == []
