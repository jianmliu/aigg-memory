"""The derived SQLite corpus index — a regenerable cache over the units."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.index import CorpusIndex, _scan_select, select_and_count


def _write_unit(root: Path, slug, kind, desc, match, body, status="active", corpus="memory"):
    fm = {"name": slug, "description": desc, "kind": kind,
          "match": {"user_intent": match}, "id": slug, "status": status,
          "confidence": "high", "observations": 2}
    path = root / corpus / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, body).to_text(), encoding="utf-8")
    return path


def test_index_builds_and_queries(tmp_path: Path) -> None:
    _write_unit(tmp_path, "budget", "semantic", "token_budget contract", ["token budget", "cost"], "the note")
    _write_unit(tmp_path, "tdd", "procedural", "red green refactor", ["tdd", "test first"], "steps")

    idx = CorpusIndex(tmp_path, "memory")
    units = idx.query("token budget please", n_best=5)
    assert [u["name"] for u in units] == ["budget"]
    assert units[0]["kind"] == "semantic" and units[0]["body"] == "the note"
    assert idx.size() == 2
    # the index db is colocated and NOT a unit file
    assert (tmp_path / "memory" / ".aimm-index.db").exists()
    assert "/.aimm-index.db" not in [p.as_posix() for p in (tmp_path / "memory").glob("*/SKILL.md")]


def test_index_kind_filter_and_archived_excluded(tmp_path: Path) -> None:
    _write_unit(tmp_path, "proc", "procedural", "sword technique", ["sword"], "grip")
    _write_unit(tmp_path, "fact", "semantic", "sword theory", ["sword"], "theory")
    _write_unit(tmp_path, "old", "semantic", "retired", ["sword"], "x", status="archived")
    idx = CorpusIndex(tmp_path, "memory")
    sem = idx.query("sword", kinds=["semantic"])
    names = [u["name"] for u in sem]
    assert "fact" in names and "proc" not in names and "old" not in names  # kind filter + archived excluded


def test_index_incremental_update_on_edit_and_delete(tmp_path: Path) -> None:
    _write_unit(tmp_path, "u", "semantic", "old", ["alpha"], "old body")
    idx = CorpusIndex(tmp_path, "memory")
    assert [u["name"] for u in idx.query("alpha")] == ["u"]

    # edit: change the match term -> old term no longer matches, new one does
    _write_unit(tmp_path, "u", "semantic", "new", ["beta"], "new body")
    assert idx.query("alpha") == []
    got = idx.query("beta")
    assert got and got[0]["body"] == "new body"

    # delete the unit dir -> dropped from the index
    import shutil
    shutil.rmtree(tmp_path / "memory" / "u")
    assert idx.query("beta") == [] and idx.size() == 0


def test_index_equivalent_to_scan(tmp_path: Path) -> None:
    for slug, kind, terms in [("a", "semantic", ["alpha", "shared"]), ("b", "procedural", ["beta", "shared"])]:
        _write_unit(tmp_path, slug, kind, f"desc {slug}", terms, f"body {slug}")
    workspace = mem.load_corpus(tmp_path, "memory")
    scan = _scan_select(workspace, "shared alpha", 5, None)
    indexed, total = select_and_count(tmp_path, "memory", "shared alpha", n_best=5)
    assert total == 2
    # same units, same ranking
    assert [(u["name"], u["score"]) for u in indexed] == [(u["name"], u["score"]) for u in scan]


def test_consolidate_corpus_refreshes_index(tmp_path: Path) -> None:
    def obs(slug, ev):
        return mem.MemoryUnit  # placeholder to keep imports tidy

    from aigg_memory import EvidenceRecord
    records = [
        EvidenceRecord(1, "t1", "observation", "f",
                       {"slug": "sage", "name": "sage", "kind": "semantic", "description": "wisdom",
                        "match": ["wise"], "body": "note"}, None, "h", "e1"),
        EvidenceRecord(1, "t2", "observation", "f",
                       {"slug": "sage", "name": "sage", "kind": "semantic", "description": "wisdom",
                        "match": ["wise"], "body": "note"}, None, "h", "e2"),
    ]
    mem.consolidate_corpus(tmp_path, records, write=True)
    # the index exists and serves the new unit without a manual sync
    units, total = select_and_count(tmp_path, "memory", "be wise", n_best=5)
    assert total == 1 and [u["name"] for u in units] == ["sage"]


def test_empty_corpus(tmp_path: Path) -> None:
    units, total = select_and_count(tmp_path, "memory", "anything")
    assert units == [] and total == 0
