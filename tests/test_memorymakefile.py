"""MemoryMakefile — the compiled dependency graph (target: prerequisites) over
the units. It's the human navigation view: pick a unit, see what it depends on
and what depends on it (blast radius), then update it.
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.index import CorpusIndex


def _unit(root: Path, slug, kind="semantic", desc="d", match=None,
          deps=None, references=None, supersedes=None, body="b", corpus="memory"):
    fm = {"name": slug, "description": desc, "kind": kind,
          "match": {"user_intent": match or [slug]}, "id": slug, "status": "active"}
    if deps:
        fm["deps"] = deps
    if references:
        fm["references"] = references
    if supersedes:
        fm["supersedes"] = supersedes
    path = root / corpus / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")


def test_dependency_graph_and_blast_radius(tmp_path: Path) -> None:
    _unit(tmp_path, "token_concept")
    _unit(tmp_path, "budget", deps=["token_concept"])
    _unit(tmp_path, "onchainpal_budget", references=["budget"])
    _unit(tmp_path, "new_budget", supersedes=["budget"])

    idx = CorpusIndex(tmp_path, "memory")
    idx.sync()
    assert idx.depends_on("budget") == ["token_concept"]          # forward
    assert idx.depended_by("budget") == ["onchainpal_budget"]     # reverse = blast radius
    assert idx.supersedes("new_budget") == ["budget"]


def test_build_memorymakefile(tmp_path: Path) -> None:
    _unit(tmp_path, "a")
    _unit(tmp_path, "b", deps=["a"])
    _unit(tmp_path, "c", references=["a"])

    mk = mem.build_memorymakefile(tmp_path, "memory")
    assert mk["metadata"]["module_type"] == "memory-makefile"
    assert mk["memories"]["b"]["depends_on"] == ["a"]
    assert sorted(mk["memories"]["a"]["depended_by"]) == ["b", "c"]   # reverse: a is needed by b and c
    # written to disk as a navigable artifact
    out = mem.build_memorymakefile(tmp_path, "memory", write=True)
    assert (tmp_path / "memory" / "MemoryMakefile").exists()


def test_edit_unit_reports_blast_radius(tmp_path: Path) -> None:
    _unit(tmp_path, "core", body="old body")
    _unit(tmp_path, "dependent", references=["core"])

    result = mem.edit_unit(tmp_path, "memory", "core", body="new body", description="updated")
    unit = mem.MemoryUnit.from_text((tmp_path / "memory" / "core" / "SKILL.md").read_text(encoding="utf-8"))
    assert unit.body == "new body" and unit.frontmatter["description"] == "updated"
    # updating core tells you who's affected
    assert result["slug"] == "core" and result["blast_radius"] == ["dependent"]


def test_edit_missing_unit_is_noop(tmp_path: Path) -> None:
    _unit(tmp_path, "x")
    result = mem.edit_unit(tmp_path, "memory", "ghost", body="z")
    assert result["updated"] is False
