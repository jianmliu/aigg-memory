"""dream = the offline maintenance pass, one orchestrated call. The LIGHT part
(consolidate new evidence -> units, then reconcile new statements) fits every session
end; the DEEP part (compact duplicates + curate unique noise) runs periodically with
deep=True. Trigger/cadence are the app's — the engine ships no scheduler. LLM steps run
only when a client is given."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGCurator, AIGGReconciler
from aigg_memory.store import EvidenceStore


def _obs(root: Path, slug):
    store = EvidenceStore(root / "ev.jsonl", domain=mem.memory_domain())
    store.record("observation", {"slug": slug, "name": slug, "kind": "semantic",
                                 "description": f"fact {slug}", "match": [slug], "body": slug})
    return store.load()


def _unit(root: Path, slug, desc, match):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": match}, "id": slug, "status": "active"}
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


def test_dream_light_consolidates_no_deep(tmp_path: Path) -> None:
    out = mem.dream(tmp_path, "memory", _obs(tmp_path, "fact1"), write=True, min_promote_count=1)
    assert (tmp_path / "memory" / "fact1" / "SKILL.md").exists()
    assert "consolidated" in out
    assert "curated" not in out and "compacted" not in out      # deep skipped by default


def test_dream_reconciles_when_reconciler_given(tmp_path: Path) -> None:
    _unit(tmp_path, "loc_sh", "User lives in Shanghai", ["lives", "location"])
    _unit(tmp_path, "loc_bj", "User lives in Beijing", ["lives", "location"])
    reconciler = AIGGReconciler(base_url="x", transport=lambda t:
        '{"relation":"temporal","current":"loc_bj","reason":"moved"}')
    out = mem.dream(tmp_path, "memory", [], write=True, reconciler=reconciler, now="2026-06-06")
    assert out["reconciled"]["reconciled"]                       # reconcile ran + acted
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "loc_sh" / "SKILL.md").read_text()).frontmatter["status"] == "archived"


def test_dream_deep_runs_compact_and_curate(tmp_path: Path) -> None:
    _unit(tmp_path, "rain_chat", "It was raining when we talked", ["weather"])
    _unit(tmp_path, "prefers_tea", "User prefers tea", ["drink"])
    curator = AIGGCurator(base_url="x", transport=lambda t:
        '[{"id":"rain_chat","verdict":"trivial"},{"id":"prefers_tea","verdict":"keep"}]')
    out = mem.dream(tmp_path, "memory", [], write=True, deep=True, curator=curator)
    assert "compacted" in out and "curated" in out
    assert out["curated"]["archived"] == ["rain_chat"]
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "rain_chat" / "SKILL.md").read_text()).frontmatter["status"] == "archived"


def test_dream_without_deep_does_not_curate(tmp_path: Path) -> None:
    _unit(tmp_path, "rain_chat", "It was raining", ["weather"])
    curator = AIGGCurator(base_url="x", transport=lambda t: '[{"id":"rain_chat","verdict":"trivial"}]')
    out = mem.dream(tmp_path, "memory", [], write=True, deep=False, curator=curator)
    assert "curated" not in out
    assert mem.MemoryUnit.from_text((tmp_path / "memory" / "rain_chat" / "SKILL.md").read_text()).frontmatter["status"] == "active"
