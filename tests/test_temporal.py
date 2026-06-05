"""The temporal dimension — the three pieces git's transaction-time history can't
express on its own (git owns "when did we *record* this"; these add "when was it
*true*", "what came before what", and an indexed temporal query).

  (1) valid/world time  -> frontmatter fields (valid_from / valid_to)
  (2) temporal ordering -> a `precedes` edge, same machinery as depends_on/infer-deps
  (3) indexed retrieval -> a column in the derived index (timeline / as_of)
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGTemporalInferrer, parse_edges
from aigg_memory.index import CorpusIndex


def _unit(root: Path, slug, desc="d", match=None, **fm_extra):
    fm = {"name": slug, "description": desc, "kind": "episodic",
          "match": {"user_intent": match or [slug]}, "id": slug, "status": "active"}
    fm.update(fm_extra)
    path = root / "memory" / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mem.MemoryUnit(fm, "body").to_text(), encoding="utf-8")


# --- (1) valid/world time in frontmatter -----------------------------------

def test_edit_unit_sets_valid_time(tmp_path: Path) -> None:
    _unit(tmp_path, "reorg")
    mem.edit_unit(tmp_path, "memory", "reorg", valid_from="2025-01-01", valid_to="2025-06-30")
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "reorg" / "SKILL.md").read_text())
    assert u.frontmatter["valid_from"] == "2025-01-01"
    assert u.frontmatter["valid_to"] == "2025-06-30"


def test_merge_carries_valid_time(tmp_path: Path) -> None:
    a = {"name": "x", "valid_from": "2025-01-01", "updated": "2025-01-01"}
    b = {"name": "x", "valid_to": "2025-12-31", "updated": "2025-02-01"}
    out = mem._merge_frontmatter(a, b)
    assert out["valid_from"] == "2025-01-01" and out["valid_to"] == "2025-12-31"


# --- (2) temporal ordering edge (precedes) ---------------------------------

def test_parse_edges_accepts_precedes() -> None:
    assert parse_edges('[{"from":"a","to":"b","rel":"precedes"}]') == \
        [{"from": "a", "to": "b", "rel": "precedes"}]


def test_infer_temporal_writes_precedes_edge(tmp_path: Path) -> None:
    _unit(tmp_path, "reorg", "the company reorganized")
    _unit(tmp_path, "promo", "alice was promoted")
    # the model asserts reorg precedes promo; a ghost node is dropped by slug validation
    inferrer = AIGGTemporalInferrer(base_url="x", transport=lambda text:
        '[{"from":"reorg","to":"promo","rel":"precedes"},'
        ' {"from":"reorg","to":"ghost","rel":"precedes"}]')
    result = mem.infer_temporal(tmp_path, "memory", inferrer, write=True)
    assert {"from": "reorg", "to": "promo", "rel": "precedes"} in result["applied"]
    assert all(e["to"] != "ghost" for e in result["applied"])          # ghost dropped
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "reorg" / "SKILL.md").read_text())
    assert u.frontmatter["precedes"] == ["promo"]
    # the edge is in the index and navigable both ways
    idx = CorpusIndex(tmp_path, "memory")
    assert idx.precedes("reorg") == ["promo"]
    assert idx.preceded_by("promo") == ["reorg"]
    # ...and it does NOT pollute the dependency graph
    assert idx.depends_on("reorg") == [] and idx.depended_by("promo") == []


# --- (3) indexed temporal retrieval (timeline / as_of) ---------------------

def test_index_timeline_orders_by_valid_from(tmp_path: Path) -> None:
    _unit(tmp_path, "late", valid_from="2025-09-01")
    _unit(tmp_path, "early", valid_from="2025-01-01")
    _unit(tmp_path, "mid", valid_from="2025-05-01")
    _unit(tmp_path, "undated")                                          # no valid_from -> excluded
    rows = CorpusIndex(tmp_path, "memory").timeline()
    assert [r["slug"] for r in rows] == ["early", "mid", "late"]


def test_index_as_of_returns_units_valid_at_time(tmp_path: Path) -> None:
    _unit(tmp_path, "closed", valid_from="2025-01-01", valid_to="2025-06-01")
    _unit(tmp_path, "open", valid_from="2025-03-01")                    # still valid (no end)
    _unit(tmp_path, "future", valid_from="2025-09-01")
    got = {r["slug"] for r in CorpusIndex(tmp_path, "memory").as_of("2025-07-01")}
    assert got == {"open"}                                              # closed ended, future not begun
    got2 = {r["slug"] for r in CorpusIndex(tmp_path, "memory").as_of("2025-04-01")}
    assert got2 == {"closed", "open"}
