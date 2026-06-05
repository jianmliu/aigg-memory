"""Memory as a versioned store (git semantics over the corpus).

The corpus is plain SKILL.md text, so it is directly versionable. Consolidation /
compaction / edits become commits; nothing is destroyed — a 'forgotten' unit
leaves HEAD but stays in history and can be restored. The derived index +
MemoryMakefile are gitignored.
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory import versioning as vcs


def _unit(root: Path, slug, body="b"):
    fm = {"name": slug, "description": slug, "kind": "semantic",
          "match": {"user_intent": [slug]}, "id": slug, "status": "active"}
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")


def test_commit_and_log(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _unit(tmp_path, "a")
    h1 = vcs.commit(root, "Dream: learned a")
    assert h1 and (root / ".git").exists()
    assert vcs.commit(root, "no change") is None        # nothing to commit

    _unit(tmp_path, "b")
    h2 = vcs.commit(root, "Dream: learned b")
    log = vcs.log(root)
    assert any("learned b" in line for line in log) and any("learned a" in line for line in log)


def test_derived_artifacts_are_gitignored(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _unit(tmp_path, "a")
    (root / ".aimm-index.db").write_text("binary")       # a derived cache
    (root / "MemoryMakefile").write_text("derived")
    vcs.commit(root, "init")
    tracked = vcs._git(root, "ls-files").stdout
    assert "a/SKILL.md" in tracked
    assert ".aimm-index.db" not in tracked and "MemoryMakefile" not in tracked  # derived, not versioned


def test_forgetting_is_reversible(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _unit(tmp_path, "old_fact")
    vcs.commit(root, "remember old_fact")

    # 'forget' it — remove from HEAD (e.g. compaction / eviction), then commit
    (root / "old_fact" / "SKILL.md").unlink()
    (root / "old_fact").rmdir()
    vcs.commit(root, "forget old_fact")
    assert not (root / "old_fact" / "SKILL.md").exists()

    # the diff of the forgetting commit shows it removed
    d = vcs.diff(root, "HEAD~1", "HEAD")
    assert d["removed"] == ["old_fact"]

    # but it is NOT gone — restore it from history
    vcs.restore(root, "HEAD~1")
    assert (root / "old_fact" / "SKILL.md").exists()


def test_diff_reports_unit_level_changes(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _unit(tmp_path, "keep")
    _unit(tmp_path, "gone")
    vcs.commit(root, "v1")
    _unit(tmp_path, "fresh")
    (root / "gone" / "SKILL.md").unlink(); (root / "gone").rmdir()
    vcs.commit(root, "v2")
    d = vcs.diff(root, "HEAD~1", "HEAD")
    assert d["added"] == ["fresh"] and d["removed"] == ["gone"]
